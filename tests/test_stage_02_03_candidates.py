from __future__ import annotations

import csv
import hashlib
import importlib
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.openalex_client import Page  # noqa: E402


stage_02 = importlib.import_module("02_fetch_author_candidates")
stage_03 = importlib.import_module("03_verify_faculty_status")


def institution(openalex_id: str) -> dict[str, str]:
    return {"institution_id": openalex_id, "openalex_id": openalex_id}


def eligible_author(
    openalex_id: str = "A100000001",
    *,
    display_name: str = "Ada Synthetic",
    institution_id: str = "I100000001",
    works_count: int = 12,
    last_year: int = 2024,
    field: str = "Computer Science",
    domain: str = "Physical Sciences",
) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/{openalex_id}",
        "display_name": display_name,
        "orcid": "https://orcid.org/0000-0001-0000-0001",
        "works_count": works_count,
        "cited_by_count": 345,
        "summary_stats": {"h_index": 7},
        "last_known_institutions": [
            {
                "id": f"https://openalex.org/{institution_id}",
                "display_name": "Synthetic Institute",
                "country_code": "CA",
                "type": "education",
            }
        ],
        "affiliations": [],
        "topics": [
            {
                "id": "https://openalex.org/T100000001",
                "display_name": "Synthetic Research",
                "count": 9,
                "subfield": {"id": "1702", "display_name": "Artificial Intelligence"},
                "field": {"id": "17", "display_name": field},
                "domain": {"id": "3", "display_name": domain},
            }
        ],
        "counts_by_year": [
            {"year": last_year, "works_count": 2, "cited_by_count": 30},
            {"year": 2013, "works_count": 1, "cited_by_count": 4},
        ],
    }


class FixtureClient:
    def __init__(self, authors_by_institution: Mapping[str, list[dict[str, Any]]]) -> None:
        self.authors_by_institution = {
            key: deepcopy(value) for key, value in authors_by_institution.items()
        }
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def iter_pages(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        start_cursor: str = "*",
    ) -> Iterator[Page]:
        copied_params = dict(params)
        self.calls.append((endpoint, copied_params, start_cursor))
        filter_value = str(copied_params["filter"])
        institution_id = filter_value.rsplit(":", maxsplit=1)[-1]
        request_hash = hashlib.sha256(
            f"{endpoint}|{filter_value}|{start_cursor}".encode()
        ).hexdigest()
        yield Page(
            results=deepcopy(self.authors_by_institution[institution_id]),
            meta={"next_cursor": None},
            cursor_in=start_cursor,
            cursor_out=None,
            request={
                "provider": "openalex",
                "endpoint": endpoint,
                "params": {"cursor": start_cursor, **copied_params},
            },
            request_hash=request_hash,
            rate_limit={"credits_remaining": 99},
            cache_status="fixture",
        )


def test_author_found_at_two_institutions_is_one_candidate(tmp_path: Path) -> None:
    author = eligible_author()
    client = FixtureClient(
        {
            "I100000001": [author],
            "I100000002": [deepcopy(author)],
        }
    )

    result = stage_02.collect_candidates(
        [institution("I100000001"), institution("I100000002")],
        client,
        tmp_path,
        limit=10,
    )

    assert len(result.rows) == 1
    assert result.rows[0]["discovery_institution_ids"] == "I100000001|I100000002"
    assert result.rows[0]["faculty_status_verified"] == "false"
    assert result.rows[0]["quality_status"] == "needs_enrichment"
    assert [call[:2] for call in client.calls] == [
        ("authors", {"filter": "last_known_institutions.id:I100000001"}),
        ("authors", {"filter": "last_known_institutions.id:I100000002"}),
    ]
    assert len(list((tmp_path / "data/raw/pages").rglob("*.json"))) == 2

    with result.output_path.open(encoding="utf-8", newline="") as stream:
        written = list(csv.DictReader(stream))
    assert written == result.rows


