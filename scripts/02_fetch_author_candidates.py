#!/usr/bin/env python3
"""Collect deduplicated OpenAlex author candidates from reviewed institutions."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from _dataset_cli import (
    StageSpec,
    build_parser,
    enforce_author_limit,
    handle_progress_action,
    stage_plan,
)
from lib.config import DatasetConfig
from lib.io import atomic_write_csv, atomic_write_json, read_csv
from lib.normalization import (
    AUTHOR_CANDIDATE_CSV_COLUMNS,
    author_candidate_status,
    canonical_openalex_id,
    normalize_author,
)
from lib.openalex_client import OpenAlexClient, UrllibTransport
from lib.progress import ProgressStore, canonical_json, make_job_id
from lib.runner import CollectionJob, PageClient, RawPageStore


STAGE = "02_fetch_author_candidates"
CLIENT_VERSION = "openalex-client-v1"
DISCOVERY_INSTITUTIONS_COLUMN = "discovery_institution_ids"
AUTHOR_OUTPUT_COLUMNS = (
    *AUTHOR_CANDIDATE_CSV_COLUMNS,
    DISCOVERY_INSTITUTIONS_COLUMN,
    "faculty_status_verified",
    "quality_status",
)
SPEC = StageSpec(
    2,
    "fetch_author_candidates",
    __doc__ or "Collect OpenAlex author candidates",
    "data/interim/institutions.csv",
    "data/interim/author_candidates.csv",
    "openalex",
    True,
    implemented_locally=True,
)


@dataclass(frozen=True)
class CandidateCollectionResult:
    """Materialized Stage 2 outputs and their stable collection identity."""

    rows: list[dict[str, str]]
    summary: dict[str, Any]
    job_id: str
    output_path: Path
    summary_path: Path


def collect_candidates(
    institutions: Sequence[Mapping[str, Any]],
    client: PageClient,
    workspace_root: str | Path,
    *,
    limit: int | None = None,
    full_run: bool = False,
    config: DatasetConfig | None = None,
    output_path: str | Path | None = None,
    raw_dir: str | Path | None = None,
    state_dir: str | Path | None = None,
    seed: int | None = None,
    resume: bool = False,
    job_id: str | None = None,
    force: bool = False,
    original_command: str = "python scripts/02_fetch_author_candidates.py",
) -> CandidateCollectionResult:
    """Collect, checkpoint, deduplicate, screen, and publish author candidates."""

    root = Path(workspace_root)
    resolved_config = config or DatasetConfig.load(
        Path(__file__).resolve().parents[1] / "config/dataset.yaml"
    )
    resolved_limit = enforce_author_limit(limit, full_run, resolved_config.safe_author_limit)
    resolved_seed = resolved_config.random_seed if seed is None else seed
    items = _institution_items(institutions)
    input_digest = hashlib.sha256(canonical_json(items).encode("utf-8")).hexdigest()
    setup = {
        "endpoint": "authors",
        "institution_ids": [item["provider_id"] for item in items],
        "dataset_version": resolved_config.dataset_version,
        "candidate_pool_version": resolved_config.candidate_pool_version,
        "limit": resolved_limit,
        "seed": resolved_seed,
    }
    calculated_job_id = make_job_id(STAGE, setup, input_digest)
    resolved_job_id = job_id or calculated_job_id

    paths = resolved_config.raw.get("paths", {})
    configured_raw = paths.get("raw", "data/raw") if isinstance(paths, Mapping) else "data/raw"
    configured_interim = (
        paths.get("interim", "data/interim") if isinstance(paths, Mapping) else "data/interim"
    )
    configured_progress = (
        paths.get("progress", Path(configured_raw) / "progress")
        if isinstance(paths, Mapping)
        else Path(configured_raw) / "progress"
    )
    raw_root = _resolve_path(root, raw_dir or configured_raw)
    progress_root = _resolve_path(root, state_dir or configured_progress)
    destination = _resolve_path(
        root, output_path or (Path(configured_interim) / "author_candidates.csv")
    )
    summary_path = destination.with_name(f"{destination.stem}_summary.json")

    raw_page_store = RawPageStore(
        raw_root / "pages",
        stage=STAGE,
        job_id=resolved_job_id,
        envelope_version=resolved_config.raw_envelope_version,
        client_version=CLIENT_VERSION,
    )
    job = CollectionJob.create_or_resume(
        client=client,
        progress_store=ProgressStore(progress_root),
        raw_page_store=raw_page_store,
        stage=STAGE,
        setup=setup,
        input_checksum=input_digest,
        items=items,
        original_command=original_command,
        output_path=str(destination),
        resume=resume,
        job_id=resolved_job_id,
    )
    job.collect_items(items, _endpoint_for_institution)

    all_rows, counts = _materialize_rows(job, items, resolved_config)
    rows = all_rows[:resolved_limit]
    summary = {
        "job_id": resolved_job_id,
        "institution ids": [item["provider_id"] for item in items],
        "records fetched": int(job.progress.get("records_written", 0)),
        "valid records": counts["valid"],
        "invalid records skipped": counts["invalid"],
        "duplicates removed": counts["valid"] - counts["distinct"],
        "screened out candidates": counts["screened_out"],
        "eligible candidates omitted by limit": max(len(all_rows) - len(rows), 0),
        "candidate limit": resolved_limit,
        "candidates collected": len(rows),
    }
    atomic_write_csv(destination, rows, fieldnames=AUTHOR_OUTPUT_COLUMNS, force=force)
    atomic_write_json(summary_path, summary, force=force)
    return CandidateCollectionResult(
        rows=rows,
        summary=summary,
        job_id=resolved_job_id,
        output_path=destination,
        summary_path=summary_path,
    )


def _resolve_path(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def _canonical_id(value: Any, prefix: str) -> str | None:
    try:
        canonical = canonical_openalex_id(value)
    except (TypeError, ValueError):
        return None
    if canonical is None or re.fullmatch(rf"{prefix}\d+", canonical) is None:
        return None
    return canonical


def _institution_items(
    institutions: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    institution_ids: set[str] = set()
    for institution in institutions:
        if not isinstance(institution, Mapping):
            raise ValueError("institution rows must be mappings")
        value = institution.get("openalex_id") or institution.get("institution_id")
        institution_id = _canonical_id(value, "I")
        if institution_id is None:
            raise ValueError(f"invalid OpenAlex institution ID: {value!r}")
        institution_ids.add(institution_id)
    if not institution_ids:
        raise ValueError("at least one institution is required")
    return [
        {
            "item_type": "institution",
            "item_id": institution_id,
            "provider_id": institution_id,
        }
        for institution_id in sorted(institution_ids)
    ]


def _endpoint_for_institution(
    item: Mapping[str, str],
) -> tuple[str, Mapping[str, Any]]:
    return "authors", {"filter": f"last_known_institutions.id:{item['provider_id']}"}


def _materialize_rows(
    job: CollectionJob,
    items: Sequence[Mapping[str, str]],
    config: DatasetConfig,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    institutions_by_item = {item["item_id"]: item["provider_id"] for item in items}
    records: dict[str, dict[str, Any]] = {}
    discoveries: dict[str, set[str]] = {}
    valid_records = 0
    invalid_records = 0

    for reference in job.progress.get("raw_pages", []):
        envelope_path = job.raw_page_store.root_dir / str(reference["path"])
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        results = envelope.get("response", {}).get("results", [])
        institution_id = institutions_by_item[str(reference["item_id"])]
        for raw in results:
            if not isinstance(raw, Mapping):
                invalid_records += 1
                continue
            author_id = _canonical_id(raw.get("id"), "A")
            if author_id is None:
                invalid_records += 1
                continue
            valid_records += 1
            if author_id not in records:
                normalized = normalize_author(raw)
                candidate_pool = config.raw.get("candidate_pool", {})
                settings = candidate_pool if isinstance(candidate_pool, Mapping) else {}
                normalized["candidate_status"] = author_candidate_status(
                    normalized,
                    minimum_works=int(settings.get("minimum_works", 8)),
                    recent_activity_year=config.recent_activity_year,
                    require_institution=bool(settings.get("require_valid_institution", True)),
                    require_topics=bool(settings.get("require_usable_topics", True)),
                )
                records[author_id] = normalized
            discoveries.setdefault(author_id, set()).add(institution_id)

    rows: list[dict[str, str]] = []
    screened_out = 0
    for author_id in sorted(records):
        normalized = records[author_id]
        if normalized.get("candidate_status") != "eligible":
            screened_out += 1
            continue
        row = {
            column: _csv_scalar(normalized.get(column)) for column in AUTHOR_CANDIDATE_CSV_COLUMNS
        }
        row[DISCOVERY_INSTITUTIONS_COLUMN] = "|".join(sorted(discoveries[author_id]))
        row["faculty_status_verified"] = "false"
        row["quality_status"] = "needs_enrichment"
        rows.append(row)
    return rows, {
        "valid": valid_records,
        "invalid": invalid_records,
        "distinct": len(records),
        "screened_out": screened_out,
    }


def _csv_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def dry_run_plan(config: DatasetConfig, arguments: Any) -> dict[str, Any]:
    plan = stage_plan(SPEC, arguments, config.raw)
    if arguments.input and Path(arguments.input).is_file():
        items = _institution_items(read_csv(arguments.input))
        plan["institution_ids"] = [item["provider_id"] for item in items]
        plan["estimated_jobs"] = len(items)
    return plan


def _option_supplied(argv: Sequence[str], option: str) -> bool:
    return any(argument == option or argument.startswith(f"{option}=") for argument in argv)


def _resolve_stage_paths(arguments: Any, config: DatasetConfig, argv: Sequence[str]) -> None:
    paths = config.raw.get("paths", {})
    if not isinstance(paths, Mapping):
        return
    if not _option_supplied(argv, "--output"):
        arguments.output = str(Path(paths.get("interim", "data/interim")) / "author_candidates.csv")
    if not _option_supplied(argv, "--state-dir"):
        arguments.state_dir = str(paths.get("progress", "data/raw/progress"))


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(SPEC)
    arguments = parser.parse_args(raw_argv)
    try:
        config = DatasetConfig.load(arguments.config)
        _resolve_stage_paths(arguments, config, raw_argv)
        progress_result = handle_progress_action(arguments, parser)
        if progress_result is not None:
            return progress_result
        arguments.limit = enforce_author_limit(
            arguments.limit, arguments.full_run, config.safe_author_limit
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))

    if arguments.dry_run:
        print(json.dumps(dry_run_plan(config, arguments), indent=2, sort_keys=True))
        return 0
    if arguments.restart:
        parser.error(
            "--restart is not yet supported for Stage 2; use a changed setup or output path"
        )

    root = Path.cwd()
    try:
        institutions = read_csv(arguments.input)
        client = OpenAlexClient(config.openalex, UrllibTransport(), arguments.cache_dir)
        collect_candidates(
            institutions,
            client,
            root,
            limit=arguments.limit,
            full_run=arguments.full_run,
            config=config,
            output_path=arguments.output,
            raw_dir=config.raw.get("paths", {}).get("raw", "data/raw"),
            state_dir=arguments.state_dir,
            seed=arguments.seed,
            resume=arguments.resume,
            job_id=arguments.job_id,
            force=arguments.force,
            original_command=shlex.join([sys.executable, __file__, *raw_argv]),
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
