from __future__ import annotations

import importlib
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

stage_06 = importlib.import_module("06_reconcile_metadata")


def work(
    work_id: str,
    *,
    doi: str | None = None,
    title: str | None = None,
    author_id: str = "A100000001",
    author_name: str = "Ada Synthetic",
    domain: str | None = None,
    professor_id: str = "MOCK-01",
    profile_author_id: str = "A100000001",
) -> dict[str, Any]:
    return {
        "professor_id": professor_id,
        "openalex_author_id": profile_author_id,
        "openalex_work_id": work_id,
        "doi": doi,
        "title": title or f"Synthetic work {work_id}",
        "authorships": [
            {
                "author": {
                    "id": author_id,
                    "display_name": author_name,
                }
            }
        ],
        "topics": [] if domain is None else [{"domain": domain}],
    }


def test_conflicting_doi_titles_need_metadata_enrichment() -> None:
    rows = [
        work("W1", doi="10.1/mock", title="First"),
        work("W2", doi="10.1/mock", title="Other"),
    ]

    result = stage_06.assess_openalex_consistency(rows, expected_author_id="A100000001")

    assert result.status == "needs_metadata_enrichment"
    assert "conflicting_doi_titles" in result.issue_codes
    assert result.externally_verified is False


def test_equivalent_title_variants_do_not_create_a_conflict() -> None:
    result = stage_06.assess_openalex_consistency(
        [
            work("W1", doi="10.1/mock", title="A Synthetic Study"),
            work("W2", doi="10.1/mock", title="a synthetic study!"),
        ],
        expected_author_id="A100000001",
    )

    assert result.status == "openalex_consistent"
    assert result.issue_codes == ()


def test_doi_url_and_bare_doi_are_compared_as_the_same_identifier() -> None:
    result = stage_06.assess_openalex_consistency(
        [
            work("W1", doi="https://doi.org/10.1/mock", title="First"),
            work("W2", doi="10.1/mock", title="Other"),
        ],
        expected_author_id="A100000001",
    )

    assert result.status == "needs_metadata_enrichment"
    assert result.issue_codes == ("conflicting_doi_titles",)


def test_missing_expected_author_needs_identity_review() -> None:
    result = stage_06.assess_openalex_consistency(
        [work("W1", author_id="A999999999")],
        expected_author_id="https://openalex.org/A100000001",
    )

    assert result.status == "needs_identity_review"
    assert result.issue_codes == ("expected_author_missing",)


def test_duplicate_work_ids_need_metadata_enrichment() -> None:
    result = stage_06.assess_openalex_consistency(
        [work("https://openalex.org/W1"), work("W1")],
        expected_author_id="A100000001",
    )

    assert result.status == "needs_metadata_enrichment"
    assert result.issue_codes == ("duplicate_work_ids",)


def test_inconsistent_expected_author_entries_need_identity_review() -> None:
    result = stage_06.assess_openalex_consistency(
        [work("W1"), work("W2", author_name="Someone Else")],
        expected_author_id="A100000001",
    )

    assert result.status == "needs_identity_review"
    assert result.issue_codes == ("inconsistent_author_entries",)


def test_implausibly_mixed_profile_topics_need_identity_review() -> None:
    rows = [
        work("W1", domain="Physical Sciences"),
        work("W2", domain="Health Sciences"),
        work("W3", domain="Social Sciences"),
        work("W4", domain="Life Sciences"),
    ]

    result = stage_06.assess_openalex_consistency(rows, expected_author_id="A100000001")

    assert result.status == "needs_identity_review"
    assert result.issue_codes == ("implausible_topic_mixture",)


def test_work_overlap_across_profiles_needs_identity_review() -> None:
    result = stage_06.assess_openalex_consistency(
        [work("W1"), work("W1", professor_id="MOCK-02")],
        expected_author_id="A100000001",
    )

    assert result.status == "needs_identity_review"
    assert result.issue_codes == ("cross_profile_work_overlap",)


