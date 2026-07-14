#!/usr/bin/env python3
"""Reconstruct OpenAlex abstracts from inverted indexes without changing raw records."""

from __future__ import annotations

import json
from pathlib import Path

from _dataset_cli import (
    ABSTRACT_RECONSTRUCTION_VERSION,
    StageSpec,
    build_parser,
    configure_logging,
    load_config,
    log_failure,
    read_jsonl,
    reconstruct_abstract,
    stage_plan,
    write_jsonl_atomic,
)

SPEC = StageSpec(5, "reconstruct_abstracts", __doc__, "data/raw/author_works.jsonl", "data/interim/author_works_with_abstracts.jsonl", implemented_locally=True)


def main() -> int:
    parser = build_parser(SPEC)
    arguments = parser.parse_args()
    try:
        config = load_config(arguments.config)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    if arguments.dry_run:
        print(json.dumps(stage_plan(SPEC, arguments, config), indent=2, sort_keys=True))
        return 0
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required for reconstruction")
    logger = configure_logging(arguments.log_file)
    try:
        records = read_jsonl(arguments.input)
        transformed = []
        for record in records:
            updated = dict(record)
            updated["reconstructed_abstract"] = reconstruct_abstract(record.get("abstract_inverted_index"))
            updated["abstract_reconstruction_version"] = ABSTRACT_RECONSTRUCTION_VERSION
            transformed.append(updated)
        write_jsonl_atomic(Path(arguments.output), transformed, force=arguments.force)
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as error:
        log_failure(logger, SPEC, None, error)
        parser.error(str(error))
    print(f"wrote {len(transformed)} records to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
