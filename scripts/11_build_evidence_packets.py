#!/usr/bin/env python3
"""Build anonymous provisional OpenAlex profile bundles for later enrichment."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from _dataset_cli import (
    StageSpec,
    build_parser,
    enforce_author_limit,
    handle_progress_action,
    read_jsonl,
    stage_plan,
)
from lib.bundles import build_openalex_bundle
from lib.config import DatasetConfig
from lib.io import atomic_write_json


DEFAULT_SCHEMA = Path("schemas/openalex_profile_bundle.schema.json")
SPEC = StageSpec(
    11,
    "build_openalex_profile_bundles",
    __doc__ or "Build anonymous provisional OpenAlex profile bundles",
    "data/final/provisional_professor_bundle_inputs.jsonl",
    "data/final/openalex_profile_bundles",
    implemented_locally=True,
)


def build_profile_bundles(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build deterministic bundles from one assembled Stage 11 input record per profile."""

    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise TypeError("Stage 11 records must be a sequence of mappings")
    bundles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            raise TypeError("every Stage 11 input record must be a mapping")
        profile = record.get("profile")
        selected_papers = record.get("selected_papers")
        focal_ids = record.get("focal_ids") or record.get("focal_paper_ids")
        provenance = record.get("provenance")
        bundle = build_openalex_bundle(profile, selected_papers, focal_ids, provenance)
        professor_id = bundle["professor_id"]
        if professor_id in seen:
            raise ValueError(f"duplicate Stage 11 professor_id {professor_id}")
        seen.add(professor_id)
        bundles.append(bundle)
    return sorted(bundles, key=lambda bundle: bundle["professor_id"])


def load_bundle_validator(
    schema_path: str | Path = DEFAULT_SCHEMA,
) -> Draft202012Validator:
    """Load and check the provisional schema with JSON Schema format validation enabled."""

    path = Path(schema_path)
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_profile_bundles(
    bundles: Sequence[Mapping[str, Any]], schema_path: str | Path = DEFAULT_SCHEMA
) -> None:
    """Raise a jsonschema validation error for the first invalid provisional bundle."""

    validator = load_bundle_validator(schema_path)
    for bundle in bundles:
        validator.validate(bundle)


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
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(str(error))

    if arguments.dry_run:
        plan = stage_plan(SPEC, arguments, config.raw)
        plan.update(
            {
                "bundle_version": config.bundle_version,
                "schema": str(DEFAULT_SCHEMA),
                "schema_draft": "2020-12",
                "output_contract": "anonymous_provisional_openalex_profile_bundles",
                "final_evidence_packet_ready": False,
            }
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if arguments.resume or arguments.restart:
        parser.error("Stage 11 is deterministic and does not use collection checkpoints")
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required for profile bundle construction")

    try:
        records = read_jsonl(arguments.input)
        bundles = build_profile_bundles(records[: arguments.limit])
        validate_profile_bundles(bundles)
        output_dir = Path(arguments.output)
        for bundle in bundles:
            atomic_write_json(
                output_dir / f"{bundle['professor_id']}.json",
                bundle,
                force=arguments.force,
            )
    except (
        OSError,
        RuntimeError,
        SchemaError,
        TypeError,
        ValidationError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        parser.error(str(error))
    print(f"wrote {len(bundles)} provisional profile bundles to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
