from __future__ import annotations

from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.bundles import build_enrichment_tasks, build_openalex_bundle  # noqa: E402


stage_11 = importlib.import_module("11_build_evidence_packets")


@pytest.fixture
def bundle_schema() -> dict[str, Any]:
    return json.loads(
        (ROOT / "schemas/openalex_profile_bundle.schema.json").read_text(encoding="utf-8")
    )


@pytest.fixture
def bundle_inputs() -> dict[str, Any]:
    profile = {
        "schema_version": "1.0.0",
        "dataset_version": "benchmark-v1",
        "candidate_pool_version": "candidate-pool-v1",
        "bundle_version": "openalex-provisional-bundle-v1",
        "professor_id": "MOCK-01",
        "openalex_author_id": "https://openalex.org/A100000001",
        "display_name": "Ada Synthetic",
        "last_known_institutions": [
            {
                "openalex_id": "I100000001",
                "openalex_url": "https://openalex.org/I100000001",
                "display_name": "Synthetic Institute",
                "country_code": "US",
                "region": "north_america",
                "type": "education",
            }
        ],
        "works_count": 24,
        "cited_by_count": 320,
        "h_index": 9,
        "first_publication_year": 2012,
        "last_publication_year": 2025,
        "primary_domain": "computer_science_engineering",
        "primary_field": "Computer Science",
        "primary_subfield": "Artificial Intelligence",
        "primary_topics": [{"id": "T100000001", "display_name": "Synthetic topic", "score": 0.9}],
        "career_estimate": {
            "stage": "mid",
            "source": "estimated_from_first_publication_year",
            "first_publication_year": 2012,
        },
        "visibility": {
            "score": 0.61,
            "components": {"citation_percentile": 0.7, "h_index_percentile": 0.52},
        },
        "research_breadth": {
            "score": 0.5,
            "components": {"normalized_topic_entropy": 0.5},
        },
        "topic_coherence_aid": {
            "score": 0.7,
            "components": {"hierarchy_agreement": 0.7},
            "human_reviewed": False,
        },
        "method_diversity": {
            "score": 0.4,
            "components": {"method_entropy": 0.4},
        },
        "paper_complexity": {
            "score": 0.55,
            "components": {"mean": 55.0, "median": 54.0},
        },
        "synthesis_difficulty": {
            "score": 0.6,
            "components": {
                "topic_entropy": 0.5,
                "mean_semantic_distance": None,
                "topic_cluster_count": 0.4,
                "method_diversity": 0.4,
                "dataset_population_diversity": 0.3,
                "temporal_research_evolution": 0.2,
                "cross_domain_breadth": 0.1,
                "inverse_topic_coherence": 0.3,
            },
            "missing_components": ["mean_semantic_distance"],
            "human_reviewed": False,
        },
        "openalex_consistency": {
            "status": "openalex_consistent",
            "issue_codes": [],
            "scope": "within_openalex",
            "externally_verified": False,
        },
    }
    papers = []
    for index in range(1, 9):
        papers.append(
            {
                "professor_id": "MOCK-01",
                "paper_id": f"W10000000{index}",
                "openalex_work_id": f"https://openalex.org/W10000000{index}",
                "title": f"Synthetic paper {index}",
                "publication_year": 2017 + index,
                "authorships": [
                    {
                        "author": {
                            "id": "https://openalex.org/A100000001",
                            "display_name": "Ada Synthetic",
                        }
                    }
                ],
                "primary_topic": {
                    "id": f"T10000000{index}",
                    "display_name": f"Synthetic topic {index}",
                },
                "method_tags": ["statistical_modeling"],
                "popularity": {
                    "cited_by_count": index,
                    "field_normalized_citation_percentile": index / 10,
                },
                "complexity": {
                    "score": 40.0 + index,
                    "components": {
                        "technical_vocabulary_density": 50.0,
                        "method_count": 30.0,
                    },
                },
                "open_access": {"is_oa": index <= 2, "oa_status": "green"},
                "best_oa_location": {"landing_page_url": f"https://example.invalid/paper-{index}"},
                "selection_reason": "recent" if index <= 3 else "diversifying",
                "selected": True,
                "focal": index <= 2,
            }
        )
    return {
        "profile": profile,
        "selected_papers": papers,
        "focal_ids": ["W100000001", "W100000002"],
        "provenance": {
            "raw_source_hashes": ["a" * 64, "b" * 64],
            "openalex_urls": [
                "https://openalex.org/A100000001",
                *[f"https://openalex.org/W10000000{index}" for index in range(1, 9)],
            ],
            "retrieved_at": "2026-07-14T12:00:00Z",
            "collection_code_version": "collection-code-v1",
        },
    }


