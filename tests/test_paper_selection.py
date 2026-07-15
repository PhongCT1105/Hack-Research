from __future__ import annotations

from collections import Counter
from copy import deepcopy
import importlib
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

stage_09 = importlib.import_module("09_select_representative_papers")

from lib.selection import (  # noqa: E402
    select_candidate_pool,
    select_focal_candidates,
    select_representative_papers,
)


def paper(
    index: int,
    *,
    year: int | None = None,
    influence: float | None = None,
    topic: str | None = None,
    methods: list[str] | None = None,
    oa_url: str | None = None,
    abstract: str | None = "A usable abstract.",
    consistency: str = "openalex_consistent",
) -> dict[str, Any]:
    topic_id = topic or f"T{index % 5}"
    return {
        "paper_id": f"W{index:03d}",
        "openalex_work_id": f"W{index:03d}",
        "professor_id": "CS-01",
        "publication_year": year if year is not None else 2000 + index,
        "popularity": {
            "field_normalized_citation_percentile": (
                influence if influence is not None else float(index)
            )
        },
        "topics": [{"topic_id": topic_id, "topic": f"Topic {topic_id}"}],
        "method_tags": methods if methods is not None else [f"method-{index % 4}"],
        "best_oa_location": {"landing_page_url": oa_url} if oa_url else None,
        "open_access": {"is_oa": bool(oa_url), "oa_status": "gold" if oa_url else "closed"},
        "reconstructed_abstract": abstract,
        "consistency_status": consistency,
        "is_retracted": False,
        "is_paratext": False,
    }


def thirty_papers() -> list[dict[str, Any]]:
    return [paper(index) for index in range(1, 31)]


def test_selector_returns_unique_three_two_two_one_allocation() -> None:
    selected = select_representative_papers(thirty_papers(), seed=42)

    assert len(selected) == 8
    assert len({item["paper_id"] for item in selected}) == 8
    assert Counter(item["selection_reason"] for item in selected) == {
        "recent": 3,
        "influential": 2,
        "diversifying": 2,
        "random": 1,
    }
    assert [item["paper_id"] for item in selected] == [
        item["paper_id"] for item in select_representative_papers(thirty_papers(), seed=42)
    ]


def test_rankings_are_input_order_independent_and_do_not_mutate_papers() -> None:
    papers = thirty_papers()
    original = deepcopy(papers)

    forward = select_representative_papers(papers, seed=17)
    backward = select_representative_papers(list(reversed(papers)), seed=17)

    assert forward == backward
    assert papers == original


def test_influential_slots_advance_after_collisions_with_recent_slots() -> None:
    papers = [paper(index, year=2000 + index, influence=float(index)) for index in range(1, 13)]

    selected = select_representative_papers(papers, seed=1)

    assert [item["paper_id"] for item in selected[:3]] == ["W012", "W011", "W010"]
    assert [item["paper_id"] for item in selected[3:5]] == ["W009", "W008"]


def test_diversifying_slots_greedily_add_new_topic_and_method_coverage() -> None:
    papers = [
        paper(
            index,
            topic="shared",
            methods=["shared-method"],
            year=2030 - index,
            influence=float(100 - index),
        )
        for index in range(1, 9)
    ]
    papers.extend(
        [
            paper(
                9,
                topic="new-topic-a",
                methods=["new-method-a"],
                year=2001,
                influence=1.0,
            ),
            paper(
                10,
                topic="new-topic-b",
                methods=["new-method-b"],
                year=2000,
                influence=0.0,
            ),
        ]
    )

    selected = select_representative_papers(papers, seed=3)
    diversifying = [
        item["paper_id"] for item in selected if item["selection_reason"] == "diversifying"
    ]

    assert diversifying == ["W009", "W010"]


def test_seed_controls_only_the_random_remaining_slot() -> None:
    first = select_representative_papers(thirty_papers(), seed=2)
    repeated = select_representative_papers(thirty_papers(), seed=2)
    different = select_representative_papers(thirty_papers(), seed=19)

    assert first == repeated
    assert [item["paper_id"] for item in first[:7]] == [item["paper_id"] for item in different[:7]]
    assert first[-1]["paper_id"] != different[-1]["paper_id"]


