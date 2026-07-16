"""Shared safe CLI behavior for expanded-benchmark collection stages."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import random
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from lib.config import DatasetConfig
from lib.io import atomic_write_json, atomic_write_jsonl, read_jsonl as read_jsonl


SCAFFOLD_VERSION = "dataset-cli-v2"
# v2: strip residual JATS/HTML/TeX markup that OpenAlex leaves as inverted-index tokens
# (e.g. "<formula ...>", "<tex Notation=\"TeX\">${H_\\infty}$</tex>"). Left in, this markup
# pollutes the evidence packet and breaks downstream JSON generation. See docs/decision_log.md.
ABSTRACT_RECONSTRUCTION_VERSION = "openalex-inverted-index-v2"

# Only match tags whose name starts with a letter right after "<" or "</", so plain-text
# inequalities like "x < 5 and y > 3" are never treated as markup.
_MARKUP_TAG = re.compile(r"</?[A-Za-z][\w:.\-]*(?:\s[^<>]*)?>")
# Inline TeX math is stripped only when it contains a backslash command, so prices such as
# "$5 million ... $10" survive while "${H_\infty}$" does not.
_TEX_MATH = re.compile(r"\$[^$]*\\[^$]*\$")
_TEX_COMMAND = re.compile(r"\\[A-Za-z]+")
_WHITESPACE = re.compile(r"\s+")


def normalize_abstract_markup(text: str) -> str:
    """Remove residual JATS/HTML/TeX markup from a reconstructed abstract.

    Conservative on purpose: only recognized tags and backslash-bearing math are removed,
    so ordinary mathematical/notation text in an abstract is preserved.
    """
    text = _MARKUP_TAG.sub(" ", text)
    text = _TEX_MATH.sub(" ", text)
    text = _TEX_COMMAND.sub(" ", text)
    text = html.unescape(text)
    return _WHITESPACE.sub(" ", text).strip()


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


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
    parser.add_argument(
        "--config", default="config/dataset.yaml", help="Dataset YAML configuration"
    )
    parser.add_argument("--input", default=spec.default_input, help="Input file or directory")
    parser.add_argument("--output", default=spec.default_output, help="Output file or directory")
    parser.add_argument(
        "--cache-dir", default="data/raw/cache", help="HTTP response cache directory"
    )
    parser.add_argument(
        "--log-file", default="logs/dataset_collection.log", help="Structured failure log"
    )
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
    parser.add_argument(
        "--limit",
        type=_positive_integer,
        default=None,
        help="Maximum number of institutions or author profiles to process",
    )
    parser.add_argument(
        "--full-run",
        action="store_true",
        help="Permit author-processing stages to exceed the configured safe limit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print a deterministic execution plan without network calls or writes",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Permit replacing a derived output; raw data must use a new versioned path",
    )
    parser.add_argument("--version", action="version", version=SCAFFOLD_VERSION)
    return parser


def load_config(path: str | Path) -> dict[str, Any]:
    return DatasetConfig.load(path).raw


def enforce_author_limit(limit: int | None, full_run: bool, safe_limit: int = 10) -> int:
    resolved = safe_limit if limit is None else limit
    if resolved < 1:
        raise ValueError("--limit must be at least 1")
    if resolved > safe_limit and not full_run:
        raise ValueError(f"author limit above {safe_limit} requires --full-run")
    return resolved


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


def log_failure(
    logger: logging.Logger, spec: StageSpec, entity_id: str | None, error: BaseException
) -> None:
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "stage": f"{spec.number:02d}_{spec.name}",
        "entity_id": entity_id,
        "error_type": type(error).__name__,
        "error": str(error),
    }
    logger.error(json.dumps(event, sort_keys=True, ensure_ascii=False))


def canonical_request_hash(provider: str, endpoint: str, params: Mapping[str, Any]) -> str:
    redacted = {
        key: value
        for key, value in params.items()
        if key.lower() not in {"api_key", "key", "token"}
    }
    payload = json.dumps(
        [provider, endpoint, sorted(redacted.items())], separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stage_plan(
    spec: StageSpec, arguments: argparse.Namespace, config: Mapping[str, Any]
) -> dict[str, Any]:
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
        "limit": arguments.limit,
        "full_run": bool(arguments.full_run),
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
        typed_config = DatasetConfig.load(arguments.config)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))
    config = typed_config.raw
    try:
        if spec.number == 1:
            arguments.limit = (
                typed_config.safe_author_limit if arguments.limit is None else arguments.limit
            )
        else:
            arguments.limit = enforce_author_limit(
                arguments.limit, arguments.full_run, typed_config.safe_author_limit
            )
    except ValueError as error:
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
    joined = " ".join(positioned[position] for position in sorted(positioned))
    return normalize_abstract_markup(joined)


def write_json_atomic(destination: str | Path, value: Any, force: bool = False) -> None:
    atomic_write_json(destination, value, force=force)


def write_jsonl_atomic(
    destination: str | Path, records: Iterable[Mapping[str, Any]], force: bool = False
) -> None:
    atomic_write_jsonl(destination, records, force=force)


def describe_stage(spec: StageSpec) -> dict[str, Any]:
    return asdict(spec)
