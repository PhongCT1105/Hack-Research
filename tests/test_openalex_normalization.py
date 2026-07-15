from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.lib.normalization import (  # noqa: E402
    AUTHOR_CANDIDATE_CSV_COLUMNS,
    CANDIDATE_PAPER_CSV_COLUMNS,
    INSTITUTION_CSV_COLUMNS,
    author_candidate_status,
    canonical_openalex_id,
    normalize_author,
    normalize_institution,
    normalize_work,
)


FIXTURES = Path(__file__).parent / "fixtures" / "openalex"


@pytest.fixture
def author_fixtures() -> list[dict[str, object]]:
    return json.loads((FIXTURES / "authors_page.json").read_text(encoding="utf-8"))["results"]


@pytest.fixture
def work_fixtures() -> list[dict[str, object]]:
    return json.loads((FIXTURES / "works_page.json").read_text(encoding="utf-8"))["results"]


def test_csv_columns_are_stable_dataset_policy_contracts() -> None:
    assert INSTITUTION_CSV_COLUMNS == (
        "institution_id",
        "openalex_id",
        "ror_id",
        "name",
        "country",
        "region",
        "institution_type",
        "works_count",
        "cited_by_count",
        "homepage_url",
    )
    assert AUTHOR_CANDIDATE_CSV_COLUMNS == (
        "openalex_author_id",
        "display_name",
        "orcid",
        "last_known_institution",
        "works_count",
        "cited_by_count",
        "h_index",
        "first_publication_year",
        "last_publication_year",
        "primary_domain",
        "primary_field",
        "primary_subfield",
        "candidate_status",
    )
    assert CANDIDATE_PAPER_CSV_COLUMNS == (
        "professor_id",
        "paper_id",
        "openalex_work_id",
        "doi",
        "title",
        "publication_year",
        "venue",
        "citation_count",
        "citation_percentile_field_year",
        "abstract_available",
        "full_text_available",
        "open_access",
        "topic_ids",
        "primary_topic",
        "method_tags",
        "complexity_score",
        "complexity_tier",
        "selected",
        "selection_reason",
        "focal",
        "ownership_verified",
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://openalex.org/W100000001", "W100000001"),
        ("https://openalex.org/A100000001/", "A100000001"),
        ("https://api.openalex.org/works/W100000001?select=id", "W100000001"),
        ("I100000001", "I100000001"),
        (None, None),
    ],
)
def test_canonical_openalex_id_accepts_provider_urls_and_short_ids(
    value: str | None, expected: str | None
) -> None:
    assert canonical_openalex_id(value) == expected


def test_institution_normalization_preserves_provider_url_and_missingness() -> None:
    raw = {
        "id": "https://openalex.org/I100000001",
        "display_name": "Synthetic Northern Institute",
        "country_code": "CA",
        "geo": {"region": "North America"},
        "type": "education",
        "works_count": 20,
        "cited_by_count": 40,
        "homepage_url": None,
        "ror": None,
        "lineage": ["https://openalex.org/I100000001"],
    }
    before = copy.deepcopy(raw)

    institution = normalize_institution(raw, institution_id="MOCK-INST-01")

    assert institution["institution_id"] == "MOCK-INST-01"
    assert institution["openalex_id"] == "I100000001"
    assert institution["openalex_url"] == "https://openalex.org/I100000001"
    assert institution["region"] == "North America"
    assert institution["ror_id"] is None
    assert institution["homepage_url"] is None
    assert institution["lineage"] == ["I100000001"]
    assert institution["lineage_urls"] == ["https://openalex.org/I100000001"]
    assert raw == before


def test_author_normalization_preserves_evidence_and_uses_summary_years(
    author_fixtures: list[dict[str, object]],
) -> None:
    raw = author_fixtures[0]
    before = copy.deepcopy(raw)

    author = normalize_author(raw)

    assert author["openalex_author_id"] == "A100000001"
    assert author["openalex_author_url"] == "https://openalex.org/A100000001"
    assert author["orcid"] == "https://orcid.org/0000-0001-0000-0001"
    assert author["h_index"] == 7
    assert author["first_publication_year"] == 2013
    assert author["last_publication_year"] == 2024
    assert author["last_known_institution"] == "Synthetic Northern Institute"
    assert author["last_known_institutions"][0]["id"] == "I100000001"
    assert author["last_known_institutions"][0]["openalex_url"] == "https://openalex.org/I100000001"
    assert author["topics"][0]["topic"] == "Synthetic Language Models"
    assert author["topics"][0]["subfield"] == "Artificial Intelligence"
    assert author["topics"][0]["field"] == "Computer Science"
    assert author["topics"][0]["domain"] == "Physical Sciences"
    assert author["candidate_status"] == "eligible"
    assert author["faculty_status_verified"] is False
    assert author["quality_status"] == "needs_enrichment"
    assert raw == before


