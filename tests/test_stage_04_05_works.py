from __future__ import annotations

import hashlib
import importlib
import json
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.openalex_client import Page, RateLimitExhausted  # noqa: E402
from lib.runner import CollectionPaused  # noqa: E402


stage_04 = importlib.import_module("04_fetch_author_works")
stage_05 = importlib.import_module("05_reconstruct_abstracts")


def candidate(
    professor_id: str = "MOCK-01", openalex_author_id: str = "A100000001"
) -> dict[str, str]:
    return {
        "professor_id": professor_id,
        "openalex_author_id": f"https://openalex.org/{openalex_author_id}",
        "faculty_status_verified": "true",
    }


def work(
    openalex_id: str,
    *,
    referenced_works: list[str] | None = None,
    abstract_inverted_index: Mapping[str, list[int]] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/{openalex_id}",
        "doi": f"https://doi.org/10.0000/{openalex_id.lower()}",
        "title": f"Synthetic work {openalex_id}",
        "publication_year": 2025,
        "publication_date": "2025-01-01",
        "type": "article",
        "type_crossref": "journal-article",
        "language": "en",
        "primary_location": {
            "source": {
                "id": "https://openalex.org/S100000001",
                "display_name": "Synthetic Journal",
            }
        },
        "locations": [],
        "best_oa_location": {"landing_page_url": "https://example.invalid/work"},
        "open_access": {"is_oa": True, "oa_status": "gold"},
        "authorships": [
            {
                "author_position": "first",
                "author": {
                    "id": "https://openalex.org/A100000001",
                    "display_name": "Ada Synthetic",
                },
                "institutions": [
                    {
                        "id": "https://openalex.org/I100000001",
                        "display_name": "Synthetic Institute",
                    }
                ],
            }
        ],
        "abstract_inverted_index": deepcopy(abstract_inverted_index),
        "topics": [],
        "primary_topic": None,
        "keywords": [],
        "concepts": [],
        "mesh": [],
        "cited_by_count": 4,
        "referenced_works": [f"https://openalex.org/{value}" for value in (referenced_works or [])],
        "related_works": [],
        "counts_by_year": [],
        "is_retracted": False,
        "is_paratext": False,
    }


@dataclass(frozen=True)
class Call:
    endpoint: str
    params: dict[str, Any]
    start_cursor: str


def page(results: list[dict[str, Any]], cursor_in: str, cursor_out: str | None) -> Page:
    request_hash = hashlib.sha256(f"works|{cursor_in}|{cursor_out}".encode("utf-8")).hexdigest()
    return Page(
        results=deepcopy(results),
        meta={"next_cursor": cursor_out},
        cursor_in=cursor_in,
        cursor_out=cursor_out,
        request={
            "provider": "openalex",
            "endpoint": "works",
            "params": {"cursor": cursor_in},
        },
        request_hash=request_hash,
        rate_limit={"credits_remaining": 99},
        cache_status="fixture",
    )


class WorksClient:
    def __init__(self, pages: list[Page], *, exhaust_after: int | None = None) -> None:
        self.pages = pages
        self.exhaust_after = exhaust_after
        self.calls: list[Call] = []

    def iter_pages(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        start_cursor: str = "*",
    ) -> Iterator[Page]:
        self.calls.append(Call(endpoint, dict(params), start_cursor))
        for index, current_page in enumerate(self.pages):
            if current_page.cursor_in != start_cursor and index == 0:
                raise AssertionError(
                    f"fixture expected cursor {current_page.cursor_in}, got {start_cursor}"
                )
            yield current_page
            if self.exhaust_after == index + 1:
                raise RateLimitExhausted(
                    "synthetic credit exhaustion",
                    rate_limit={"credits_remaining": 0, "resets_in_seconds": 60},
                )


def complete_pages() -> list[Page]:
    return [
        page(
            [
                work("W100000001", referenced_works=["W100000099"]),
                work("W100000002"),
            ],
            "*",
            "cursor-2",
        ),
        page([work("W100000002"), work("W100000003")], "cursor-2", None),
    ]


