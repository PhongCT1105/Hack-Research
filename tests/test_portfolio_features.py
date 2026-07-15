from __future__ import annotations

import importlib
import math
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

stage_08 = importlib.import_module("08_score_research_portfolios")

SYNTHESIS_WEIGHTS = stage_08.SYNTHESIS_WEIGHTS
build_topic_clusters = stage_08.build_topic_clusters
method_entropy = stage_08.method_entropy
score_portfolio = stage_08.score_portfolio
score_portfolios = stage_08.score_portfolios
topic_entropy = stage_08.topic_entropy


def _topic(
    topic_id: str,
    topic: str,
    subfield_id: str,
    subfield: str,
    field_id: str,
    field: str,
    domain_id: str = "D3",
    domain: str = "Physical Sciences",
) -> dict[str, str]:
    return {
        "topic_id": topic_id,
        "topic": topic,
        "subfield_id": subfield_id,
        "subfield": subfield,
        "field_id": field_id,
        "field": field,
        "domain_id": domain_id,
        "domain": domain,
    }


def _paper(
    paper_id: str,
    topic: dict[str, str],
    *,
    year: int,
    methods: list[str],
    datasets: list[str],
    complexity: float,
    citations: float,
    is_oa: bool,
) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "professor_id": "CS-01",
        "openalex_author_id": "A1",
        "publication_year": year,
        "primary_topic": topic,
        "topics": [topic],
        "method_tags": methods,
        "dataset_population_tags": datasets,
        "complexity": {"score": complexity},
        "popularity": {"field_normalized_citation_percentile": citations},
        "open_access": {"is_oa": is_oa, "oa_status": "gold" if is_oa else "closed"},
        "reconstructed_abstract": "A usable abstract.",
        "authorships": [
            {
                "author": {"id": "A1"},
                "institutions": [{"id": "I1"}, {"id": f"I-{paper_id}"}],
            },
            {"author": {"id": f"A-{paper_id}"}, "institutions": [{"id": "I2"}]},
        ],
    }


def related_multi_field_papers() -> list[dict[str, Any]]:
    return [
        _paper(
            "W1",
            _topic(
                "T1", "Machine learning", "S1", "Artificial Intelligence", "F1", "Computer Science"
            ),
            year=2018,
            methods=["deep_learning"],
            datasets=["students"],
            complexity=30.0,
            citations=20.0,
            is_oa=True,
        ),
        _paper(
            "W2",
            _topic(
                "T2", "Language models", "S1", "Artificial Intelligence", "F1", "Computer Science"
            ),
            year=2020,
            methods=["deep_learning", "statistical_modeling"],
            datasets=["students"],
            complexity=50.0,
            citations=40.0,
            is_oa=False,
        ),
        _paper(
            "W3",
            _topic("T3", "Learning analytics", "S2", "Education Systems", "F2", "Education"),
            year=2022,
            methods=["statistical_modeling"],
            datasets=["teachers"],
            complexity=70.0,
            citations=60.0,
            is_oa=True,
        ),
        _paper(
            "W4",
            _topic(
                "T4",
                "Human-computer interaction",
                "S3",
                "Human Computing",
                "F1",
                "Computer Science",
            ),
            year=2024,
            methods=["survey_research"],
            datasets=["teachers", "students"],
            complexity=90.0,
            citations=80.0,
            is_oa=True,
        ),
    ]


def test_entropy_is_normalized_and_order_independent() -> None:
    assert topic_entropy(["T1", "T1", "T2", "T2"]) == pytest.approx(1.0)
    assert topic_entropy(["T2", "T1", "T2", "T1"]) == pytest.approx(1.0)
    assert method_entropy(["survey", "survey", "survey"]) == pytest.approx(0.0)
    assert topic_entropy([]) is None

    raw_works = [
        {"id": "W1", "primary_topic": {"id": "T1"}},
        {"id": "W2", "primary_topic": {"id": "T1"}},
    ]
    assert topic_entropy(raw_works) == pytest.approx(0.0)
    assert topic_entropy([{"id": "T1"}, {"id": "T2"}]) == pytest.approx(1.0)