def test_author_years_ignore_zero_work_summary_rows(
    author_fixtures: list[dict[str, object]],
) -> None:
    raw = copy.deepcopy(author_fixtures[0])
    raw["counts_by_year"] = [
        {"year": 1999, "works_count": 0},
        {"year": 2020, "works_count": 1},
        {"year": 2025, "works_count": 2},
    ]
    raw["works"] = [{"publication_year": 1980}]

    author = normalize_author(raw)

    assert author["first_publication_year"] == 2020
    assert author["last_publication_year"] == 2025


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "eligible"),
        ({"works_count": 7}, "ineligible_insufficient_works"),
        ({"last_publication_year": 2020}, "ineligible_no_recent_activity"),
        ({"last_known_institutions": []}, "ineligible_no_institution"),
        ({"topics": []}, "ineligible_no_topics"),
    ],
)
def test_author_candidate_status_reports_first_observable_screening_failure(
    overrides: dict[str, object], expected: str
) -> None:
    candidate = {
        "works_count": 8,
        "last_publication_year": 2024,
        "last_known_institutions": [{"id": "I100000001"}],
        "topics": [{"topic_id": "T100000001"}],
        **overrides,
    }

    assert author_candidate_status(candidate, recent_activity_year=2021) == expected


def test_author_normalization_retains_empty_collections_and_null_scalars(
    author_fixtures: list[dict[str, object]],
) -> None:
    author = normalize_author(author_fixtures[1])

    assert author["orcid"] is None
    assert author["h_index"] is None
    assert author["first_publication_year"] is None
    assert author["last_publication_year"] is None
    assert author["last_known_institutions"] == []
    assert author["affiliations"] == []
    assert author["topics"] == []
    assert author["topic_share"] == []
    assert author["counts_by_year"] == []
    assert author["candidate_status"] == "ineligible_insufficient_works"


def test_work_normalization_preserves_complete_evidence_fields(
    work_fixtures: list[dict[str, object]],
) -> None:
    raw = work_fixtures[0]
    before = copy.deepcopy(raw)

    work = normalize_work(raw, professor_id="MOCK-01")

    assert work["professor_id"] == "MOCK-01"
    assert work["paper_id"] == "W100000001"
    assert work["openalex_work_id"] == "W100000001"
    assert work["openalex_work_url"] == "https://openalex.org/W100000001"
    assert work["abstract_inverted_index"] == {"Synthetic": [0], "abstract": [1]}
    assert work["topics"][0]["field"] == "Computer Science"
    assert work["topics"][0]["field_id"] == "17"
    assert work["topics"][0]["field_url"] == "https://openalex.org/fields/17"
    assert work["authorships"][0]["author_position"] == "first"
    assert work["authorships"][0]["author"]["id"] == "A100000001"
    assert work["authorships"][0]["author"]["openalex_url"] == "https://openalex.org/A100000001"
    assert work["authorships"][0]["institutions"][0]["id"] == "I100000001"
    assert work["referenced_works"] == ["W100000099"]
    assert work["referenced_work_urls"] == ["https://openalex.org/W100000099"]
    assert work["related_works"] == ["W100000098"]
    assert work["locations"][0]["pdf_url"].endswith("synthetic.1.pdf")
    assert work["best_oa_location"]["license"] == "cc-by"
    assert work["open_access"]["oa_status"] == "gold"
    assert work["venue"] == "Journal of Synthetic Evidence"
    assert work["is_retracted"] is False
    assert raw == before


def test_work_normalization_canonicalizes_nested_openalex_identifier_fields(
    work_fixtures: list[dict[str, object]],
) -> None:
    work = normalize_work(work_fixtures[0], professor_id="MOCK-01")

    assert work["ids"]["openalex"] == "W100000001"
    assert work["ids"]["openalex_url"] == "https://openalex.org/W100000001"
    assert work["corresponding_author_ids"] == ["A100000001"]
    assert work["corresponding_author_urls"] == ["https://openalex.org/A100000001"]
    assert work["corresponding_institution_ids"] == ["I100000001"]
    assert work["corresponding_institution_urls"] == ["https://openalex.org/I100000001"]
    source = work["primary_location"]["source"]
    assert source["host_organization"] == "I100000001"
    assert source["host_organization_url"] == "https://openalex.org/I100000001"
    assert source["host_organization_lineage"] == ["I100000001"]
    assert source["host_organization_lineage_urls"] == ["https://openalex.org/I100000001"]
    institution = work["authorships"][0]["institutions"][0]
    assert institution["lineage"] == ["I100000001"]
    assert institution["lineage_urls"] == ["https://openalex.org/I100000001"]
    affiliation = work["authorships"][0]["affiliations"][0]
    assert affiliation["institution_ids"] == ["I100000001"]
    assert affiliation["institution_urls"] == ["https://openalex.org/I100000001"]
    assert work["grants"][0]["funder"] == "F100000001"
    assert work["grants"][0]["funder_url"] == "https://openalex.org/F100000001"


def test_work_normalization_retains_empty_collections_and_null_scalars(
    work_fixtures: list[dict[str, object]],
) -> None:
    work = normalize_work(work_fixtures[1], professor_id="MOCK-02")

    assert work["doi"] is None
    assert work["title"] is None
    assert work["publication_year"] is None
    assert work["primary_location"] is None
    assert work["best_oa_location"] is None
    assert work["open_access"] is None
    assert work["abstract_inverted_index"] is None
    assert work["authorships"] == []
    assert work["locations"] == []
    assert work["topics"] == []
    assert work["keywords"] == []
    assert work["referenced_works"] == []
    assert work["related_works"] == []
    assert work["counts_by_year"] == []