def test_reconciliation_adds_provisional_profile_fields_to_every_work() -> None:
    rows = [work("W1"), work("W2")]
    original = deepcopy(rows)

    reconciled = stage_06.reconcile_openalex_records(
        rows, expected_author_ids={"MOCK-01": "A100000001"}
    )

    assert rows == original
    assert [row["consistency_status"] for row in reconciled] == [
        "openalex_consistent",
        "openalex_consistent",
    ]
    assert all(row["consistency_issue_codes"] == [] for row in reconciled)
    assert all(row["openalex_consistency"]["scope"] == "within_openalex" for row in reconciled)
    assert all(row["ownership_verified"] is False for row in reconciled)
    assert all(row["externally_verified"] is False for row in reconciled)
    assert all(row["verification_sources"] == [] for row in reconciled)
    assert all(
        row["reconciliation"]
        == {
            "ownership_verified": False,
            "externally_verified": False,
            "verification_sources": [],
            "doi_verified": None,
            "title_similarity": None,
            "author_match_status": "needs_external_verification",
            "metadata_conflict": False,
        }
        for row in reconciled
    )


def test_reconciliation_marks_overlap_on_each_affected_profile() -> None:
    rows = [
        work("W1", professor_id="MOCK-01", author_id="A100000001"),
        work(
            "W1",
            professor_id="MOCK-02",
            author_id="A200000002",
            profile_author_id="A200000002",
        ),
    ]

    reconciled = stage_06.reconcile_openalex_records(
        rows,
        expected_author_ids={
            "MOCK-01": "A100000001",
            "MOCK-02": "A200000002",
        },
    )

    assert all(row["consistency_status"] == "needs_identity_review" for row in reconciled)
    assert all(
        row["consistency_issue_codes"] == ["cross_profile_work_overlap"] for row in reconciled
    )


def test_stage_4_shaped_rows_use_target_id_when_coauthor_is_more_frequent() -> None:
    rows = [
        work("W1"),
        work("W2"),
        work("W3", author_id="A999999999", author_name="Frequent Coauthor"),
    ]
    for row in rows[:2]:
        row["authorships"].append(
            {"author": {"id": "A999999999", "display_name": "Frequent Coauthor"}}
        )

    reconciled = stage_06.reconcile_openalex_records(rows)

    assert all(row["consistency_status"] == "needs_identity_review" for row in reconciled)
    assert all(row["consistency_issue_codes"] == ["expected_author_missing"] for row in reconciled)
    assert all(
        row["openalex_consistency"]["expected_author_id"] == "A100000001" for row in reconciled
    )


def test_reconciliation_rejects_group_without_authoritative_author_id() -> None:
    rows = [work("W1"), work("W2")]
    for row in rows:
        row.pop("openalex_author_id")

    with pytest.raises(
        ValueError,
        match="missing authoritative OpenAlex author ID for MOCK-01",
    ):
        stage_06.reconcile_openalex_records(rows)


def test_reconciliation_rejects_conflicting_authoritative_author_ids() -> None:
    rows = [work("W1"), work("W2", profile_author_id="A200000002")]

    with pytest.raises(
        ValueError,
        match="conflicting authoritative OpenAlex author IDs for MOCK-01",
    ):
        stage_06.reconcile_openalex_records(rows)


def test_stage_6_cli_writes_offline_provisional_records(tmp_path: Path) -> None:
    input_path = tmp_path / "works.jsonl"
    output_path = tmp_path / "reconciled.jsonl"
    input_path.write_text(
        "".join(f"{json.dumps(row)}\n" for row in [work("W1"), work("W2")]),
        encoding="utf-8",
    )

    result = stage_06.main(
        [
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--limit",
            "1",
            "--log-file",
            str(tmp_path / "stage-6.log"),
        ]
    )

    assert result == 0
    written = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert len(written) == 2
    assert all(row["consistency_status"] == "openalex_consistent" for row in written)
