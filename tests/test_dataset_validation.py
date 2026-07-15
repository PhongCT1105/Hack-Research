from __future__ import annotations

import csv
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.bundles import build_openalex_bundle  # noqa: E402
from lib.validation import (  # noqa: E402
    scan_public_artifacts,
    validate_openalex_collection,
    validate_provisional_bundles,
)


stage_12 = importlib.import_module("12_validate_dataset")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture
def complete_fixture_dataset(tmp_path: Path) -> Path:
    config = yaml.safe_load((ROOT / "config/dataset.yaml").read_text(encoding="utf-8"))
    config_path = tmp_path / "config/dataset.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    _write_csv(
        tmp_path / "data/interim/institutions.csv",
        [
            {
                "institution_id": "I100000001",
                "openalex_id": "I100000001",
                "country_code": "US",
            }
        ],
    )
    _write_csv(
        tmp_path / "data/interim/author_candidates.csv",
        [
            {
                "openalex_author_id": "A100000001",
                "discovery_institution_ids": json.dumps(["I100000001"]),
                "candidate_status": "eligible",
            }
        ],
    )
    _write_csv(
        tmp_path / "data/interim/faculty_identity_enrichment_queue.csv",
        [
            {
                "professor_id": "MOCK-01",
                "openalex_author_id": "A100000001",
                "discovery_institution_ids": json.dumps(["I100000001"]),
                "faculty_status_verified": "false",
                "quality_status": "needs_enrichment",
            }
        ],
    )

    works = [
        {
            "schema_version": "1.0.0",
            "professor_id": "MOCK-01",
            "openalex_author_id": "A100000001",
            "paper_id": f"W10000000{index}",
            "openalex_work_id": f"W10000000{index}",
            "title": f"Synthetic paper {index}",
            "publication_year": 2017 + index,
        }
        for index in range(1, 9)
    ]
    works_path = tmp_path / "data/raw/author_works.jsonl"
    works_path.parent.mkdir(parents=True, exist_ok=True)
    works_path.write_text(
        "".join(json.dumps(work, sort_keys=True) + "\n" for work in works),
        encoding="utf-8",
    )

    raw_page = tmp_path / "data/raw/pages/04_fetch_author_works/job/MOCK-01/page.json"
    _write_json(
        raw_page,
        {
            "envelope_version": "openalex-raw-envelope-v1",
            "provider": "openalex",
            "job_id": "job",
            "item_id": "MOCK-01",
            "request": {"endpoint": "works", "cursor": "*"},
            "request_hash": "1" * 64,
            "response_checksum": "2" * 64,
            "cursor_in": "*",
            "cursor_out": None,
            "response": {"results": [], "meta": {"next_cursor": None}},
        },
    )
    raw_hash = hashlib.sha256(raw_page.read_bytes()).hexdigest()
    _write_json(
        tmp_path / "data/raw/progress/abc123.json",
        {
            "checkpoint_version": "collection-progress-v1",
            "job_id": "abc123",
            "stage": "04_fetch_author_works",
            "status": "complete",
            "total_items": 1,
            "completed_item_ids": ["MOCK-01"],
            "current_cursor": None,
            "raw_pages": [
                {
                    "path": "04_fetch_author_works/job/MOCK-01/page.json",
                    "checksum": raw_hash,
                    "item_id": "MOCK-01",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "data/raw/completeness/04_fetch_author_works/job/MOCK-01.json",
        {
            "professor_id": "MOCK-01",
            "openalex_author_id": "A100000001",
            "terminal_cursor": None,
            "page_count": 1,
            "work_count": 8,
            "raw_hashes": [raw_hash],
            "collection_complete": True,
        },
    )

    selected_rows = []
    for index, work in enumerate(works, start=1):
        selected_rows.append(
            {
                "professor_id": "MOCK-01",
                "paper_id": work["paper_id"],
                "openalex_work_id": work["openalex_work_id"],
                "title": work["title"],
                "selected": "true",
                "focal": "true" if index <= 2 else "false",
                "selection_reason": (
                    "recent"
                    if index <= 3
                    else "influential"
                    if index <= 5
                    else "diversifying"
                    if index <= 7
                    else "random"
                ),
            }
        )
    _write_csv(tmp_path / "data/interim/candidate_papers.csv", selected_rows)
    _write_csv(
        tmp_path / "data/final/verified_professors.csv",
        [
            {
                "professor_id": "MOCK-01",
                "openalex_author_id": "A100000001",
                "sampling_selected": "true",
                "sampling_seed": "42",
                "sampling_algorithm_version": "constrained-margins-v1",
                "sampling_status": "provisional_openalex_sample",
            }
        ],
    )
    _write_json(
        tmp_path / "data/final/verified_professors.sampling_report.json",
        {
            "algorithm_version": "constrained-margins-v1",
            "candidate_pool_version": "candidate-pool-v1",
            "seed": 42,
            "selected_ids": ["MOCK-01"],
            "achieved_distribution": {"domain": {"computer_science_engineering": 1}},
            "exclusions": {},
            "reason_counts": {},
        },
    )

    bundle = build_openalex_bundle(
        {
            "schema_version": "1.0.0",
            "dataset_version": "benchmark-v1",
            "candidate_pool_version": "candidate-pool-v1",
            "bundle_version": "openalex-provisional-bundle-v1",
            "professor_id": "MOCK-01",
            "openalex_author_id": "A100000001",
            "institutions": [{"openalex_id": "I100000001", "country_code": "US"}],
            "career_stage": "mid",
            "visibility": {"score": 0.5, "components": {}},
            "research_breadth": {"score": 0.5, "components": {}},
            "topic_coherence_aid": {"score": 0.5, "components": {}},
            "method_diversity": {"score": 0.5, "components": {}},
            "paper_complexity": {"score": 0.5, "components": {}},
            "synthesis_difficulty": {"score": 0.5, "components": {}},
            "openalex_consistency": {
                "status": "openalex_consistent",
                "issue_codes": [],
                "scope": "within_openalex",
                "externally_verified": False,
            },
        },
        [
            {
                **work,
                "selected": True,
                "focal": index <= 2,
                "selection_reason": "recent" if index <= 3 else "diversifying",
            }
            for index, work in enumerate(works, start=1)
        ],
        ["W100000001", "W100000002"],
        {
            "raw_source_hashes": [raw_hash],
            "openalex_urls": [
                "https://openalex.org/A100000001",
                *[f"https://openalex.org/W10000000{index}" for index in range(1, 9)],
            ],
            "retrieved_at": "2026-07-14T12:00:00Z",
            "collection_code_version": "collection-code-v1",
        },
    )
    _write_json(tmp_path / "data/final/openalex_profile_bundles/MOCK-01.json", bundle)
    _write_csv(
        tmp_path / "data/private/professor_identity_map.csv",
        [
            {
                "professor_id": "MOCK-01",
                "openalex_author_id": "A100000001",
                "display_name": "Ada Synthetic",
            }
        ],
    )
    return tmp_path


def test_valid_openalex_collection_is_explicitly_not_final(
    complete_fixture_dataset: Path,
) -> None:
    report = stage_12.validate_dataset(complete_fixture_dataset)

    assert report["openalex_collection_valid"] is True
    assert report["provisional_bundle_valid"] is True
    assert report["final_evidence_packet_ready"] is False
    assert "faculty_status_unverified" in report["final_blockers"]
    assert report["manifest"]["template_only"] is False
    assert report["manifest"]["counts"]["selected_professors"] == 1
    assert report["manifest"]["counts"]["selected_papers"] == 8
    assert report["manifest"]["counts"]["focal_papers"] == 2
    assert report["manifest"]["validation"]["final_evidence_packet_ready"] is False


def test_collection_validation_rejects_checksum_join_and_completeness_failures(
    complete_fixture_dataset: Path,
) -> None:
    raw_page = next((complete_fixture_dataset / "data/raw/pages").rglob("*.json"))
    raw_page.write_text("{}\n", encoding="utf-8")
    works_path = complete_fixture_dataset / "data/raw/author_works.jsonl"
    works = [json.loads(line) for line in works_path.read_text(encoding="utf-8").splitlines()]
    works[0]["professor_id"] = "UNKNOWN-99"
    works_path.write_text("".join(json.dumps(row) + "\n" for row in works), encoding="utf-8")
    marker = next((complete_fixture_dataset / "data/raw/completeness").rglob("*.json"))
    marker_value = json.loads(marker.read_text(encoding="utf-8"))
    marker_value["collection_complete"] = False
    _write_json(marker, marker_value)

    result = validate_openalex_collection(complete_fixture_dataset)

    assert result["valid"] is False
    assert any("checksum" in error for error in result["errors"])
    assert any("unknown professor" in error for error in result["errors"])
    assert any("not complete" in error for error in result["errors"])


def test_bundle_validation_rejects_wrong_schema_counts_tasks_and_joins(
    complete_fixture_dataset: Path,
) -> None:
    bundle_path = next(
        (complete_fixture_dataset / "data/final/openalex_profile_bundles").glob("*.json")
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["schema_version"] = "9.9.9"
    bundle["selected_papers"] = bundle["selected_papers"][:-1]
    bundle["enrichment_tasks"] = bundle["enrichment_tasks"][:-1]
    _write_json(bundle_path, bundle)

    result = validate_provisional_bundles(complete_fixture_dataset)

    assert result["valid"] is False
    assert any("MOCK-01" in error for error in result["errors"])


def test_public_scan_rejects_names_secrets_and_tracked_pdfs(
    complete_fixture_dataset: Path,
) -> None:
    leaked = complete_fixture_dataset / "data/final/public.json"
    leaked.write_text(
        '{"person": "Ada Synthetic", "token": "OPENALEX_API_KEY=abc123secret"}\n',
        encoding="utf-8",
    )

    result = scan_public_artifacts(
        complete_fixture_dataset,
        tracked_files=["data/final/public.json", "data/final/publisher-copy.pdf"],
    )

    assert result["valid"] is False
    assert any("private identity name" in error for error in result["errors"])
    assert any("secret" in error for error in result["errors"])
    assert any("tracked PDF" in error for error in result["errors"])


def test_manifest_is_deterministic_and_retains_strict_false_flags(
    complete_fixture_dataset: Path,
) -> None:
    first = stage_12.validate_dataset(complete_fixture_dataset)
    second = stage_12.validate_dataset(complete_fixture_dataset)

    assert first["manifest"] == second["manifest"]
    manifest = first["manifest"]
    raw_files = manifest["source_snapshots"]["raw_files"]
    assert raw_files == sorted(raw_files)
    assert set(manifest["source_snapshots"]["raw_checksums_sha256"]) == set(raw_files)
    assert manifest["algorithms"]["sampling"] == "constrained-margins-v1"
    assert manifest["quality_control"]["schema_validation_passed"] is True
    assert manifest["quality_control"]["authorship_verification_passed"] is False
    assert manifest["quality_control"]["passage_counts_passed"] is False


def test_missing_required_file_is_reported_without_crashing(
    complete_fixture_dataset: Path,
) -> None:
    (complete_fixture_dataset / "config/dataset.yaml").unlink()

    report = stage_12.validate_dataset(complete_fixture_dataset)

    assert report["openalex_collection_valid"] is False
    assert report["final_evidence_packet_ready"] is False
    assert any("configuration" in error for error in report["errors"])


def test_manifest_validity_includes_public_scan_failures(
    complete_fixture_dataset: Path,
) -> None:
    (complete_fixture_dataset / "data/final/leak.txt").write_text(
        "OPENALEX_API_KEY=abc123secret\n", encoding="utf-8"
    )

    report = stage_12.validate_dataset(complete_fixture_dataset)

    assert report["openalex_collection_valid"] is False
    assert report["provisional_bundle_valid"] is False
    assert report["manifest"]["validation"]["openalex_collection_valid"] is False
    assert report["manifest"]["validation"]["provisional_bundle_valid"] is False


def test_report_never_promotes_final_readiness_from_provisional_claim(
    complete_fixture_dataset: Path,
) -> None:
    bundle_path = next(
        (complete_fixture_dataset / "data/final/openalex_profile_bundles").glob("*.json")
    )
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    claimed = deepcopy(bundle)
    claimed["final_evidence_packet_ready"] = True
    _write_json(bundle_path, claimed)

    report = stage_12.validate_dataset(complete_fixture_dataset)

    assert report["provisional_bundle_valid"] is False
    assert report["final_evidence_packet_ready"] is False
