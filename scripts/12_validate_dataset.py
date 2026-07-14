#!/usr/bin/env python3
"""Validate expanded-benchmark configuration, schemas, directories, and optional packets."""

from __future__ import annotations

import json
from pathlib import Path

from _dataset_cli import StageSpec, build_parser, load_config, stage_plan, write_json_atomic

SPEC = StageSpec(12, "validate_dataset", __doc__, "data/final/evidence_packets", "data/final/validation_report.json", implemented_locally=True)
ROOT = Path(__file__).resolve().parents[1]


def validate_repository(config_path: str | Path, packet_input: str | Path | None) -> dict[str, object]:
    errors: list[str] = []
    checks: dict[str, object] = {}
    try:
        config = load_config(config_path)
        checks["dataset_version"] = config.get("dataset_version")
    except (OSError, ValueError, RuntimeError) as error:
        errors.append(str(error))
        config = {}

    schema_names = ["professor.schema.json", "paper.schema.json", "evidence_packet.schema.json"]
    parsed_schemas = []
    for name in schema_names:
        path = ROOT / "schemas" / name
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                errors.append(f"{name}: unexpected or missing draft declaration")
            parsed_schemas.append(name)
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{name}: {error}")
    checks["parsed_schemas"] = parsed_schemas

    required_directories = ["data/raw", "data/interim", "data/final", "data/private", "scripts"]
    missing_directories = [name for name in required_directories if not (ROOT / name).is_dir()]
    checks["required_directories"] = required_directories
    if missing_directories:
        errors.append(f"missing directories: {', '.join(missing_directories)}")

    packet_files: list[Path] = []
    if packet_input:
        candidate = Path(packet_input)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if candidate.is_dir():
            packet_files = sorted(candidate.glob("*.json"))
        elif candidate.is_file():
            packet_files = [candidate]
    packet_errors = []
    professor_ids = set()
    for path in packet_files:
        try:
            packet = json.loads(path.read_text(encoding="utf-8"))
            professor_id = packet.get("professor_id")
            if not professor_id or professor_id in professor_ids:
                packet_errors.append(f"{path}: missing or duplicate professor_id")
            professor_ids.add(professor_id)
            if len(packet.get("papers", [])) != 8:
                packet_errors.append(f"{path}: expected exactly 8 papers")
            if len(packet.get("focal_paper_ids", [])) != 2:
                packet_errors.append(f"{path}: expected exactly 2 focal_paper_ids")
        except (OSError, json.JSONDecodeError, AttributeError) as error:
            packet_errors.append(f"{path}: {error}")
    errors.extend(packet_errors)
    checks["packet_files_checked"] = len(packet_files)

    return {
        "validator_version": "dataset-validator-v1",
        "valid": not errors,
        "checks": checks,
        "errors": errors,
    }


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
    report = validate_repository(arguments.config, arguments.input)
    if arguments.output:
        write_json_atomic(arguments.output, report, force=arguments.force)
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
