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

from lib.bundles import (  # noqa: E402
    build_enrichment_tasks,
    build_openalex_bundle,
    validate_enrichment_tasks,
    validate_openalex_bundle_semantics,
)


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


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("openalex_work_id", "https://openalex.org/W999999991"),
        ("openalex_url", "https://openalex.org/W999999992"),
    ],
)
def test_bundle_rejects_mismatched_selected_paper_openalex_identifiers(
    bundle_inputs: dict[str, Any], field: str, value: str
) -> None:
    papers = deepcopy(bundle_inputs["selected_papers"])
    papers[0][field] = value

    with pytest.raises(ValueError, match="identifiers.*same OpenAlex work"):
        build_openalex_bundle(**{**bundle_inputs, "selected_papers": papers})


@pytest.mark.parametrize(
    ("container", "forbidden_key", "value"),
    [
        (("openalex_profile", "career_estimate"), "display_name", "Real Person"),
        (
            ("selected_papers", 0, "complexity", "components"),
            "name",
            "Real Person",
        ),
        (("openalex_profile", "career_estimate"), "passages", []),
        (("selected_papers", 0, "primary_topic"), "passage_text", "forbidden text"),
    ],
)
def test_schema_rejects_forbidden_keys_anywhere_in_provisional_metadata(
    bundle_inputs: dict[str, Any],
    bundle_schema: dict[str, Any],
    container: tuple[str | int, ...],
    forbidden_key: str,
    value: Any,
) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)
    target: Any = bundle
    for segment in container:
        target = target[segment]
    target[forbidden_key] = value

    validator = Draft202012Validator(bundle_schema, format_checker=FormatChecker())
    assert not validator.is_valid(bundle)


@pytest.mark.parametrize(
    ("container", "forbidden_key"),
    [
        (("openalex_profile", "career_estimate"), "Display_Name"),
        (("selected_papers", 0, "complexity", "components"), "NAME"),
        (("openalex_profile", "career_estimate"), "Passages"),
        (("selected_papers", 0, "primary_topic"), "Passage_Text"),
        (("openalex_profile", "career_estimate"), "Ｄｉｓｐｌａｙ＿Ｎａｍｅ"),
        (("selected_papers", 0, "primary_topic"), "Passage-Text"),
    ],
)
def test_semantics_reject_case_unicode_and_separator_variants_of_forbidden_keys(
    bundle_inputs: dict[str, Any],
    container: tuple[str | int, ...],
    forbidden_key: str,
) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)
    target: Any = bundle
    for segment in container:
        target = target[segment]
    target[forbidden_key] = "forbidden"

    with pytest.raises(ValueError, match="forbidden bundle key"):
        validate_openalex_bundle_semantics(bundle)


def test_builder_sanitizes_case_unicode_and_separator_variants_recursively(
    bundle_inputs: dict[str, Any],
) -> None:
    inputs = deepcopy(bundle_inputs)
    inputs["profile"]["career_estimate"].update(
        {
            "Display_Name": "Real Person",
            "ＮＡＭＥ": "Real Person",
            "Passages": ["forbidden"],
            "Passage Text": "forbidden",
        }
    )
    inputs["selected_papers"][0]["complexity"]["components"].update(
        {"display-name": "Real Person", "PASSAGE_TEXT": "forbidden"}
    )

    bundle = build_openalex_bundle(**inputs)

    assert set(bundle["openalex_profile"]["career_estimate"]) == {
        "stage",
        "source",
        "first_publication_year",
    }
    assert set(bundle["selected_papers"][0]["complexity"]["components"]) == {
        "technical_vocabulary_density",
        "method_count",
    }


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


def test_schema_caps_enrichment_tasks_and_rejects_exact_duplicates(
    bundle_inputs: dict[str, Any], bundle_schema: dict[str, Any]
) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)
    validator = Draft202012Validator(bundle_schema, format_checker=FormatChecker())

    duplicated = deepcopy(bundle)
    duplicated["enrichment_tasks"].append(deepcopy(duplicated["enrichment_tasks"][0]))

    assert not validator.is_valid(duplicated)
    assert bundle_schema["properties"]["enrichment_tasks"]["maxItems"] == 10
    assert bundle_schema["properties"]["enrichment_tasks"]["uniqueItems"] is True


@pytest.mark.parametrize("mutation", ["wrong_hash", "general_has_paper", "focal_missing_paper"])
def test_enrichment_semantics_reject_wrong_hash_or_scope(
    bundle_inputs: dict[str, Any], mutation: str
) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)
    tasks = bundle["enrichment_tasks"]
    if mutation == "wrong_hash":
        tasks[0]["task_id"] = "0" * 64
    elif mutation == "general_has_paper":
        tasks[0]["paper_id"] = bundle["focal_paper_ids"][0]
    else:
        focal_task = next(task for task in tasks if task["task_type"] == "extract_focal_passages")
        focal_task.pop("paper_id")

    with pytest.raises(ValueError, match="enrichment task"):
        validate_enrichment_tasks(bundle)


@pytest.mark.parametrize("mutation", ["missing", "repeated_type", "duplicate_id"])
def test_enrichment_semantics_reject_missing_repeated_or_duplicate_tasks(
    bundle_inputs: dict[str, Any], mutation: str
) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)
    tasks = bundle["enrichment_tasks"]
    if mutation == "missing":
        tasks.pop()
    elif mutation == "repeated_type":
        tasks[-1] = deepcopy(tasks[-2])
    else:
        tasks[-1]["task_id"] = tasks[0]["task_id"]

    with pytest.raises(ValueError, match="enrichment task"):
        validate_enrichment_tasks(bundle)


def test_stage_11_semantic_validation_rejects_schema_valid_task_tampering(
    bundle_inputs: dict[str, Any],
) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)
    bundle["enrichment_tasks"][0]["task_id"] = "0" * 64

    with pytest.raises(ValueError, match="enrichment task"):
        stage_11.validate_profile_bundles([bundle])


def test_stage_11_semantic_validation_rejects_selected_paper_identity_mismatch(
    bundle_inputs: dict[str, Any],
) -> None:
    bundle = build_openalex_bundle(**bundle_inputs)
    bundle["selected_papers"][0]["openalex_work_id"] = "W999999999"

    with pytest.raises(ValueError, match="identifiers.*same OpenAlex work"):
        stage_11.validate_profile_bundles([bundle])


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
