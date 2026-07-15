#!/usr/bin/env python3
"""Reconstruct OpenAlex abstracts from inverted indexes without changing raw records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from _dataset_cli import (
    ABSTRACT_RECONSTRUCTION_VERSION,
    StageSpec,
    build_parser,
    configure_logging,
    enforce_author_limit,
    handle_progress_action,
    log_failure,
    read_jsonl,
    reconstruct_abstract,
    stage_plan,
    write_jsonl_atomic,
)
from lib.config import DatasetConfig

SPEC = StageSpec(
    5,
    "reconstruct_abstracts",
    __doc__,
    "data/raw/author_works.jsonl",
    "data/interim/author_works_with_abstracts.jsonl",
    implemented_locally=True,
)


def reconstruct_work_abstracts(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add deterministic abstract text while retaining each source record and index."""

    transformed: list[dict[str, Any]] = []
    for record in records:
        updated = dict(record)
        updated["reconstructed_abstract"] = reconstruct_abstract(
            record.get("abstract_inverted_index")
        )
        updated["abstract_reconstruction_version"] = ABSTRACT_RECONSTRUCTION_VERSION
        transformed.append(updated)
    return transformed


def _limit_records_by_author(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected_authors: set[str] = set()
    for record in records:
        professor_id = record.get("professor_id")
        if not isinstance(professor_id, str) or not professor_id.strip():
            raise ValueError("every work record must have a non-empty professor_id")
        if len(selected_authors) < limit:
            selected_authors.add(professor_id)
    return [record for record in records if record["professor_id"] in selected_authors]


def main(argv: list[str] | None = None) -> int:
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
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    if arguments.dry_run:
        print(json.dumps(stage_plan(SPEC, arguments, config.raw), indent=2, sort_keys=True))
        return 0
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required for reconstruction")
    if arguments.resume or arguments.restart:
        parser.error("Stage 5 is deterministic and does not use collection checkpoints")
    logger = configure_logging(arguments.log_file)
    try:
        records = _limit_records_by_author(read_jsonl(arguments.input), arguments.limit)
        transformed = reconstruct_work_abstracts(records)
        write_jsonl_atomic(Path(arguments.output), transformed, force=arguments.force)
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as error:
        log_failure(logger, SPEC, None, error)
        parser.error(str(error))
    print(f"wrote {len(transformed)} records to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
