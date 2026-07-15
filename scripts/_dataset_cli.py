"""Shared safe CLI behavior for expanded-benchmark collection stages."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCAFFOLD_VERSION = "dataset-cli-v2"
ABSTRACT_RECONSTRUCTION_VERSION = "openalex-inverted-index-v1"


@dataclass(frozen=True)
class StageSpec:
    number: int
    name: str
    description: str
    default_input: str | None
    default_output: str | None
    network_provider: str | None = None
    supports_seed: bool = False
    implemented_locally: bool = False


def build_parser(spec: StageSpec) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=spec.description,
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--config", default="config/dataset.yaml", help="Dataset YAML configuration")
    parser.add_argument("--input", default=spec.default_input, help="Input file or directory")
    parser.add_argument("--output", default=spec.default_output, help="Output file or directory")
    parser.add_argument("--cache-dir", default="data/raw/cache", help="HTTP response cache directory")
    parser.add_argument("--log-file", default="logs/dataset_collection.log", help="Structured failure log")
    parser.add_argument(
        "--state-dir",
        default="data/raw/progress",
        help="Local per-command progress checkpoint directory",
    )
    parser.add_argument(
        "--resume", action="store_true", help="Resume the matching incomplete collection job"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print a saved job's current profile/cursor and resume command",
    )
    parser.add_argument(
        "--job-id", default=None, help="Saved progress job ID used with --status or explicit resume"
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Start a new attempt; requires --force and preserves prior raw data",
    )
    parser.add_argument("--seed", type=int, default=None, help="Deterministic random seed")
    parser.add_argument("--dry-run", action="store_true", help="Print a deterministic execution plan without network calls or writes")
    parser.add_argument("--force", action="store_true", help="Permit replacing a derived output; raw data must use a new versioned path")
    parser.add_argument("--version", action="version", version=SCAFFOLD_VERSION)
    return parser


def load_config(path: str | Path) -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as error:
        raise RuntimeError('PyYAML is required; install project dependencies with pip install -e ".[dev]"') from error
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(f"configuration not found: {config_path}")
    loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"configuration must contain a YAML mapping: {config_path}")
    return loaded


def resolved_seed(arguments: argparse.Namespace, config: Mapping[str, Any]) -> int:
    return int(arguments.seed if arguments.seed is not None else config.get("random_seed", 42))


def configure_logging(path: str | Path) -> logging.Logger:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"dataset_collection.{destination}")
    if not logger.handlers:
        handler = logging.FileHandler(destination, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_failure(logger: logging.Logger, spec: StageSpec, entity_id: str | None, error: BaseException) -> None:
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "stage": f"{spec.number:02d}_{spec.name}",
        "entity_id": entity_id,
        "error_type": type(error).__name__,
        "error": str(error),
    }
    logger.error(json.dumps(event, sort_keys=True, ensure_ascii=False))


def canonical_request_hash(provider: str, endpoint: str, params: Mapping[str, Any]) -> str:
    redacted = {key: value for key, value in params.items() if key.lower() not in {"api_key", "key", "token"}}
    payload = json.dumps([provider, endpoint, sorted(redacted.items())], separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stage_plan(spec: StageSpec, arguments: argparse.Namespace, config: Mapping[str, Any]) -> dict[str, Any]:
    seed = resolved_seed(arguments, config)
    provider_environment = None
    if spec.network_provider:
        provider_environment = (
            config.get("providers", {})
            .get(spec.network_provider, {})
            .get("api_key_environment_variable")
        )
    return {
        "stage": f"{spec.number:02d}_{spec.name}",
        "description": spec.description,
        "dataset_version": config.get("dataset_version"),
        "input": arguments.input,
        "output": arguments.output,
        "cache_dir": arguments.cache_dir,
        "log_file": arguments.log_file,
        "state_dir": arguments.state_dir,
        "resume": bool(arguments.resume),
        "job_id": arguments.job_id,
        "seed": seed,
        "force": bool(arguments.force),
        "network_provider": spec.network_provider,
        "credential_environment_variable": provider_environment,
        "credential_present": bool(provider_environment and os.environ.get(provider_environment)),
        "implemented_locally": spec.implemented_locally,
        "dry_run": True,
        "scaffold_version": SCAFFOLD_VERSION,
    }


def handle_progress_action(
    arguments: argparse.Namespace, parser: argparse.ArgumentParser
) -> int | None:
    if arguments.restart and not arguments.force:
        parser.error("--restart requires --force; prior raw data are never deleted silently")
    if not arguments.status:
        return None
    if not arguments.job_id:
        parser.error("--status requires --job-id")
    from _collection_progress import ProgressStore, render_status

    try:
        progress = ProgressStore(arguments.state_dir).load(arguments.job_id)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.error(str(error))
    print(render_status(progress))
    return 0


def run_scaffold(spec: StageSpec, argv: Sequence[str] | None = None) -> int:
    parser = build_parser(spec)
    arguments = parser.parse_args(argv)
    progress_result = handle_progress_action(arguments, parser)
    if progress_result is not None:
        return progress_result
    try:
        config = load_config(arguments.config)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    random.seed(resolved_seed(arguments, config))
    if arguments.dry_run:
        print(json.dumps(stage_plan(spec, arguments, config), indent=2, sort_keys=True))
        return 0
    if not spec.implemented_locally:
        parser.error(
            "live stage body is intentionally not enabled yet; review the dry-run plan and "
            "docs/openalex_collection_guide.md before implementing provider-specific mutations"
        )
    parser.error("this locally implemented stage must supply its own execution handler")
    return 2


def reconstruct_abstract(inverted_index: Mapping[str, Iterable[int]] | None) -> str | None:
    if inverted_index is None:
        return None
    positioned: dict[int, str] = {}
    for token, positions in inverted_index.items():
        if not isinstance(token, str):
            raise ValueError("abstract token must be a string")
        for position in positions:
            if not isinstance(position, int) or position < 0:
                raise ValueError(f"invalid abstract position: {position!r}")
            if position in positioned:
                raise ValueError(f"duplicate abstract position: {position}")
            positioned[position] = token
    if not positioned:
        return ""
    return " ".join(positioned[position] for position in sorted(positioned))


def _atomic_text_write(destination: Path, content: str, force: bool) -> None:
    if destination.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_json_atomic(destination: str | Path, value: Any, force: bool = False) -> None:
    content = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _atomic_text_write(Path(destination), content, force)


def write_jsonl_atomic(destination: str | Path, records: Iterable[Mapping[str, Any]], force: bool = False) -> None:
    content = "".join(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n" for record in records)
    _atomic_text_write(Path(destination), content, force)


def read_jsonl(source: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(Path(source).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL line {line_number} is not an object")
        records.append(value)
    return records


def describe_stage(spec: StageSpec) -> dict[str, Any]:
    return asdict(spec)
