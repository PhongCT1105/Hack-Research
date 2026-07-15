from __future__ import annotations

import csv
import importlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

stage_10 = importlib.import_module("10_stratified_sample_professors")


def candidate(
    professor_id: str,
    *,
    institution: str,
    region: str,
    domain: str,
    career_stage: str = "early",
    synthesis_difficulty: str = "low",
) -> dict[str, Any]:
    return {
        "professor_id": professor_id,
        "institution_id": institution,
        "region": region,
        "domain": domain,
        "career_stage": career_stage,
        "synthesis_difficulty": synthesis_difficulty,
        "selected_papers": [f"{professor_id}-W{index}" for index in range(8)],
        "work_history": {"collection_complete": True},
        "openalex_consistency": {"status": "openalex_consistent", "issue_codes": []},
    }


def targets() -> dict[str, dict[str, int]]:
    return {
        "domain": {"systems": 2, "health": 2, "theory": 2},
        "career_stage": {"early": 2, "senior": 2},
        "synthesis_difficulty": {"low": 2, "high": 2},
    }


def synthetic_candidates() -> list[dict[str, Any]]:
    return [
        candidate(
            f"P{index:02d}",
            institution=f"I{index // 2}",
            region=("north", "south")[index % 2],
            domain=("systems", "health")[index % 2],
            career_stage=("early", "senior")[index % 2],
            synthesis_difficulty=("low", "high")[index % 2],
        )
        for index in range(5)
    ]


def test_sampler_is_reproducible_and_reports_unmet_targets() -> None:
    first = stage_10.sample_professors(synthetic_candidates(), targets(), seed=42, limit=4)
    second = stage_10.sample_professors(
        list(reversed(synthetic_candidates())), targets(), seed=42, limit=4
    )

    assert first.selected_ids == second.selected_ids
    assert first.achieved_distribution == second.achieved_distribution
    assert first.unmet_targets == {"domain": {"theory": 2}}
    assert first.target_distribution == targets()
    assert first.objective >= 0
    assert all(reasons for reasons in first.exclusion_reasons.values())
    assert first.reason_counts["not_selected_by_optimizer"] == 1


def test_sampler_applies_all_hard_openalex_quality_gates() -> None:
    eligible = candidate("ELIGIBLE", institution="I1", region="north", domain="systems")
    too_few = candidate("TOO-FEW", institution="I2", region="south", domain="health")
    too_few["selected_papers"].pop()
    incomplete = candidate("INCOMPLETE", institution="I3", region="east", domain="health")
    incomplete["work_history"]["collection_complete"] = False
    identity_issue = candidate("IDENTITY", institution="I4", region="west", domain="systems")
    identity_issue["openalex_consistency"] = {
        "status": "needs_identity_review",
        "issue_codes": ["cross_profile_work_overlap"],
    }

    result = stage_10.sample_professors(
        [too_few, incomplete, identity_issue, eligible],
        {"domain": {"systems": 1}},
        seed=7,
        limit=4,
    )

    assert result.selected_ids == ("ELIGIBLE",)
    assert result.exclusion_reasons == {
        "IDENTITY": ("blocking_openalex_consistency_issue",),
        "INCOMPLETE": ("incomplete_work_history",),
        "TOO-FEW": ("selected_paper_count_not_eight",),
    }
    assert result.reason_counts == {
        "blocking_openalex_consistency_issue": 1,
        "incomplete_work_history": 1,
        "selected_paper_count_not_eight": 1,
    }


def test_sampler_requires_eight_unique_selected_papers() -> None:
    duplicate_papers = candidate("DUPLICATE", institution="I1", region="north", domain="systems")
    duplicate_papers["selected_papers"] = ["W1"] * 8
    duplicate_papers["selected_paper_count"] = 8

    result = stage_10.sample_professors(
        [duplicate_papers], {"domain": {"systems": 1}}, seed=42, limit=1
    )

    assert result.selected_ids == ()
    assert result.exclusion_reasons == {"DUPLICATE": ("selected_paper_count_not_eight",)}


