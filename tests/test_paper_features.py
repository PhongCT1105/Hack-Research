from __future__ import annotations

from copy import deepcopy
import importlib
from pathlib import Path
import sys
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.features import (  # noqa: E402
    PAPER_FEATURES_VERSION,
    ComplexityComponents,
    extract_paper_features,
    percentile_rank,
    score_paper_complexity,
)


stage_07 = importlib.import_module("07_score_paper_complexity")


def paper(
    paper_id: str,
    text: str | None,
    *,
    field: str = "Computer Science",
    domain: str = "Physical Sciences",
    year: int = 2024,
    citations: int = 0,
) -> dict[str, Any]:
    return {
        "paper_id": paper_id,
        "professor_id": "MOCK-01",
        "reconstructed_abstract": text,
        "field": field,
        "domain": domain,
        "publication_year": year,
        "cited_by_count": citations,
        "topics": [
            {"display_name": "Machine learning", "field": field, "domain": domain},
            {"display_name": "Education", "field": "Education", "domain": "Social Sciences"},
        ],
    }


def test_complexity_uses_documented_weights() -> None:
    components = ComplexityComponents(100, 50, 40, 20, 80, 60, 2, 0.1)

    assert score_paper_complexity(components) == pytest.approx(62.0)


def test_missing_abstract_is_explicit_not_zero() -> None:
    result = extract_paper_features(None, topics=[])

    assert result.available is False
    assert result.technical_vocabulary_density is None
    assert result.word_count is None
    assert result.qualification_hedging_density is None


def test_lexical_features_are_unicode_aware_counted_and_repeatable() -> None:
    text = (
        "We hypothesize a naïve Bayesian model. Using regression on a cohort dataset, "
        "we evaluate two experiments. Results significantly improved accuracy; however, "
        "the effect may be limited."
    )
    topics = [
        {"field": "Computer Science", "domain": "Physical Sciences"},
        {"field": "Education", "domain": "Social Sciences"},
        {"field": "Computer Science", "domain": "Physical Sciences"},
    ]

    first = extract_paper_features(text, topics)
    second = extract_paper_features(text, topics)

    assert first == second
    assert first.available is True
    assert first.word_count == 26
    assert first.sentence_count == 3
    assert first.method_count >= 2
    assert first.dataset_or_population_count >= 2
    assert first.result_or_experiment_count >= 3
    assert first.research_objective_count >= 1
    assert first.qualification_hedging_count >= 2
    assert first.interdisciplinary_breadth == 2
    assert first.technical_vocabulary_count > 0
    assert first.technical_vocabulary_density == pytest.approx(
        100 * first.technical_vocabulary_count / first.word_count
    )


def test_percentile_rank_uses_midrank_for_ties_and_handles_singleton() -> None:
    values = [10.0, 20.0, 20.0, 40.0]

    assert percentile_rank(20.0, values) == pytest.approx(50.0)
    assert percentile_rank(10.0, values) == pytest.approx(12.5)
    assert percentile_rank(40.0, values) == pytest.approx(87.5)
    assert percentile_rank(7.0, [7.0]) == pytest.approx(50.0)
    assert percentile_rank(None, values) is None


def test_controlled_indicators_cover_common_inflected_abstract_terms() -> None:
    result = extract_paper_features(
        "Methods use datasets and cohorts. Results from experiments suggest findings.",
        topics=[],
    )

    assert result.method_count >= 2
    assert result.dataset_or_population_count >= 2
    assert result.result_or_experiment_count >= 3
    assert result.qualification_hedging_count >= 1


def test_stage_scores_with_recorded_field_year_and_domain_year_fallbacks() -> None:
    rows = [
        paper("P1", "We use regression on a dataset and report results.", citations=2),
        paper(
            "P2", "We use regression and simulation on two cohorts. Results improved.", citations=8
        ),
        paper("P3", "A model evaluates an experiment and reports accuracy.", citations=20),
        paper(
            "P4",
            "Interviews analyze a participant sample and may suggest findings.",
            field="Education",
            domain="Social Sciences",
            citations=1,
        ),
        paper(
            "P5",
            "A survey analyzes a student population and reports evidence.",
            field="Psychology",
            domain="Social Sciences",
            citations=4,
        ),
        paper(
            "P6",
            "A randomized trial evaluates a cohort and reports outcomes.",
            field="Sociology",
            domain="Social Sciences",
            citations=9,
        ),
    ]

    scored = stage_07.score_paper_records(rows, minimum_stratum_size=3)

    assert scored[0]["complexity"]["normalization_stratum"] == "field_year:Computer Science:2024"
    assert scored[3]["complexity"]["normalization_stratum"] == "domain_year:Social Sciences:2024"
    assert scored[0]["complexity"]["score_version"] == "paper-complexity-v1"
    assert scored[0]["paper_features"]["feature_version"] == PAPER_FEATURES_VERSION
    assert "raw_counts" in scored[0]["paper_features"]
    assert "densities" in scored[0]["paper_features"]


def test_stage_preserves_missingness_does_not_mutate_and_keeps_popularity_separate() -> None:
    rows = [
        paper("P1", None, citations=10_000),
        paper("P2", "We report a result.", citations=1),
        paper("P3", "We report two experiments and a result.", citations=5),
    ]
    original = deepcopy(rows)

    first = stage_07.score_paper_records(rows, minimum_stratum_size=3)
    second = stage_07.score_paper_records(rows, minimum_stratum_size=3)

    assert first == second
    assert rows == original
    assert first[0]["paper_features"]["available"] is False
    assert first[0]["complexity"]["score"] is None
    assert first[0]["complexity"]["components"]["technical_vocabulary_density"] is None
    assert first[0]["popularity"]["raw_citation_count"] == 10_000
    assert first[0]["popularity"]["field_normalized_citation_percentile"] is not None
    assert "citation" not in first[0]["complexity"]["components"]
