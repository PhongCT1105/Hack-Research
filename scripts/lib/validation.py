"""Offline validation for OpenAlex collection and provisional bundle artifacts."""

from __future__ import annotations

import csv
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Mapping, Sequence
import unicodedata

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
import yaml

from .bundles import validate_openalex_bundle_semantics


VALIDATOR_VERSION = "openalex-dataset-validator-v1"
FINAL_BLOCKERS = (
    "faculty_status_unverified",
    "author_identity_unverified",
    "crossref_metadata_unreconciled",
    "semantic_scholar_authorship_unverified",
    "legal_full_text_not_retrieved",
    "focal_passages_missing",
    "topic_coherence_unreviewed",
    "synthesis_difficulty_unreviewed",
)
PUBLIC_DIRECTORIES = ("data/interim", "data/final")
TEXT_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".md", ".txt", ".yaml", ".yml"})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROFESSOR_ID = re.compile(r"^[A-Z][A-Z0-9_]{1,15}-[0-9]{2,3}$")
_OPENALEX_ID = re.compile(r"^[AISTW][0-9]+$")
_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)"
        r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{6,}"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)


def validate_openalex_collection(dataset_root: str | Path) -> dict[str, Any]:
    """Validate local collection tables, joins, raw hashes, and completion evidence."""

    root = Path(dataset_root).resolve()
    errors: list[str] = []
    checks: dict[str, bool] = {}
    counts = {
        "institutions": 0,
        "raw_author_candidates": 0,
        "work_records": 0,
        "selected_professors": 0,
        "selected_papers": 0,
        "focal_papers": 0,
    }

    config = _read_yaml_mapping(root / "config/dataset.yaml", errors, "configuration")
    required_version_fields = ("dataset_version", "schema_version", "candidate_pool_version")
    for field in required_version_fields:
        if not _string(config.get(field)):
            errors.append(f"configuration: missing {field}")
    checks["configuration"] = not any(error.startswith("configuration:") for error in errors)

    institutions = _read_table(root / "data/interim/institutions.csv", errors, "institutions")
    candidates = _read_table(
        root / "data/interim/author_candidates.csv", errors, "author candidates"
    )
    works = _read_table(root / "data/raw/author_works.jsonl", errors, "author works")
    selected = _read_table(root / "data/interim/candidate_papers.csv", errors, "candidate papers")
    sampled = _read_table(
        root / "data/final/verified_professors.csv", errors, "selected professors"
    )
    counts.update(
        {
            "institutions": len(institutions),
            "raw_author_candidates": len(candidates),
            "work_records": len(works),
            "selected_professors": len(sampled),
        }
    )
    checks["required_tables"] = all(
        bool(rows) for rows in (institutions, candidates, works, selected, sampled)
    )

    institution_ids = _unique_ids(
        institutions,
        ("institution_id", "openalex_institution_id", "openalex_id", "id"),
        "institution",
        errors,
        prefix="I",
    )
    candidate_author_ids = _unique_ids(
        candidates,
        ("openalex_author_id", "openalex_author_url"),
        "candidate author",
        errors,
        prefix="A",
    )
    sampled_ids = _unique_ids(
        sampled, ("professor_id",), "selected professor", errors, professor=True
    )
    optional_candidate_professor_ids = {
        professor_id
        for row in candidates
        if (professor_id := _string(row.get("professor_id"))) is not None
    }
    for index, professor_id in enumerate(sorted(optional_candidate_professor_ids), start=1):
        if not _PROFESSOR_ID.fullmatch(professor_id):
            errors.append(f"candidate professor row {index} has an invalid ID")
    professor_ids = sampled_ids | optional_candidate_professor_ids
    checks["unique_ids"] = not any("duplicate" in error for error in errors)

    sampled_by_professor = {
        _first_id(row, ("professor_id",)): row
        for row in sampled
        if _first_id(row, ("professor_id",))
    }
    candidate_author_by_professor = {
        professor_id: _canonical_openalex_id(
            row.get("openalex_author_id") or row.get("openalex_author_url"), "A"
        )
        for professor_id, row in sampled_by_professor.items()
    }
    for professor_id, author_id in candidate_author_by_professor.items():
        if author_id is None:
            errors.append(f"selected professor {professor_id} has an invalid OpenAlex author ID")
        elif author_id not in candidate_author_ids:
            errors.append(f"selected professor {professor_id} is absent from author candidates")
    for row in candidates:
        for institution_id in _id_list(row.get("discovery_institution_ids"), "I"):
            if institution_id not in institution_ids:
                errors.append(f"author candidate references unknown institution {institution_id}")

    works_by_professor: dict[str, dict[str, Mapping[str, Any]]] = {}
    work_pairs: set[tuple[str, str]] = set()
    expected_schema_version = _string(config.get("schema_version"))
    for index, work in enumerate(works, start=1):
        professor_id = _string(work.get("professor_id"))
        if professor_id not in professor_ids:
            errors.append(f"author work row {index} references unknown professor {professor_id!r}")
            continue
        author_id = _canonical_openalex_id(
            work.get("openalex_author_id") or work.get("openalex_author_url"), "A"
        )
        if author_id is None or author_id != candidate_author_by_professor.get(professor_id):
            errors.append(f"author work row {index} has an invalid candidate-author join")
        work_id = _canonical_openalex_id(
            work.get("paper_id") or work.get("openalex_work_id") or work.get("id"), "W"
        )
        if work_id is None:
            errors.append(f"author work row {index} has an invalid OpenAlex work ID")
            continue
        pair = (professor_id, work_id)
        if pair in work_pairs:
            errors.append(f"duplicate work ID {work_id} for professor {professor_id}")
        work_pairs.add(pair)
        works_by_professor.setdefault(professor_id, {})[work_id] = work
        row_schema_version = _string(work.get("schema_version"))
        if (
            row_schema_version
            and expected_schema_version
            and row_schema_version != expected_schema_version
        ):
            errors.append(
                f"author work {work_id} schema version {row_schema_version} does not match "
                f"{expected_schema_version}"
            )

    selected_by_professor: dict[str, list[tuple[str, bool]]] = {}
    for index, row in enumerate(selected, start=1):
        if not _truthy(row.get("selected")):
            continue
        professor_id = _string(row.get("professor_id"))
        work_id = _canonical_openalex_id(
            row.get("paper_id") or row.get("openalex_work_id") or row.get("id"), "W"
        )
        if professor_id not in professor_ids:
            errors.append(
                f"selected paper row {index} references unknown professor {professor_id!r}"
            )
            continue
        if work_id is None or work_id not in works_by_professor.get(professor_id, {}):
            errors.append(
                f"selected paper row {index} references unknown work {work_id!r} for {professor_id}"
            )
            continue
        selected_by_professor.setdefault(professor_id, []).append(
            (work_id, _truthy(row.get("focal")))
        )

    for professor_id in sampled_ids:
        if professor_id not in professor_ids:
            errors.append(f"selected professor {professor_id} is absent from collection tables")
            continue
        papers = selected_by_professor.get(professor_id, [])
        paper_ids = [paper_id for paper_id, _ in papers]
        focal_ids = [paper_id for paper_id, focal in papers if focal]
        if len(paper_ids) != 8 or len(set(paper_ids)) != 8:
            errors.append(f"{professor_id}: expected exactly 8 unique selected papers")
        if len(focal_ids) != 2 or len(set(focal_ids)) != 2:
            errors.append(f"{professor_id}: expected exactly 2 unique focal papers")
    counts["selected_papers"] = sum(len(papers) for papers in selected_by_professor.values())
    counts["focal_papers"] = sum(
        1 for papers in selected_by_professor.values() for _, focal in papers if focal
    )
    checks["joins"] = not any(
        token in error
        for error in errors
        for token in ("references unknown", "join", "absent from")
    )
    checks["selection_counts"] = not any("expected exactly" in error for error in errors)

    raw_hashes, checkpoint_valid = _validate_checkpoints(root, errors)
    marker_valid = _validate_completeness_markers(
        root, sampled_ids, candidate_author_by_professor, works_by_professor, raw_hashes, errors
    )
    checks["raw_checksums"] = checkpoint_valid
    checks["checkpoints_complete"] = checkpoint_valid
    checks["work_histories_complete"] = marker_valid

    deterministic_valid = _validate_deterministic_metadata(
        root, config, selected, sampled, sampled_ids, errors
    )
    checks["deterministic_metadata"] = deterministic_valid
    return {
        "valid": not errors,
        "errors": errors,
        "checks": checks,
        "counts": counts,
        "raw_files": sorted(raw_hashes),
        "raw_checksums_sha256": dict(sorted(raw_hashes.items())),
        "versions": {
            "dataset_version": config.get("dataset_version"),
            "schema_version": config.get("schema_version"),
            "candidate_pool_version": config.get("candidate_pool_version"),
        },
    }


