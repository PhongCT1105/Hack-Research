#!/usr/bin/env python3
"""Assess within-OpenAlex metadata consistency without claiming external verification."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence
import unicodedata

from _dataset_cli import (
    StageSpec,
    build_parser,
    configure_logging,
    enforce_author_limit,
    handle_progress_action,
    log_failure,
    read_jsonl,
    stage_plan,
    write_jsonl_atomic,
)
from lib.config import DatasetConfig
from lib.normalization import canonical_openalex_id


SPEC = StageSpec(
    6,
    "reconcile_metadata",
    __doc__,
    "data/interim/author_works_with_abstracts.jsonl",
    "data/interim/reconciled_candidate_papers.jsonl",
    implemented_locally=True,
)


@dataclass(frozen=True)
class ConsistencyAssessment:
    """Profile-level findings derived only from the supplied OpenAlex records."""

    status: str
    issue_codes: tuple[str, ...]
    externally_verified: bool = False


def reconcile_openalex_records(
    records: Sequence[Mapping[str, Any]],
    *,
    expected_author_ids: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Attach profile-level within-provider findings to every supplied work."""

    records_by_profile: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        professor_id = _professor_id(record)
        if professor_id is None:
            raise ValueError("every work record must have a non-empty professor_id")
        records_by_profile.setdefault(professor_id, []).append(record)

    work_owners: dict[str, set[str]] = {}
    for professor_id, profile_records in records_by_profile.items():
        for record in profile_records:
            work_id = _canonical_work_id(record)
            if work_id is not None:
                work_owners.setdefault(work_id, set()).add(professor_id)
    overlapping_profiles = {
        professor_id
        for owners in work_owners.values()
        if len(owners) > 1
        for professor_id in owners
    }

    assessments: dict[str, tuple[str, ConsistencyAssessment]] = {}
    for professor_id, profile_records in records_by_profile.items():
        expected_author_id = (
            expected_author_ids.get(professor_id)
            if expected_author_ids is not None
            else _infer_expected_author_id(profile_records, professor_id)
        )
        if not isinstance(expected_author_id, str) or not expected_author_id.strip():
            raise ValueError(f"missing expected OpenAlex author ID for {professor_id}")
        assessment = assess_openalex_consistency(
            profile_records, expected_author_id=expected_author_id
        )
        if professor_id in overlapping_profiles:
            assessment = ConsistencyAssessment(
                status="needs_identity_review",
                issue_codes=(*assessment.issue_codes, "cross_profile_work_overlap"),
            )
        assessments[professor_id] = (expected_author_id, assessment)

    transformed: list[dict[str, Any]] = []
    metadata_issue_codes = {"conflicting_doi_titles", "duplicate_work_ids"}
    for record in records:
        professor_id = _professor_id(record)
        assert professor_id is not None
        expected_author_id, assessment = assessments[professor_id]
        updated = deepcopy(dict(record))
        updated["consistency_status"] = assessment.status
        updated["consistency_issue_codes"] = list(assessment.issue_codes)
        updated["ownership_verified"] = False
        updated["externally_verified"] = False
        updated["verification_sources"] = []
        updated["openalex_consistency"] = {
            "status": assessment.status,
            "issue_codes": list(assessment.issue_codes),
            "scope": "within_openalex",
            "expected_author_id": canonical_openalex_id(expected_author_id),
            "externally_verified": False,
        }
        updated["reconciliation"] = {
            "ownership_verified": False,
            "externally_verified": False,
            "verification_sources": [],
            "doi_verified": None,
            "title_similarity": None,
            "author_match_status": "needs_external_verification",
            "metadata_conflict": bool(metadata_issue_codes & set(assessment.issue_codes)),
        }
        transformed.append(updated)
    return transformed


def assess_openalex_consistency(
    records: Sequence[Mapping[str, Any]], *, expected_author_id: str
) -> ConsistencyAssessment:
    """Assess metadata agreement within one OpenAlex work history."""

    canonical_author_id = canonical_openalex_id(expected_author_id)
    issue_codes: list[str] = []
    if any(canonical_author_id not in _authorship_author_ids(record) for record in records):
        issue_codes.append("expected_author_missing")
    author_names: dict[str, set[str]] = {}
    for record in records:
        for author_id, author_name in _authorship_author_entries(record):
            if author_name:
                author_names.setdefault(author_id, set()).add(author_name)
    if any(len(names) > 1 for names in author_names.values()):
        issue_codes.append("inconsistent_author_entries")
    domains = [domain for record in records if (domain := _primary_domain(record))]
    if len(set(domains)) >= 3 and max(Counter(domains).values()) / len(domains) < 0.6:
        issue_codes.append("implausible_topic_mixture")

    owners_by_work: dict[str, list[str | None]] = {}
    for record in records:
        work_id = _canonical_work_id(record)
        if work_id is not None:
            owners_by_work.setdefault(work_id, []).append(_professor_id(record))
    if any(
        len(owners) > 1 and len({owner for owner in owners if owner is not None}) <= 1
        for owners in owners_by_work.values()
    ):
        issue_codes.append("duplicate_work_ids")
    if any(
        len({owner for owner in owners if owner is not None}) > 1
        for owners in owners_by_work.values()
    ):
        issue_codes.append("cross_profile_work_overlap")

    titles_by_doi: dict[str, set[str]] = {}
    for record in records:
        doi = record.get("doi")
        title = record.get("title")
        if isinstance(doi, str) and doi.strip() and isinstance(title, str) and title.strip():
            titles_by_doi.setdefault(_normalize_doi(doi), set()).add(_normalize_title(title))

    if any(len(titles) > 1 for titles in titles_by_doi.values()):
        issue_codes.append("conflicting_doi_titles")
    identity_issues = {
        "expected_author_missing",
        "inconsistent_author_entries",
        "implausible_topic_mixture",
        "cross_profile_work_overlap",
    }
    if identity_issues & set(issue_codes):
        status = "needs_identity_review"
    elif issue_codes:
        status = "needs_metadata_enrichment"
    else:
        status = "openalex_consistent"
    return ConsistencyAssessment(status=status, issue_codes=tuple(issue_codes))


