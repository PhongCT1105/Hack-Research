#!/usr/bin/env python3
"""Build the anonymous faculty-identity enrichment queue for human review."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

from _dataset_cli import (
    StageSpec,
    build_parser,
    enforce_author_limit,
    handle_progress_action,
    stage_plan,
)
from lib.config import DatasetConfig
from lib.io import atomic_write_csv, read_csv
from lib.normalization import canonical_openalex_id


QUEUE_COLUMNS = (
    "professor_id",
    "openalex_author_id",
    "openalex_author_url",
    "orcid",
    "last_known_institution",
    "discovery_institution_ids",
    "works_count",
    "cited_by_count",
    "h_index",
    "first_publication_year",
    "last_publication_year",
    "primary_domain",
    "primary_field",
    "primary_subfield",
    "candidate_status",
    "faculty_status_verified",
    "faculty_page_url",
    "faculty_title",
    "faculty_page_retrieved_at",
    "career_stage",
    "career_stage_source",
    "suspected_identity_issue",
    "identity_notes",
    "quality_status",
)
IDENTITY_MAP_COLUMNS = ("professor_id", "openalex_author_id", "display_name")
SPEC = StageSpec(
    3,
    "verify_faculty_status",
    __doc__ or "Build the faculty identity enrichment queue",
    "data/interim/author_candidates.csv",
    "data/interim/faculty_identity_enrichment_queue.csv",
    implemented_locally=True,
)


def build_enrichment_queue(
    candidate_rows: Sequence[Mapping[str, Any]],
    candidate_pool_version: str,
) -> list[dict[str, str]]:
    """Return a deterministic, name-free queue of eligible candidates."""

    assignments = _anonymous_id_assignments(candidate_rows, candidate_pool_version)
    queue: list[dict[str, str]] = []
    rows_by_id = _eligible_rows_by_id(candidate_rows)
    for author_id, professor_id in sorted(assignments.items(), key=lambda item: item[1]):
        candidate = rows_by_id[author_id]
        queue.append(
            {
                "professor_id": professor_id,
                "openalex_author_id": author_id,
                "openalex_author_url": f"https://openalex.org/{author_id}",
                "orcid": _csv_scalar(candidate.get("orcid")),
                "last_known_institution": _csv_scalar(candidate.get("last_known_institution")),
                "discovery_institution_ids": _csv_scalar(
                    candidate.get("discovery_institution_ids")
                ),
                "works_count": _csv_scalar(candidate.get("works_count")),
                "cited_by_count": _csv_scalar(candidate.get("cited_by_count")),
                "h_index": _csv_scalar(candidate.get("h_index")),
                "first_publication_year": _csv_scalar(candidate.get("first_publication_year")),
                "last_publication_year": _csv_scalar(candidate.get("last_publication_year")),
                "primary_domain": _csv_scalar(candidate.get("primary_domain")),
                "primary_field": _csv_scalar(candidate.get("primary_field")),
                "primary_subfield": _csv_scalar(candidate.get("primary_subfield")),
                "candidate_status": "eligible",
                "faculty_status_verified": "false",
                "faculty_page_url": "",
                "faculty_title": "",
                "faculty_page_retrieved_at": "",
                "career_stage": "",
                "career_stage_source": "",
                "suspected_identity_issue": "",
                "identity_notes": "",
                "quality_status": "needs_enrichment",
            }
        )
    return queue


def write_enrichment_queue(
    candidate_rows: Sequence[Mapping[str, Any]],
    candidate_pool_version: str,
    output_path: str | Path,
    identity_map_path: str | Path,
    *,
    force: bool = False,
) -> list[dict[str, str]]:
    """Write the public/provisional queue and separate private identity mapping."""

    queue = build_enrichment_queue(candidate_rows, candidate_pool_version)
    assignments = {row["openalex_author_id"]: row["professor_id"] for row in queue}
    rows_by_id = _eligible_rows_by_id(candidate_rows)
    identity_rows = [
        {
            "professor_id": assignments[author_id],
            "openalex_author_id": author_id,
            "display_name": _csv_scalar(rows_by_id[author_id].get("display_name")),
        }
        for author_id in sorted(assignments, key=lambda value: assignments[value])
    ]
    atomic_write_csv(output_path, queue, fieldnames=QUEUE_COLUMNS, force=force)
    atomic_write_csv(
        identity_map_path,
        identity_rows,
        fieldnames=IDENTITY_MAP_COLUMNS,
        force=force,
    )
    return queue


def _eligible_rows_by_id(
    candidate_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    rows_by_id: dict[str, Mapping[str, Any]] = {}
    for candidate in candidate_rows:
        if candidate.get("candidate_status") != "eligible":
            continue
        author_id = _author_id(candidate.get("openalex_author_id"))
        if author_id in rows_by_id:
            raise ValueError(f"duplicate OpenAlex author ID: {author_id}")
        rows_by_id[author_id] = candidate
    return rows_by_id


def _anonymous_id_assignments(
    candidate_rows: Sequence[Mapping[str, Any]],
    candidate_pool_version: str,
) -> dict[str, str]:
    if not isinstance(candidate_pool_version, str) or not candidate_pool_version.strip():
        raise ValueError("candidate pool version must be a non-empty string")
    rows_by_id = _eligible_rows_by_id(candidate_rows)
    grouped: dict[str, list[str]] = defaultdict(list)
    for author_id, candidate in rows_by_id.items():
        grouped[_domain_prefix(candidate)].append(author_id)

    assignments: dict[str, str] = {}
    for prefix in sorted(grouped):
        ranked = sorted(
            grouped[prefix],
            key=lambda author_id: (
                hashlib.sha256(
                    f"{candidate_pool_version}\0{author_id}".encode("utf-8")
                ).hexdigest(),
                author_id,
            ),
        )
        for rank, author_id in enumerate(ranked, start=1):
            assignments[author_id] = f"{prefix}-{rank:03d}"
    return assignments


def _author_id(value: Any) -> str:
    try:
        author_id = canonical_openalex_id(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid OpenAlex author ID: {value!r}") from error
    if author_id is None or re.fullmatch(r"A\d+", author_id) is None:
        raise ValueError(f"invalid OpenAlex author ID: {value!r}")
    return author_id


def _domain_prefix(candidate: Mapping[str, Any]) -> str:
    classification = " ".join(
        _csv_scalar(candidate.get(field)).lower()
        for field in ("primary_field", "primary_subfield", "primary_domain")
    )
    if any(term in classification for term in ("computer", "engineering")):
        return "CS"
    if any(
        term in classification
        for term in ("medicine", "medical", "health", "biolog", "neuroscience")
    ):
        return "BIO"
    if any(term in classification for term in ("psycholog", "cognitive")):
        return "PSY"
    if any(
        term in classification
        for term in ("physical", "physics", "mathemat", "chemistry", "astronom")
    ):
        return "PHY"
    return "SSH"


def _csv_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _option_supplied(argv: Sequence[str], option: str) -> bool:
    return any(argument == option or argument.startswith(f"{option}=") for argument in argv)


def _resolve_stage_paths(arguments: Any, config: DatasetConfig, argv: Sequence[str]) -> None:
    paths = config.raw.get("paths", {})
    if not isinstance(paths, Mapping):
        return
    if not _option_supplied(argv, "--output"):
        arguments.output = str(
            Path(paths.get("interim", "data/interim")) / "faculty_identity_enrichment_queue.csv"
        )
    if not _option_supplied(argv, "--state-dir"):
        arguments.state_dir = str(paths.get("progress", "data/raw/progress"))


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(SPEC)
    arguments = parser.parse_args(raw_argv)
    try:
        config = DatasetConfig.load(arguments.config)
        _resolve_stage_paths(arguments, config, raw_argv)
        progress_result = handle_progress_action(arguments, parser)
        if progress_result is not None:
            return progress_result
        arguments.limit = enforce_author_limit(
            arguments.limit, arguments.full_run, config.safe_author_limit
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))

    if arguments.dry_run:
        print(json.dumps(stage_plan(SPEC, arguments, config.raw), indent=2, sort_keys=True))
        return 0
    if arguments.restart or arguments.resume:
        parser.error("Stage 3 is deterministic and does not use collection checkpoints")

    try:
        candidates = read_csv(arguments.input)[: arguments.limit]
        privacy = config.raw.get("privacy", {})
        configured_map = (
            privacy.get("identity_map", "data/private/professor_identity_map.csv")
            if isinstance(privacy, Mapping)
            else "data/private/professor_identity_map.csv"
        )
        write_enrichment_queue(
            candidates,
            config.candidate_pool_version,
            arguments.output,
            configured_map,
            force=arguments.force,
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