def test_candidate_limit_is_applied_after_deduplication(tmp_path: Path) -> None:
    duplicate = eligible_author("A100000001")
    second = eligible_author("A100000002", display_name="Grace Synthetic")
    client = FixtureClient(
        {
            "I100000001": [duplicate],
            "I100000002": [deepcopy(duplicate), second],
        }
    )

    result = stage_02.collect_candidates(
        [institution("I100000001"), institution("I100000002")],
        client,
        tmp_path,
        limit=1,
    )

    assert [row["openalex_author_id"] for row in result.rows] == ["A100000001"]
    assert result.rows[0]["discovery_institution_ids"] == "I100000001|I100000002"
    assert result.summary["duplicates removed"] == 1
    assert result.summary["eligible candidates omitted by limit"] == 1


def test_candidate_screening_uses_only_openalex_observable_signals(tmp_path: Path) -> None:
    named_student = eligible_author(display_name="Definitely A Student")
    too_few_works = eligible_author("A100000002", works_count=7)
    stale = eligible_author("A100000003", last_year=2020)
    client = FixtureClient({"I100000001": [named_student, too_few_works, stale]})

    result = stage_02.collect_candidates([institution("I100000001")], client, tmp_path, limit=10)

    assert [row["openalex_author_id"] for row in result.rows] == ["A100000001"]
    assert result.rows[0]["candidate_status"] == "eligible"
    assert result.rows[0]["faculty_status_verified"] == "false"
    assert result.summary["screened out candidates"] == 2


def test_candidate_collection_enforces_safe_limit_before_creating_job(tmp_path: Path) -> None:
    client = FixtureClient({"I100000001": []})

    with pytest.raises(ValueError, match="--full-run"):
        stage_02.collect_candidates([institution("I100000001")], client, tmp_path, limit=11)

    assert client.calls == []
    assert not (tmp_path / "data/raw/progress").exists()


@pytest.fixture
def candidate_rows() -> list[dict[str, Any]]:
    return [
        {
            "openalex_author_id": "A100000002",
            "display_name": "Grace Synthetic",
            "orcid": "",
            "last_known_institution": "Synthetic Institute",
            "discovery_institution_ids": "I100000002",
            "works_count": "14",
            "cited_by_count": "200",
            "h_index": "6",
            "first_publication_year": "2014",
            "last_publication_year": "2025",
            "primary_domain": "Physical Sciences",
            "primary_field": "Computer Science",
            "primary_subfield": "Artificial Intelligence",
            "candidate_status": "eligible",
            "faculty_status_verified": "false",
            "quality_status": "needs_enrichment",
        },
        {
            "openalex_author_id": "A100000001",
            "display_name": "Ada Synthetic",
            "orcid": "https://orcid.org/0000-0001-0000-0001",
            "last_known_institution": "Another Synthetic Institute",
            "discovery_institution_ids": "I100000001",
            "works_count": "12",
            "cited_by_count": "345",
            "h_index": "7",
            "first_publication_year": "2013",
            "last_publication_year": "2024",
            "primary_domain": "Physical Sciences",
            "primary_field": "Computer Science",
            "primary_subfield": "Artificial Intelligence",
            "candidate_status": "eligible",
            "faculty_status_verified": "false",
            "quality_status": "needs_enrichment",
        },
    ]


def test_queue_uses_stable_anonymous_ids(candidate_rows: list[dict[str, Any]]) -> None:
    first = stage_03.build_enrichment_queue(candidate_rows, "candidate-pool-v1")
    second = stage_03.build_enrichment_queue(list(reversed(candidate_rows)), "candidate-pool-v1")

    first_ids = {row["openalex_author_id"]: row["professor_id"] for row in first}
    second_ids = {row["openalex_author_id"]: row["professor_id"] for row in second}
    assert first_ids == second_ids
    assert set(first_ids.values()) == {"CS-001", "CS-002"}
    assert all(row["quality_status"] == "needs_enrichment" for row in first)
    assert all(row["faculty_status_verified"] == "false" for row in first)


def test_public_enrichment_queue_omits_real_names(
    candidate_rows: list[dict[str, Any]],
) -> None:
    queue = stage_03.build_enrichment_queue(candidate_rows, "candidate-pool-v1")

    assert all("display_name" not in row for row in queue)
    serialized = json.dumps(queue)
    assert "Ada Synthetic" not in serialized
    assert "Grace Synthetic" not in serialized