def validate_provisional_bundles(
    dataset_root: str | Path,
    bundle_dir: str | Path | None = None,
    schema_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate provisional bundle schema, joins, hashes, 8+2 selection, and task coverage."""

    root = Path(dataset_root).resolve()
    errors: list[str] = []
    config = _read_yaml_mapping(root / "config/dataset.yaml", errors, "configuration")
    resolved_schema = _resolve_schema_path(root, schema_path)
    validator: Draft202012Validator | None = None
    try:
        schema = json.loads(resolved_schema.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, SchemaError) as error:
        errors.append(f"bundle schema {resolved_schema}: {error}")

    selected_rows = _read_table(
        root / "data/interim/candidate_papers.csv", errors, "candidate papers"
    )
    sampled_rows = _read_table(
        root / "data/final/verified_professors.csv", errors, "selected professors"
    )
    sampled_ids = {
        professor_id
        for row in sampled_rows
        if (professor_id := _string(row.get("professor_id"))) is not None
    }
    selected_ids: dict[str, set[str]] = {}
    for row in selected_rows:
        if not _truthy(row.get("selected")):
            continue
        professor_id = _string(row.get("professor_id"))
        paper_id = _canonical_openalex_id(
            row.get("paper_id") or row.get("openalex_work_id") or row.get("id"), "W"
        )
        if professor_id and paper_id:
            selected_ids.setdefault(professor_id, set()).add(paper_id)

    resolved_bundle_dir = _resolve_under_root(
        root, bundle_dir or "data/final/openalex_profile_bundles"
    )
    bundle_paths = (
        sorted(resolved_bundle_dir.glob("*.json")) if resolved_bundle_dir.is_dir() else []
    )
    if not bundle_paths:
        errors.append(f"provisional bundles: no JSON files found in {resolved_bundle_dir}")

    raw_hashes = {
        _file_sha256(path)
        for path in sorted((root / "data/raw/pages").rglob("*.json"))
        if path.is_file()
    }
    seen_professors: set[str] = set()
    source_retrieved_at: list[str] = []
    collection_code_versions: set[str] = set()
    for path in bundle_paths:
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(bundle, dict):
                raise TypeError("bundle is not a JSON object")
            if validator is None:
                raise ValueError("bundle schema is unavailable")
            validator.validate(bundle)
            validate_openalex_bundle_semantics(bundle)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            TypeError,
            ValidationError,
            ValueError,
        ) as error:
            errors.append(f"{path.name}: {error}")
            continue

        professor_id = _string(bundle.get("professor_id"))
        if professor_id is None or not _PROFESSOR_ID.fullmatch(professor_id):
            errors.append(f"{path.name}: invalid professor_id")
            continue
        if professor_id in seen_professors:
            errors.append(f"{path.name}: duplicate professor_id {professor_id}")
        seen_professors.add(professor_id)
        if professor_id not in sampled_ids:
            errors.append(f"{path.name}: professor_id {professor_id} is not in selected professors")
        bundle_paper_ids = {
            _canonical_openalex_id(paper.get("paper_id"), "W")
            for paper in bundle.get("selected_papers", [])
            if isinstance(paper, Mapping)
        }
        if bundle_paper_ids != selected_ids.get(professor_id, set()):
            errors.append(f"{path.name}: selected-paper join does not match Stage 9")
        if bundle.get("dataset_version") != config.get("dataset_version"):
            errors.append(f"{path.name}: dataset_version does not match configuration")
        if bundle.get("candidate_pool_version") != config.get("candidate_pool_version"):
            errors.append(f"{path.name}: candidate_pool_version does not match configuration")
        if bundle.get("schema_version") != config.get("schema_version"):
            errors.append(f"{path.name}: schema_version does not match configuration")
        configured_bundle_version = _nested(config, "collection", "bundle_version")
        if configured_bundle_version and bundle.get("bundle_version") != configured_bundle_version:
            errors.append(f"{path.name}: bundle_version does not match configuration")
        provenance = bundle.get("provenance")
        if isinstance(provenance, Mapping):
            for checksum in provenance.get("raw_source_hashes", []):
                if checksum not in raw_hashes:
                    errors.append(f"{path.name}: unknown raw source checksum {checksum}")
            retrieved_at = _string(provenance.get("retrieved_at"))
            if retrieved_at:
                source_retrieved_at.append(retrieved_at)
            code_version = _string(provenance.get("collection_code_version"))
            if code_version:
                collection_code_versions.add(code_version)

    missing_bundles = sampled_ids - seen_professors
    for professor_id in sorted(missing_bundles):
        errors.append(f"selected professor {professor_id} has no provisional bundle")
    return {
        "valid": not errors,
        "errors": errors,
        "checks": {
            "schema_validation": validator is not None
            and not any("schema" in error.casefold() for error in errors),
            "unique_professor_ids": not any("duplicate professor_id" in error for error in errors),
            "selection_joins": not any("join" in error for error in errors),
            "task_coverage": not any("task" in error.casefold() for error in errors),
            "raw_hashes": not any("raw source checksum" in error for error in errors),
        },
        "bundle_count": len(bundle_paths),
        "retrieval_window_start": min(source_retrieved_at) if source_retrieved_at else None,
        "retrieval_window_end": max(source_retrieved_at) if source_retrieved_at else None,
        "collection_code_versions": sorted(collection_code_versions),
    }


def scan_public_artifacts(
    dataset_root: str | Path,
    public_paths: Sequence[str | Path] | None = None,
    identity_names: Iterable[str] | None = None,
    tracked_files: Sequence[str | Path] | None = None,
) -> dict[str, Any]:
    """Scan public outputs for secret material, private names, and tracked PDF files."""

    root = Path(dataset_root).resolve()
    errors: list[str] = []
    names = set(identity_names or ())
    names.update(_private_identity_names(root / "data/private/professor_identity_map.csv"))
    normalized_names = {
        _normalized_text(name) for name in names if len(_normalized_text(name)) >= 4
    }
    files = _public_files(root, public_paths)
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            errors.append(f"public artifact {path}: cannot read text: {error}")
            continue
        relative = _relative_display(path, root)
        if any(pattern.search(text) for pattern in _SECRET_PATTERNS):
            errors.append(f"public artifact {relative} contains a secret-like value")
        normalized = _normalized_text(text)
        leaked_names = sorted(name for name in normalized_names if name in normalized)
        if leaked_names:
            errors.append(f"public artifact {relative} contains a private identity name")

    tracked = [Path(value).as_posix() for value in (tracked_files or _git_tracked_files(root))]
    tracked_pdfs = sorted(path for path in tracked if Path(path).suffix.casefold() == ".pdf")
    for path in tracked_pdfs:
        errors.append(f"tracked PDF is prohibited: {path}")
    return {
        "valid": not errors,
        "errors": errors,
        "checks": {
            "secret_absence": not any("secret-like" in error for error in errors),
            "public_identity_absence": not any("identity name" in error for error in errors),
            "tracked_pdf_absence": not tracked_pdfs,
        },
        "files_scanned": len(files),
        "tracked_pdfs": tracked_pdfs,
    }


def build_manifest(
    dataset_root: str | Path,
    collection: Mapping[str, Any],
    bundles: Mapping[str, Any],
    public_scan: Mapping[str, Any],
    *,
    template_path: str | Path | None = None,
) -> dict[str, Any]:
    """Populate a deterministic provisional manifest while keeping final gates strict."""

    root = Path(dataset_root).resolve()
    template = _resolve_manifest_template(root, template_path)
    manifest = deepcopy(_read_yaml_mapping(template, [], "manifest template"))
    config_path = root / "config/dataset.yaml"
    config = _read_yaml_mapping(config_path, [], "configuration")
    public_scan_valid = bool(public_scan.get("valid"))
    counts = dict(manifest.get("counts", {}))
    counts.update(collection.get("counts", {}))
    counts["verified_professors"] = 0
    counts["evidence_passages"] = 0
    manifest.update(
        {
            "template_only": False,
            "status": "provisional_openalex_collection",
            "dataset_version": config.get("dataset_version"),
            "schema_version": config.get("schema_version"),
            "candidate_pool_version": config.get("candidate_pool_version"),
            "configuration_path": "config/dataset.yaml",
            "configuration_checksum_sha256": _file_sha256(config_path)
            if config_path.is_file()
            else None,
            "counts": counts,
            "validation": {
                "openalex_collection_valid": bool(collection.get("valid") and public_scan_valid),
                "provisional_bundle_valid": bool(bundles.get("valid") and public_scan_valid),
                "final_evidence_packet_ready": False,
                "final_blockers": list(FINAL_BLOCKERS),
            },
        }
    )
    source_snapshots = dict(manifest.get("source_snapshots", {}))
    source_snapshots.update(
        {
            "retrieval_window_start": bundles.get("retrieval_window_start"),
            "retrieval_window_end": bundles.get("retrieval_window_end"),
            "providers": ["openalex"],
            "raw_files": list(collection.get("raw_files", [])),
            "raw_checksums_sha256": dict(collection.get("raw_checksums_sha256", {})),
        }
    )
    manifest["source_snapshots"] = source_snapshots
    code_versions = list(bundles.get("collection_code_versions", []))
    manifest["collection_code_version"] = (
        code_versions[0] if len(code_versions) == 1 else code_versions
    )

    sampling_report = _read_json_mapping(
        root / "data/final/verified_professors.sampling_report.json", [], "sampling report"
    )
    algorithms = dict(manifest.get("algorithms", {}))
    algorithms["sampling"] = sampling_report.get("algorithm_version") or _nested(
        config, "sampling", "algorithm_version"
    )
    algorithms["paper_selection"] = algorithms.get(
        "paper_selection", "representative-paper-selection-v1"
    )
    manifest["algorithms"] = algorithms
    sampling = dict(manifest.get("sampling", {}))
    sampling.update(
        {
            "sampling_seed": sampling_report.get("seed", config.get("random_seed")),
            "sampling_algorithm_version": algorithms["sampling"],
            "achieved_distribution": sampling_report.get("achieved_distribution", {}),
            "excluded_candidates": sampling_report.get("exclusions", {}),
            "exclusion_reason_counts": sampling_report.get("reason_counts", {}),
        }
    )
    manifest["sampling"] = sampling
    collection_checks = collection.get("checks", {})
    bundle_checks = bundles.get("checks", {})
    privacy_checks = public_scan.get("checks", {})
    quality = dict(manifest.get("quality_control", {}))
    quality.update(
        {
            "schema_validation_passed": bool(bundle_checks.get("schema_validation")),
            "unique_professor_ids_passed": bool(
                collection_checks.get("unique_ids") and bundle_checks.get("unique_professor_ids")
            ),
            "paper_counts_passed": bool(collection_checks.get("selection_counts")),
            "focal_paper_counts_passed": bool(collection_checks.get("selection_counts")),
            "passage_counts_passed": False,
            "source_urls_and_dates_passed": bool(bundles.get("retrieval_window_start")),
            "authorship_verification_passed": False,
            "public_identity_scan_passed": bool(privacy_checks.get("public_identity_absence")),
            "secret_scan_passed": bool(privacy_checks.get("secret_absence")),
            "raw_pdf_commit_scan_passed": bool(privacy_checks.get("tracked_pdf_absence")),
            "validation_report_path": "data/final/validation_report.json",
            "final_evidence_packet_ready": False,
        }
    )
    manifest["quality_control"] = quality
    return manifest


def _validate_checkpoints(root: Path, errors: list[str]) -> tuple[dict[str, str], bool]:
    pages_root = root / "data/raw/pages"
    raw_hashes = {
        path.relative_to(root).as_posix(): _file_sha256(path)
        for path in sorted(pages_root.rglob("*.json"))
        if path.is_file()
    }
    checkpoint_paths = sorted((root / "data/raw/progress").glob("*.json"))
    if not checkpoint_paths:
        errors.append("checkpoints: no collection checkpoint files found")
        return raw_hashes, False
    valid = True
    referenced: set[str] = set()
    for path in checkpoint_paths:
        checkpoint = _read_json_mapping(path, errors, "checkpoint")
        if checkpoint.get("checkpoint_version") != "collection-progress-v1":
            errors.append(f"checkpoint {path.name}: unsupported checkpoint version")
            valid = False
        if checkpoint.get("status") not in {"complete", "completed"}:
            errors.append(f"checkpoint {path.name}: status is not complete")
            valid = False
        total = checkpoint.get("total_items")
        completed = checkpoint.get("completed_item_ids")
        if not isinstance(total, int) or not isinstance(completed, list) or len(completed) != total:
            errors.append(f"checkpoint {path.name}: completed item count does not match total")
            valid = False
        if checkpoint.get("current_cursor") is not None:
            errors.append(f"checkpoint {path.name}: terminal cursor is not null")
            valid = False
        for reference in checkpoint.get("raw_pages", []):
            if not isinstance(reference, Mapping):
                errors.append(f"checkpoint {path.name}: malformed raw-page reference")
                valid = False
                continue
            relative_page = _string(reference.get("path"))
            expected = _string(reference.get("checksum"))
            if relative_page is None or expected is None or not _SHA256.fullmatch(expected):
                errors.append(f"checkpoint {path.name}: malformed raw-page checksum reference")
                valid = False
                continue
            full_relative = (Path("data/raw/pages") / relative_page).as_posix()
            referenced.add(full_relative)
            actual = raw_hashes.get(full_relative)
            if actual != expected:
                errors.append(
                    f"checkpoint {path.name}: raw-page checksum mismatch for {relative_page}"
                )
                valid = False
    unreferenced = set(raw_hashes) - referenced
    for path in sorted(unreferenced):
        errors.append(f"raw page is not referenced by a checkpoint: {path}")
        valid = False
    return raw_hashes, valid


def _validate_completeness_markers(
    root: Path,
    sampled_ids: set[str],
    candidate_author_by_professor: Mapping[str, str | None],
    works_by_professor: Mapping[str, Mapping[str, Mapping[str, Any]]],
    raw_hashes: Mapping[str, str],
    errors: list[str],
) -> bool:
    marker_paths = sorted((root / "data/raw/completeness").rglob("*.json"))
    markers: dict[str, Mapping[str, Any]] = {}
    for path in marker_paths:
        marker = _read_json_mapping(path, errors, "completeness marker")
        professor_id = _string(marker.get("professor_id"))
        if professor_id:
            if professor_id in markers:
                errors.append(f"duplicate completeness marker for {professor_id}")
            markers[professor_id] = marker
    valid = True
    known_hashes = set(raw_hashes.values())
    for professor_id in sorted(sampled_ids):
        marker = markers.get(professor_id)
        if marker is None:
            errors.append(f"work history is not complete for {professor_id}: marker missing")
            valid = False
            continue
        if marker.get("collection_complete") is not True:
            errors.append(f"work history is not complete for {professor_id}")
            valid = False
        if marker.get("terminal_cursor") is not None:
            errors.append(f"work history terminal cursor is not null for {professor_id}")
            valid = False
        if marker.get("work_count") != len(works_by_professor.get(professor_id, {})):
            errors.append(f"work history count does not match records for {professor_id}")
            valid = False
        marker_author = _canonical_openalex_id(marker.get("openalex_author_id"), "A")
        if marker_author != candidate_author_by_professor.get(professor_id):
            errors.append(
                f"completeness marker has an invalid candidate-author join for {professor_id}"
            )
            valid = False
        hashes = marker.get("raw_hashes")
        if (
            not isinstance(hashes, list)
            or not hashes
            or any(value not in known_hashes for value in hashes)
        ):
            errors.append(f"completeness marker has unknown raw hashes for {professor_id}")
            valid = False
    return valid


def _validate_deterministic_metadata(
    root: Path,
    config: Mapping[str, Any],
    selected: Sequence[Mapping[str, Any]],
    sampled: Sequence[Mapping[str, Any]],
    sampled_ids: set[str],
    errors: list[str],
) -> bool:
    valid = True
    seed = config.get("random_seed")
    expected_sampling_algorithm = _nested(config, "sampling", "algorithm_version")
    report = _read_json_mapping(
        root / "data/final/verified_professors.sampling_report.json", errors, "sampling report"
    )
    if report.get("seed") != seed:
        errors.append("sampling report seed does not match configuration")
        valid = False
    if report.get("algorithm_version") != expected_sampling_algorithm:
        errors.append("sampling algorithm version does not match configuration")
        valid = False
    if report.get("candidate_pool_version") != config.get("candidate_pool_version"):
        errors.append("sampling candidate-pool version does not match configuration")
        valid = False
    if set(report.get("selected_ids", [])) != sampled_ids:
        errors.append("sampling selected IDs do not match selected-professor table")
        valid = False
    for row in sampled:
        if _integer(row.get("sampling_seed")) != seed:
            errors.append("selected-professor sampling seed does not match configuration")
            valid = False
        if row.get("sampling_algorithm_version") != expected_sampling_algorithm:
            errors.append(
                "selected-professor sampling algorithm version is missing or inconsistent"
            )
            valid = False
    for row in selected:
        if not _truthy(row.get("selected")):
            continue
        selection_seed = _integer(row.get("selection_seed"))
        if selection_seed is not None and selection_seed != seed:
            errors.append("paper-selection seed does not match configuration")
            valid = False
        selection_algorithm = _string(row.get("selection_algorithm_version"))
        if (
            selection_algorithm is not None
            and selection_algorithm != "representative-paper-selection-v1"
        ):
            errors.append("paper-selection algorithm version is missing or inconsistent")
            valid = False
    return valid


def _resolve_schema_path(root: Path, schema_path: str | Path | None) -> Path:
    if schema_path is not None:
        return _resolve_under_root(root, schema_path)
    local = root / "schemas/openalex_profile_bundle.schema.json"
    if local.is_file():
        return local
    return Path(__file__).resolve().parents[2] / "schemas/openalex_profile_bundle.schema.json"


def _resolve_manifest_template(root: Path, template_path: str | Path | None) -> Path:
    if template_path is not None:
        return _resolve_under_root(root, template_path)
    local = root / "data/dataset_manifest.template.yaml"
    if local.is_file():
        return local
    return Path(__file__).resolve().parents[2] / "data/dataset_manifest.template.yaml"


def _read_table(path: Path, errors: list[str], label: str) -> list[dict[str, Any]]:
    if not path.is_file():
        errors.append(f"{label}: required file is missing: {path}")
        return []
    try:
        if path.suffix == ".csv":
            with path.open(encoding="utf-8", newline="") as stream:
                rows = [dict(row) for row in csv.DictReader(stream)]
        elif path.suffix == ".jsonl":
            rows = []
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"line {line_number} is not an object")
                rows.append(value)
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
            rows = value if isinstance(value, list) else [value]
        if not rows:
            errors.append(f"{label}: required table is empty")
        return rows
    except (OSError, UnicodeDecodeError, csv.Error, json.JSONDecodeError, ValueError) as error:
        errors.append(f"{label}: {error}")
        return []


def _read_yaml_mapping(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("document is not a mapping")
        return value
    except (OSError, UnicodeDecodeError, TypeError, yaml.YAMLError) as error:
        errors.append(f"{label}: {error}")
        return {}


def _read_json_mapping(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise TypeError("document is not a mapping")
        return value
    except (OSError, UnicodeDecodeError, TypeError, json.JSONDecodeError) as error:
        errors.append(f"{label}: {error}")
        return {}


def _unique_ids(
    rows: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
    label: str,
    errors: list[str],
    *,
    prefix: str | None = None,
    professor: bool = False,
) -> set[str]:
    identifiers: set[str] = set()
    for index, row in enumerate(rows, start=1):
        raw = next((row.get(key) for key in keys if _string(row.get(key))), None)
        identifier = _string(raw)
        if prefix:
            identifier = _canonical_openalex_id(raw, prefix)
        if professor and (identifier is None or not _PROFESSOR_ID.fullmatch(identifier)):
            identifier = None
        if identifier is None:
            errors.append(f"{label} row {index} has an invalid ID")
            continue
        if identifier in identifiers:
            errors.append(f"duplicate {label} ID {identifier}")
        identifiers.add(identifier)
    return identifiers


def _canonical_openalex_id(value: Any, prefix: str) -> str | None:
    text = _string(value)
    if text is None:
        return None
    identifier = text.rstrip("/").rsplit("/", 1)[-1]
    return (
        identifier if _OPENALEX_ID.fullmatch(identifier) and identifier.startswith(prefix) else None
    )


def _first_id(row: Mapping[str, Any], keys: Sequence[str]) -> str | None:
    return next((_string(row.get(key)) for key in keys if _string(row.get(key))), None)


def _id_list(value: Any, prefix: str) -> list[str]:
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        try:
            parsed = json.loads(stripped)
            values = parsed if isinstance(parsed, list) else [parsed]
        except json.JSONDecodeError:
            values = re.split(r"[|,;]", stripped)
    elif isinstance(value, Sequence):
        values = value
    else:
        return []
    return [identifier for item in values if (identifier := _canonical_openalex_id(item, prefix))]


def _public_files(root: Path, public_paths: Sequence[str | Path] | None) -> list[Path]:
    candidates = (
        [_resolve_under_root(root, value) for value in public_paths]
        if public_paths is not None
        else [root / directory for directory in PUBLIC_DIRECTORIES]
    )
    files: set[Path] = set()
    for candidate in candidates:
        if candidate.is_file() and candidate.suffix.casefold() in TEXT_SUFFIXES:
            files.add(candidate)
        elif candidate.is_dir():
            files.update(
                path
                for path in candidate.rglob("*")
                if path.is_file() and path.suffix.casefold() in TEXT_SUFFIXES
            )
    return sorted(files)


def _private_identity_names(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except (OSError, UnicodeDecodeError, csv.Error):
        return set()
    name_columns = ("display_name", "name", "faculty_name", "professor_name", "full_name")
    return {
        value
        for row in rows
        for column in name_columns
        if (value := _string(row.get(column))) is not None
    }


def _git_tracked_files(root: Path) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    return completed.stdout.splitlines() if completed.returncode == 0 else []


def _resolve_under_root(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def _relative_display(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _nested(value: Mapping[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _normalized_text(value: Any) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(value)).casefold().split())


def _truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().casefold() == "true")


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value.strip()):
        return int(value)
    return None


def _string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