def test_concentration_penalties_prefer_new_institution_and_region() -> None:
    candidates = [
        candidate("P1", institution="I1", region="north", domain="systems"),
        candidate("P2", institution="I1", region="north", domain="systems"),
        candidate("P3", institution="I2", region="south", domain="systems"),
    ]

    result = stage_10.sample_professors(
        candidates,
        {"domain": {"systems": 2}},
        seed=19,
        limit=2,
    )

    assert "P3" in result.selected_ids
    assert (
        len({candidates[int(item[1:]) - 1]["institution_id"] for item in result.selected_ids}) == 2
    )
    assert result.objective_components["institution_concentration_penalty"] == 0
    assert result.objective_components["region_concentration_penalty"] == 0


def test_human_review_dependent_target_is_marked_provisional() -> None:
    result = stage_10.sample_professors(
        [candidate("P1", institution="I1", region="north", domain="systems")],
        {"domain": {"systems": 1}, "synthesis_difficulty": {"low": 1}},
        seed=42,
        limit=1,
    )

    assert result.provisional_dimensions == ("domain", "synthesis_difficulty")
    assert result.report["target_status"] == {
        "domain": "provisional_human_review_required",
        "synthesis_difficulty": "provisional_human_review_required",
    }
    assert result.report["selected_ids"] == ["P1"]


@pytest.mark.parametrize(
    ("seed", "limit", "message"),
    [(True, 1, "seed must be an integer"), (42, 0, "limit must be at least 1")],
)
def test_sampler_rejects_invalid_control_values(seed: Any, limit: int, message: str) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        stage_10.sample_professors([], {}, seed=seed, limit=limit)


def test_stage_10_dry_run_reports_local_sampling_contract(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = stage_10.main(["--config", str(ROOT / "config/dataset.yaml"), "--dry-run"])

    assert exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["implemented_locally"] is True
    assert plan["limit"] == 100
    assert plan["algorithm_version"] == "constrained-margins-v1"
    assert plan["candidate_pool_version"] == "candidate-pool-v1"
    assert plan["target_dimensions"] == [
        "career_stage",
        "domain",
        "paper_complexity",
        "research_breadth",
        "synthesis_difficulty",
        "visibility",
    ]


def test_stage_10_cli_writes_selected_rows_and_sampling_report(tmp_path: Path) -> None:
    source = tmp_path / "candidates.csv"
    output = tmp_path / "selected.csv"
    rows = [
        {
            "professor_id": "P1",
            "institution_id": "I1",
            "region": "north",
            "domain": "systems",
            "selected_paper_count": "8",
            "collection_complete": "true",
            "consistency_status": "openalex_consistent",
        },
        {
            "professor_id": "P2",
            "institution_id": "I2",
            "region": "south",
            "domain": "health",
            "selected_paper_count": "8",
            "collection_complete": "true",
            "consistency_status": "openalex_consistent",
        },
        {
            "professor_id": "P3",
            "institution_id": "I3",
            "region": "east",
            "domain": "systems",
            "selected_paper_count": "7",
            "collection_complete": "true",
            "consistency_status": "openalex_consistent",
        },
    ]
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    exit_code = stage_10.main(
        [
            "--config",
            str(ROOT / "config/dataset.yaml"),
            "--input",
            str(source),
            "--output",
            str(output),
            "--limit",
            "2",
            "--seed",
            "11",
        ]
    )

    assert exit_code == 0
    with output.open(encoding="utf-8", newline="") as stream:
        written = list(csv.DictReader(stream))
    assert {row["professor_id"] for row in written} == {"P1", "P2"}
    assert [row["sampling_order"] for row in written] == ["1", "2"]
    report = json.loads(output.with_suffix(".sampling_report.json").read_text(encoding="utf-8"))
    assert report["selected_ids"] == [row["professor_id"] for row in written]
    assert report["exclusions"] == {"P3": ["selected_paper_count_not_eight"]}
    assert report["unmet_targets"]