def test_selector_rejects_fewer_than_eight_unique_papers_and_duplicate_ids() -> None:
    with pytest.raises(ValueError, match="at least 8 unique papers"):
        select_representative_papers(thirty_papers()[:7], seed=42)

    duplicates = thirty_papers()[:8] + [deepcopy(thirty_papers()[0])]
    with pytest.raises(ValueError, match="duplicate paper_id W001"):
        select_representative_papers(duplicates, seed=42)


def test_candidate_pool_filters_explicitly_ineligible_records_and_caps_deterministically() -> None:
    papers = thirty_papers() + [paper(31), paper(32)]
    papers[0]["is_retracted"] = True
    papers[1]["is_paratext"] = True

    forward = select_candidate_pool(papers)
    backward = select_candidate_pool(list(reversed(papers)))

    assert forward == backward
    assert len(forward) == 30
    assert {item["paper_id"] for item in forward}.isdisjoint({"W001", "W002"})


def test_focal_candidates_are_two_provisional_metadata_only_choices() -> None:
    selected = select_representative_papers(thirty_papers(), seed=42)
    for item in selected:
        item["best_oa_location"] = None
        item["open_access"] = {"is_oa": False, "oa_status": "closed"}
        item["reconstructed_abstract"] = None
        item["consistency_status"] = "needs_identity_review"
    selected[4].update(
        {
            "best_oa_location": {"pdf_url": "https://example.test/five.pdf"},
            "open_access": {"is_oa": True, "oa_status": "green"},
            "reconstructed_abstract": "Methods and results are summarized.",
            "consistency_status": "openalex_consistent",
        }
    )
    selected[6].update(
        {
            "best_oa_location": {"landing_page_url": "https://example.test/seven"},
            "open_access": {"is_oa": True, "oa_status": "gold"},
            "reconstructed_abstract": "A second usable abstract.",
            "consistency_status": "openalex_consistent",
        }
    )

    focal = select_focal_candidates(selected)

    assert [item["paper_id"] for item in focal] == [
        selected[4]["paper_id"],
        selected[6]["paper_id"],
    ]
    assert all(item["focal"] is True for item in focal)
    assert all(item["focal_selection"]["provisional"] is True for item in focal)
    assert all(item["focal_selection"]["full_text_inspected"] is False for item in focal)
    assert all("full_text" not in item["focal_selection"]["basis"] for item in focal)


def test_focal_ranking_does_not_consume_a_full_text_availability_claim() -> None:
    selected = select_representative_papers(thirty_papers(), seed=42)
    baseline = select_focal_candidates(selected)
    toggled = deepcopy(selected)
    for index, item in enumerate(toggled):
        item["full_text_available"] = index % 2 == 0

    reranked = select_focal_candidates(toggled)

    assert [item["paper_id"] for item in reranked] == [item["paper_id"] for item in baseline]


def test_closed_primary_location_is_not_treated_as_oa_location_metadata() -> None:
    selected = [paper(index, abstract=None) for index in range(1, 4)]
    for item in selected:
        item["consistency_status"] = "needs_identity_review"
        item["open_access"] = {"is_oa": False, "oa_status": "closed"}
    selected[0]["primary_location"] = {
        "landing_page_url": "https://publisher.test/paywalled",
        "is_oa": False,
    }
    selected[1]["best_oa_location"] = {"landing_page_url": "https://repository.test/two"}
    selected[2]["best_oa_location"] = {"landing_page_url": "https://repository.test/three"}
    selected[1]["open_access"] = {"is_oa": True, "oa_status": "green"}
    selected[2]["open_access"] = {"is_oa": True, "oa_status": "gold"}

    focal = select_focal_candidates(selected)

    assert [item["paper_id"] for item in focal] == ["W002", "W003"]


def test_stage_groups_professors_and_marks_only_selected_and_focal_records() -> None:
    first = thirty_papers()
    second = [
        {**item, "professor_id": "CS-02", "paper_id": f"X{item['paper_id']}"} for item in first
    ]

    output = stage_09.select_paper_records(first + second, seed=11)

    assert len(output) == 60
    for professor_id in ("CS-01", "CS-02"):
        group = [item for item in output if item["professor_id"] == professor_id]
        assert sum(item["selected"] for item in group) == 8
        assert sum(item["focal"] for item in group) == 2
        assert all(item["focal"] is False for item in group if not item["selected"])


def test_candidate_csv_preserves_a_zero_citation_count() -> None:
    source = paper(1)
    source["citation_count"] = 0
    source["cited_by_count"] = 99

    row = stage_09._candidate_csv_record(source)

    assert row["citation_count"] == 0