def test_topic_clusters_use_stable_openalex_hierarchy_ids() -> None:
    papers = related_multi_field_papers()
    first = build_topic_clusters(papers)
    second = build_topic_clusters(list(reversed(papers)))

    assert first == second
    assert [cluster["cluster_id"] for cluster in first] == ["field:F1", "field:F2"]
    assert first[0]["paper_ids"] == ["W1", "W2", "W4"]
    assert first[0]["topic_ids"] == ["T1", "T2", "T4"]


def test_broad_portfolio_can_still_have_high_coherence_aid() -> None:
    result = score_portfolio(related_multi_field_papers())

    assert result["research_breadth"]["score"] > 0.5
    assert result["topic_coherence_aid"]["score"] > 0.5
    assert "synthesis_difficulty" in result
    assert result["topic_coherence_aid"]["human_reviewed"] is False
    assert result["synthesis_difficulty"]["human_reviewed"] is False


def test_portfolio_constructs_and_distributions_remain_separate() -> None:
    result = score_portfolio(related_multi_field_papers())

    expected_constructs = {
        "research_breadth",
        "topic_coherence_aid",
        "method_diversity",
        "paper_complexity",
        "synthesis_difficulty",
        "visibility",
        "evidence_completeness",
    }
    assert expected_constructs <= result.keys()
    assert result["temporal_distribution"]["publication_span_years"] == 6
    assert result["collaboration_distribution"]["mean_author_count"] == pytest.approx(2.0)
    assert result["collaboration_distribution"]["unique_collaborator_count"] == 4
    assert result["open_access_distribution"]["rate"] == pytest.approx(0.75)
    assert result["method_diversity"]["tags"] == [
        "deep_learning",
        "statistical_modeling",
        "survey_research",
    ]
    assert result["dataset_population_distribution"]["tags"] == ["students", "teachers"]
    assert result["paper_complexity"]["distribution"]["mean"] == pytest.approx(60.0)
    assert result["visibility"]["score"] == pytest.approx(0.5)
    assert result["research_breadth"]["components"][
        "normalized_topic_cluster_balance"
    ] == pytest.approx(0.8112781244591328)


def test_synthesis_uses_documented_available_weight_denominator() -> None:
    result = score_portfolio(related_multi_field_papers())
    synthesis = result["synthesis_difficulty"]

    assert synthesis["components"]["mean_semantic_distance"] is None
    assert synthesis["missing_components"] == ["mean_semantic_distance"]
    expected_denominator = sum(
        weight
        for name, weight in SYNTHESIS_WEIGHTS.items()
        if synthesis["components"][name] is not None
    )
    expected_score = (
        math.fsum(
            synthesis["components"][name] * weight
            for name, weight in SYNTHESIS_WEIGHTS.items()
            if synthesis["components"][name] is not None
        )
        / expected_denominator
    )
    assert synthesis["weight_denominator"] == pytest.approx(expected_denominator)
    assert synthesis["score"] == pytest.approx(expected_score)


def test_missing_portfolio_evidence_is_explicit_not_imputed() -> None:
    result = score_portfolio(
        [
            {
                "paper_id": "W-missing",
                "professor_id": "CS-02",
                "primary_topic": None,
                "topics": [],
                "method_tags": [],
                "dataset_population_tags": [],
                "open_access": None,
                "authorships": [],
            }
        ]
    )

    assert result["research_breadth"]["score"] is None
    assert result["paper_complexity"]["score"] is None
    assert result["visibility"]["score"] is None
    assert result["evidence_completeness"]["score"] == pytest.approx(0.0)
    assert result["synthesis_difficulty"]["score"] is None
    assert result["synthesis_difficulty"]["weight_denominator"] == pytest.approx(0.0)
    assert set(result["synthesis_difficulty"]["missing_components"]) == set(SYNTHESIS_WEIGHTS)


def test_score_portfolios_groups_records_without_mixing_professors() -> None:
    papers = related_multi_field_papers()
    papers.append({**papers[0], "paper_id": "W5", "professor_id": "CS-02"})

    portfolios = score_portfolios(papers)

    assert [portfolio["professor_id"] for portfolio in portfolios] == ["CS-01", "CS-02"]
    assert [portfolio["paper_count"] for portfolio in portfolios] == [4, 1]