def test_stage_4_fetches_every_page_but_not_referenced_work_records(
    tmp_path: Path,
) -> None:
    client = WorksClient(complete_pages())

    result = stage_04.collect_author_works([candidate()], client, tmp_path, limit=10)

    assert [record["openalex_work_id"] for record in result.works] == [
        "W100000001",
        "W100000002",
        "W100000003",
    ]
    assert result.works[0]["professor_id"] == "MOCK-01"
    assert all(record["openalex_author_id"] == "A100000001" for record in result.works)
    assert "W100000099" in result.works[0]["referenced_works"]
    assert client.calls == [Call("works", {"filter": "author.id:A100000001"}, "*")]

    completeness = result.completeness["MOCK-01"]
    assert completeness["first_cursor"] == "*"
    assert completeness["last_cursor"] == "cursor-2"
    assert completeness["terminal_cursor"] is None
    assert completeness["page_count"] == 2
    assert completeness["work_count"] == 3
    assert completeness["collection_complete"] is True
    assert len(completeness["raw_hashes"]) == 2
    assert all(len(value) == 64 for value in completeness["raw_hashes"])

    marker = result.completeness_dir / "MOCK-01.json"
    assert json.loads(marker.read_text(encoding="utf-8")) == completeness
    checkpoint = json.loads(next((tmp_path / "data/raw/progress").glob("*.json")).read_text())
    assert checkpoint["normalized_setup"]["per_page"] == 100
    assert len(list((tmp_path / "data/raw/pages").rglob("*.json"))) == 2
    assert [
        json.loads(line) for line in result.output_path.read_text().splitlines()
    ] == result.works


def test_stage_4_resumes_at_saved_cursor_and_merges_persisted_pages(
    tmp_path: Path,
) -> None:
    first_client = WorksClient([complete_pages()[0]], exhaust_after=1)

    with pytest.raises(CollectionPaused) as caught:
        stage_04.collect_author_works([candidate()], first_client, tmp_path, limit=10)

    assert caught.value.code == 75
    assert first_client.calls[0].start_cursor == "*"
    assert not (tmp_path / "data/raw/author_works.jsonl").exists()

    resumed_client = WorksClient([complete_pages()[1]])
    result = stage_04.collect_author_works(
        [candidate()], resumed_client, tmp_path, limit=10, resume=True
    )

    assert resumed_client.calls == [Call("works", {"filter": "author.id:A100000001"}, "cursor-2")]
    assert [record["openalex_work_id"] for record in result.works] == [
        "W100000001",
        "W100000002",
        "W100000003",
    ]
    assert result.completeness["MOCK-01"]["page_count"] == 2
    assert len(list((tmp_path / "data/raw/pages").rglob("*.json"))) == 2


def test_stage_4_enforces_author_safety_limit_before_writing(tmp_path: Path) -> None:
    candidates = [candidate(f"MOCK-{index:02d}", f"A1000000{index:02d}") for index in range(1, 12)]
    client = WorksClient([])

    with pytest.raises(ValueError, match="--full-run"):
        stage_04.collect_author_works(candidates, client, tmp_path, limit=11)

    assert client.calls == []
    assert not (tmp_path / "data/raw").exists()


def test_stage_4_rejects_unsafe_professor_marker_id_before_writing(tmp_path: Path) -> None:
    client = WorksClient([])

    with pytest.raises(ValueError, match="professor_id"):
        stage_04.collect_author_works([candidate("../escaped-marker")], client, tmp_path, limit=10)

    assert client.calls == []
    assert not (tmp_path / "data/raw").exists()


def test_stage_5_reconstructs_abstract_without_discarding_inverted_index() -> None:
    inverted = {"evidence": [2], "Verified": [0], "helps": [1, 3]}
    original = {
        **work("W100000001", abstract_inverted_index=inverted),
        "openalex_author_id": "A100000001",
    }

    transformed = stage_05.reconstruct_work_abstracts([original])

    assert original["abstract_inverted_index"] == inverted
    assert "reconstructed_abstract" not in original
    assert transformed[0]["abstract_inverted_index"] == inverted
    assert transformed[0]["openalex_author_id"] == "A100000001"
    assert transformed[0]["reconstructed_abstract"] == "Verified helps evidence helps"
    assert transformed[0]["abstract_reconstruction_version"] == ("openalex-inverted-index-v2")


def test_stage_5_limit_counts_authors_not_work_records(tmp_path: Path) -> None:
    records = [
        {**work("W100000001", abstract_inverted_index={"One": [0]}), "professor_id": "MOCK-01"},
        {**work("W100000002", abstract_inverted_index={"Two": [0]}), "professor_id": "MOCK-01"},
        {**work("W100000003", abstract_inverted_index={"Three": [0]}), "professor_id": "MOCK-02"},
    ]
    source = tmp_path / "author_works.jsonl"
    destination = tmp_path / "author_works_with_abstracts.jsonl"
    source.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")

    exit_code = stage_05.main(
        [
            "--config",
            str(ROOT / "config/dataset.yaml"),
            "--input",
            str(source),
            "--output",
            str(destination),
            "--log-file",
            str(tmp_path / "stage-5.log"),
            "--limit",
            "1",
        ]
    )

    written = [json.loads(line) for line in destination.read_text().splitlines()]
    assert exit_code == 0
    assert [record["id"] for record in written] == [
        "https://openalex.org/W100000001",
        "https://openalex.org/W100000002",
    ]
    assert [record["reconstructed_abstract"] for record in written] == ["One", "Two"]