def test_provisional_bundle_validates_but_is_not_final_ready(
    bundle_inputs: dict[str, Any], bundle_schema: dict[str, Any]
) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)
    Draft202012Validator(bundle_schema, format_checker=FormatChecker()).validate(bundle)
    assert bundle["final_evidence_packet_ready"] is False
    assert {task["task_type"] for task in bundle["enrichment_tasks"]} >= {
        "verify_faculty_status",
        "resolve_author_identity",
        "extract_focal_passages",
    }
    assert "passages" not in bundle


def test_bundle_is_anonymous_and_has_exact_selection_counts(bundle_inputs: dict[str, Any]) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)

    assert len(bundle["selected_papers"]) == 8
    assert len(bundle["focal_paper_ids"]) == 2
    serialized = json.dumps(bundle, sort_keys=True)
    assert "Ada Synthetic" not in serialized
    assert "Synthetic Institute" not in serialized
    assert "display_name" not in serialized
    assert "authorships" not in serialized
    assert bundle["provenance"]["raw_source_hashes"] == ["a" * 64, "b" * 64]
    assert len(bundle["provenance"]["openalex_urls"]) == 9


def test_bundle_rejects_wrong_or_inconsistent_paper_counts(bundle_inputs: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="exactly 8"):
        build_openalex_bundle(
            **{**bundle_inputs, "selected_papers": bundle_inputs["selected_papers"][:-1]}
        )

    with pytest.raises(ValueError, match="focal.*selected"):
        build_openalex_bundle(**{**bundle_inputs, "focal_ids": ["W100000001", "W999999999"]})


def test_enrichment_task_ids_are_stable_and_cover_every_missing_gate(
    bundle_inputs: dict[str, Any],
) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)
    expected_types = {
        "verify_faculty_status",
        "resolve_author_identity",
        "reconcile_crossref_metadata",
        "reconcile_semantic_scholar_ownership",
        "retrieve_legal_full_text",
        "extract_focal_passages",
        "review_topic_coherence",
        "review_synthesis_difficulty",
    }

    assert {task["task_type"] for task in bundle["enrichment_tasks"]} == expected_types
    assert bundle["enrichment_tasks"] == build_enrichment_tasks(deepcopy(bundle))
    assert len({task["task_id"] for task in bundle["enrichment_tasks"]}) == len(
        bundle["enrichment_tasks"]
    )
    assert all(len(task["task_id"]) == 64 for task in bundle["enrichment_tasks"])
    focal_tasks = [
        task
        for task in bundle["enrichment_tasks"]
        if task["task_type"] in {"retrieve_legal_full_text", "extract_focal_passages"}
    ]
    assert {task["paper_id"] for task in focal_tasks} == set(bundle["focal_paper_ids"])

    changed = deepcopy(bundle)
    changed["bundle_version"] = "openalex-provisional-bundle-v2"
    assert {task["task_id"] for task in build_enrichment_tasks(changed)}.isdisjoint(
        {task["task_id"] for task in bundle["enrichment_tasks"]}
    )


def test_stage_11_builds_and_validates_profile_bundles(
    tmp_path: Path, bundle_inputs: dict[str, Any]
) -> None:
    bundle = stage_11.build_profile_bundles(
        [
            {
                "profile": bundle_inputs["profile"],
                "selected_papers": bundle_inputs["selected_papers"],
                "focal_ids": bundle_inputs["focal_ids"],
                "provenance": bundle_inputs["provenance"],
            }
        ]
    )

    assert len(bundle) == 1
    assert bundle[0]["professor_id"] == "MOCK-01"
    stage_11.validate_profile_bundles(bundle)
    assert stage_11.SPEC.name == "build_openalex_profile_bundles"
    assert stage_11.SPEC.default_output == "data/final/openalex_profile_bundles"


def test_strict_final_schema_remains_separate_and_requires_passages() -> None:
    strict_schema = json.loads(
        (ROOT / "schemas/evidence_packet.schema.json").read_text(encoding="utf-8")
    )

    assert "passages" in strict_schema["required"]
    assert "final_evidence_packet_ready" not in strict_schema["properties"]
