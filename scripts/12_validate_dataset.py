#!/usr/bin/env python3
"""Validate the local OpenAlex collection without promoting it to a final evidence dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
import yaml

from _dataset_cli import (
    StageSpec,
    build_parser,
    handle_progress_action,
    load_config,
    stage_plan,
    write_json_atomic,
)
from lib.io import _atomic_text_write
from lib.validation import (
    FINAL_BLOCKERS,
    VALIDATOR_VERSION,
    build_manifest,
    scan_public_artifacts,
    validate_openalex_collection,
    validate_provisional_bundles,
)


SPEC = StageSpec(
    12,
    "validate_dataset",
    __doc__ or "Validate the provisional OpenAlex dataset",
    "data/final/openalex_profile_bundles",
    "data/final/validation_report.json",
    implemented_locally=True,
)
ROOT = Path(__file__).resolve().parents[1]


def validate_dataset(
    dataset_root: str | Path,
    bundle_dir: str | Path | None = None,
    *,
    schema_path: str | Path | None = None,
    tracked_files: Sequence[str | Path] | None = None,
    manifest_template: str | Path | None = None,
) -> dict[str, Any]:
    """Return separate OpenAlex, provisional-bundle, and strict-final validation states."""

    root = Path(dataset_root).resolve()
    collection = validate_openalex_collection(root)
    bundles = validate_provisional_bundles(root, bundle_dir, schema_path)
    public_scan = scan_public_artifacts(root, tracked_files=tracked_files)
    schema_errors = _validate_schema_documents(root)
    if schema_errors:
        bundles["valid"] = False
        bundles["errors"] = [*bundles["errors"], *schema_errors]
        bundles["checks"]["schema_validation"] = False

    manifest = build_manifest(
        root,
        collection,
        bundles,
        public_scan,
        template_path=manifest_template,
    )
    openalex_collection_valid = bool(collection["valid"] and public_scan["valid"])
    provisional_bundle_valid = bool(bundles["valid"] and public_scan["valid"])
    return {
        "validator_version": VALIDATOR_VERSION,
        "openalex_collection_valid": openalex_collection_valid,
        "provisional_bundle_valid": provisional_bundle_valid,
        "final_evidence_packet_ready": False,
        "final_blockers": list(FINAL_BLOCKERS),
        "collection": collection,
        "provisional_bundles": bundles,
        "public_artifacts": public_scan,
        "errors": [*collection["errors"], *bundles["errors"], *public_scan["errors"]],
        "manifest": manifest,
    }


def validate_repository(config_path: str | Path, packet_input: str | Path | None) -> dict[str, Any]:
    """Compatibility wrapper for callers of the former Stage 12 scaffold."""

    config = Path(config_path).resolve()
    root = config.parent.parent
    return validate_dataset(root, bundle_dir=packet_input)


def _validate_schema_documents(root: Path) -> list[str]:
    schema_root = root / "schemas"
    if not schema_root.is_dir():
        schema_root = ROOT / "schemas"
    required = {
        "professor.schema.json",
        "paper.schema.json",
        "evidence_packet.schema.json",
        "openalex_profile_bundle.schema.json",
    }
    errors: list[str] = []
    paths = {path.name: path for path in schema_root.glob("*.schema.json")}
    for missing in sorted(required - set(paths)):
        errors.append(f"schema file is missing: {missing}")
    for name, path in sorted(paths.items()):
        try:
            schema = json.loads(path.read_text(encoding="utf-8"))
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                raise ValueError("unexpected or missing Draft 2020-12 declaration")
            Draft202012Validator.check_schema(schema)
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            SchemaError,
            ValueError,
        ) as error:
            errors.append(f"schema {name}: {error}")
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(SPEC)
    arguments = parser.parse_args(argv)
    progress_result = handle_progress_action(arguments, parser)
    if progress_result is not None:
        return progress_result
    try:
        config = load_config(arguments.config)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    if arguments.dry_run:
        plan = stage_plan(SPEC, arguments, config)
        plan.update(
            {
                "validator_version": VALIDATOR_VERSION,
                "release_boundary": "provisional_openalex_collection",
                "final_evidence_packet_ready": False,
            }
        )
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    try:
        report = validate_dataset(ROOT, bundle_dir=arguments.input)
        if arguments.output:
            write_json_atomic(arguments.output, report, force=arguments.force)
            manifest_path = Path(arguments.output).with_name("dataset_manifest.yaml")
            manifest_text = yaml.safe_dump(report["manifest"], sort_keys=False)
            _atomic_text_write(manifest_path, manifest_text, arguments.force)
        else:
            print(json.dumps(report, indent=2, sort_keys=True))
    except (OSError, RuntimeError, TypeError, ValueError, yaml.YAMLError) as error:
        parser.error(str(error))
    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