def _authorship_author_ids(record: Mapping[str, Any]) -> set[str]:
    return {author_id for author_id, _ in _authorship_author_entries(record)}


def _authorship_author_entries(record: Mapping[str, Any]) -> set[tuple[str, str]]:
    entries: set[tuple[str, str]] = set()
    authorships = record.get("authorships")
    if not isinstance(authorships, (list, tuple)):
        return entries
    for authorship in authorships:
        if not isinstance(authorship, Mapping):
            continue
        author = authorship.get("author")
        if not isinstance(author, Mapping) or not isinstance(author.get("id"), str):
            continue
        author_id = canonical_openalex_id(author["id"])
        if author_id is not None:
            name = author.get("display_name")
            normalized_name = name.strip().casefold() if isinstance(name, str) else ""
            entries.add((author_id, normalized_name))
    return entries


def _canonical_work_id(record: Mapping[str, Any]) -> str | None:
    value = record.get("openalex_work_id") or record.get("id") or record.get("paper_id")
    return canonical_openalex_id(value) if isinstance(value, str) else None


def _professor_id(record: Mapping[str, Any]) -> str | None:
    value = record.get("professor_id")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _primary_domain(record: Mapping[str, Any]) -> str | None:
    primary_topic = record.get("primary_topic")
    if isinstance(primary_topic, Mapping) and isinstance(primary_topic.get("domain"), str):
        return primary_topic["domain"].strip().casefold() or None
    topics = record.get("topics")
    if not isinstance(topics, (list, tuple)):
        return None
    for topic in topics:
        if isinstance(topic, Mapping) and isinstance(topic.get("domain"), str):
            return topic["domain"].strip().casefold() or None
    return None


def _normalize_doi(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    for prefix in (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    ):
        if normalized.startswith(prefix):
            return normalized.removeprefix(prefix).strip()
    return normalized


def _normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w\s]", " ", normalized).split())


def _infer_expected_author_id(records: Sequence[Mapping[str, Any]], professor_id: str) -> str:
    declared_ids = {
        canonical_openalex_id(value)
        for record in records
        if isinstance(
            (value := record.get("profile_openalex_author_id") or record.get("openalex_author_id")),
            str,
        )
    }
    declared_ids.discard(None)
    if len(declared_ids) == 1:
        return next(iter(declared_ids))
    if len(declared_ids) > 1:
        raise ValueError(f"conflicting expected OpenAlex author IDs for {professor_id}")

    author_counts = Counter(
        author_id for record in records for author_id in _authorship_author_ids(record)
    )
    ranked_ids = author_counts.most_common()
    if not ranked_ids or (len(ranked_ids) > 1 and ranked_ids[0][1] == ranked_ids[1][1]):
        raise ValueError(
            f"cannot infer one expected OpenAlex author ID for {professor_id}; "
            "add profile_openalex_author_id to the work records"
        )
    return ranked_ids[0][0]


def _limit_records_by_profile(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected_profiles: list[str] = []
    selected_profile_set: set[str] = set()
    for record in records:
        professor_id = _professor_id(record)
        if professor_id is None:
            raise ValueError("every work record must have a non-empty professor_id")
        if professor_id not in selected_profile_set and len(selected_profiles) < limit:
            selected_profiles.append(professor_id)
            selected_profile_set.add(professor_id)
    return [record for record in records if _professor_id(record) in selected_profile_set]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(SPEC)
    arguments = parser.parse_args(argv)
    progress_result = handle_progress_action(arguments, parser)
    if progress_result is not None:
        return progress_result
    try:
        config = DatasetConfig.load(arguments.config)
        arguments.limit = enforce_author_limit(
            arguments.limit, arguments.full_run, config.safe_author_limit
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    if arguments.dry_run:
        print(json.dumps(stage_plan(SPEC, arguments, config.raw), indent=2, sort_keys=True))
        return 0
    if arguments.resume or arguments.restart:
        parser.error("Stage 6 is deterministic and does not use collection checkpoints")
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required for consistency assessment")

    logger = configure_logging(arguments.log_file)
    try:
        records = _limit_records_by_profile(read_jsonl(arguments.input), arguments.limit)
        reconciled = reconcile_openalex_records(records)
        write_jsonl_atomic(Path(arguments.output), reconciled, force=arguments.force)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        log_failure(logger, SPEC, None, error)
        parser.error(str(error))
    print(f"wrote {len(reconciled)} records to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