def test_real_name_mapping_is_written_only_to_private_identity_map(
    tmp_path: Path, candidate_rows: list[dict[str, Any]]
) -> None:
    initialize_git_repository(tmp_path, "data/private/*\n")
    output = tmp_path / "data/interim/faculty_identity_enrichment_queue.csv"
    identity_map = tmp_path / "data/private/professor_identity_map.csv"

    queue = stage_03.write_enrichment_queue(
        candidate_rows,
        "candidate-pool-v1",
        output,
        identity_map,
        private_dir=tmp_path / "data/private",
        repository_root=tmp_path,
    )

    public_text = output.read_text(encoding="utf-8")
    private_text = identity_map.read_text(encoding="utf-8")
    assert [row["professor_id"] for row in queue]
    assert "display_name" not in public_text
    assert "Ada Synthetic" not in public_text
    assert "Grace Synthetic" not in public_text
    assert "display_name" in private_text
    assert "Ada Synthetic" in private_text
    assert "Grace Synthetic" in private_text


def initialize_git_repository(root: Path, ignore_rules: str) -> None:
    subprocess.run(
        ["git", "init", "--quiet", str(root)],
        check=True,
        capture_output=True,
        text=True,
    )
    (root / ".gitignore").write_text(ignore_rules, encoding="utf-8")


def test_enrichment_destinations_must_differ_before_writing(
    tmp_path: Path, candidate_rows: list[dict[str, Any]]
) -> None:
    initialize_git_repository(tmp_path, "data/private/*\n")
    shared = tmp_path / "data/private/professor_identity_map.csv"

    with pytest.raises(ValueError, match="must differ"):
        stage_03.write_enrichment_queue(
            candidate_rows,
            "candidate-pool-v1",
            shared,
            shared,
            private_dir=tmp_path / "data/private",
            repository_root=tmp_path,
        )

    assert not shared.exists()


def test_identity_map_must_be_beneath_configured_private_directory(
    tmp_path: Path, candidate_rows: list[dict[str, Any]]
) -> None:
    initialize_git_repository(tmp_path, "data/private/*\n")
    output = tmp_path / "data/interim/faculty_identity_enrichment_queue.csv"
    identity_map = tmp_path / "data/public/professor_identity_map.csv"

    with pytest.raises(ValueError, match="beneath configured private directory"):
        stage_03.write_enrichment_queue(
            candidate_rows,
            "candidate-pool-v1",
            output,
            identity_map,
            private_dir=tmp_path / "data/private",
            repository_root=tmp_path,
        )

    assert not output.exists()
    assert not identity_map.exists()


def test_identity_map_must_be_git_ignored_before_writing(
    tmp_path: Path, candidate_rows: list[dict[str, Any]]
) -> None:
    initialize_git_repository(tmp_path, "data/other-private/*\n")
    output = tmp_path / "data/interim/faculty_identity_enrichment_queue.csv"
    identity_map = tmp_path / "data/private/professor_identity_map.csv"

    with pytest.raises(ValueError, match="must be Git-ignored"):
        stage_03.write_enrichment_queue(
            candidate_rows,
            "candidate-pool-v1",
            output,
            identity_map,
            private_dir=tmp_path / "data/private",
            repository_root=tmp_path,
        )

    assert not output.exists()
    assert not identity_map.exists()


def test_tracked_identity_map_is_rejected_before_public_write(
    tmp_path: Path, candidate_rows: list[dict[str, Any]]
) -> None:
    initialize_git_repository(tmp_path, "data/private/*\n")
    output = tmp_path / "data/interim/faculty_identity_enrichment_queue.csv"
    identity_map = tmp_path / "data/private/professor_identity_map.csv"
    identity_map.parent.mkdir(parents=True)
    identity_map.write_text("preexisting tracked secret\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "--force", str(identity_map)],
        check=True,
        capture_output=True,
        text=True,
    )

    with pytest.raises(ValueError, match="must not be tracked"):
        stage_03.write_enrichment_queue(
            candidate_rows,
            "candidate-pool-v1",
            output,
            identity_map,
            private_dir=tmp_path / "data/private",
            repository_root=tmp_path,
            force=True,
        )

    assert not output.exists()
    assert identity_map.read_text(encoding="utf-8") == "preexisting tracked secret\n"
