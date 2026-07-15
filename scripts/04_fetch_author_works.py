#!/usr/bin/env python3
"""Collect complete cursor-paginated work histories for verified OpenAlex authors."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import sys
from dataclasses import dataclass
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
from lib.io import atomic_write_json, atomic_write_jsonl, read_csv
from lib.normalization import canonical_openalex_id, normalize_work
from lib.openalex_client import OpenAlexClient, UrllibTransport
from lib.progress import ProgressStore, canonical_json, make_job_id
from lib.runner import CollectionJob, PageClient, RawPageStore


STAGE = "04_fetch_author_works"
CLIENT_VERSION = "openalex-client-v1"
SPEC = StageSpec(
    4,
    "fetch_author_works",
    __doc__ or "Collect complete OpenAlex work histories",
    "data/interim/verified_professors.csv",
    "data/raw/author_works.jsonl",
    "openalex",
    implemented_locally=True,
)


@dataclass(frozen=True)
class WorkCollectionResult:
    """Materialized complete work histories and their collection evidence."""

    works: list[dict[str, Any]]
    completeness: dict[str, dict[str, Any]]
    job_id: str
    output_path: Path
    completeness_dir: Path


def collect_author_works(
    candidates: Sequence[Mapping[str, Any]],
    client: PageClient,
    workspace_root: str | Path,
    *,
    limit: int | None = None,
    full_run: bool = False,
    config: DatasetConfig | None = None,
    output_path: str | Path | None = None,
    raw_dir: str | Path | None = None,
    state_dir: str | Path | None = None,
    resume: bool = False,
    job_id: str | None = None,
    force: bool = False,
    original_command: str = "python scripts/04_fetch_author_works.py",
) -> WorkCollectionResult:
    """Collect, checkpoint, normalize, deduplicate, and publish complete histories."""

    root = Path(workspace_root)
    resolved_config = config or DatasetConfig.load(
        Path(__file__).resolve().parents[1] / "config/dataset.yaml"
    )
    resolved_limit = enforce_author_limit(limit, full_run, resolved_config.safe_author_limit)
    all_items = _candidate_items(candidates)
    items = all_items[:resolved_limit]
    input_digest = hashlib.sha256(canonical_json(all_items).encode("utf-8")).hexdigest()
    setup = {
        "endpoint": "works",
        "per_page": resolved_config.openalex.per_page,
        "author_ids": [item["provider_id"] for item in items],
        "dataset_version": resolved_config.dataset_version,
        "candidate_pool_version": resolved_config.candidate_pool_version,
        "limit": resolved_limit,
    }
    calculated_job_id = make_job_id(STAGE, setup, input_digest)
    resolved_job_id = job_id or calculated_job_id

    paths = resolved_config.raw.get("paths", {})
    configured_raw = paths.get("raw", "data/raw") if isinstance(paths, Mapping) else "data/raw"
    configured_progress = (
        paths.get("progress", Path(configured_raw) / "progress")
        if isinstance(paths, Mapping)
        else Path(configured_raw) / "progress"
    )
    raw_root = _resolve_path(root, raw_dir or configured_raw)
    progress_root = _resolve_path(root, state_dir or configured_progress)
    destination = _resolve_path(root, output_path or (Path(configured_raw) / "author_works.jsonl"))
    completeness_dir = raw_root / "completeness" / STAGE / resolved_job_id

    raw_page_store = RawPageStore(
        raw_root / "pages",
        stage=STAGE,
        job_id=resolved_job_id,
        envelope_version=resolved_config.raw_envelope_version,
        client_version=CLIENT_VERSION,
    )
    job = CollectionJob.create_or_resume(
        client=client,
        progress_store=ProgressStore(progress_root),
        raw_page_store=raw_page_store,
        stage=STAGE,
        setup=setup,
        input_checksum=input_digest,
        items=items,
        original_command=original_command,
        output_path=str(destination),
        resume=resume,
        job_id=resolved_job_id,
    )
    job.collect_items(items, _endpoint_for_author)

    works, completeness = _materialize_histories(job, items)
    for professor_id, marker in completeness.items():
        _write_completeness_marker(completeness_dir / f"{professor_id}.json", marker)
    atomic_write_jsonl(destination, works, force=force)
    return WorkCollectionResult(
        works=works,
        completeness=completeness,
        job_id=resolved_job_id,
        output_path=destination,
        completeness_dir=completeness_dir,
    )


def _resolve_path(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def _candidate_items(
    candidates: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    professor_ids: set[str] = set()
    author_ids: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ValueError("candidate rows must be mappings")
        professor_id = candidate.get("professor_id")
        if not isinstance(professor_id, str) or not professor_id.strip():
            raise ValueError("candidate professor_id must be a non-empty string")
        professor_id = professor_id.strip()
        if professor_id in {".", ".."} or re.fullmatch(r"[A-Za-z0-9._-]+", professor_id) is None:
            raise ValueError(f"candidate professor_id is not path-safe: {professor_id!r}")
        author_id = _author_id(
            candidate.get("openalex_author_id") or candidate.get("openalex_author_url")
        )
        if professor_id in professor_ids:
            raise ValueError(f"duplicate professor ID: {professor_id}")
        if author_id in author_ids:
            raise ValueError(f"duplicate OpenAlex author ID: {author_id}")
        professor_ids.add(professor_id)
        author_ids.add(author_id)
        items.append(
            {
                "item_type": "professor",
                "item_id": professor_id,
                "provider_id": author_id,
            }
        )
    if not items:
        raise ValueError("at least one author candidate is required")
    return items


def _author_id(value: Any) -> str:
    try:
        author_id = canonical_openalex_id(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid OpenAlex author ID: {value!r}") from error
    if author_id is None or re.fullmatch(r"A\d+", author_id) is None:
        raise ValueError(f"invalid OpenAlex author ID: {value!r}")
    return author_id


def _work_id(value: Any) -> str:
    try:
        work_id = canonical_openalex_id(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid OpenAlex work ID: {value!r}") from error
    if work_id is None or re.fullmatch(r"W\d+", work_id) is None:
        raise ValueError(f"invalid OpenAlex work ID: {value!r}")
    return work_id


def _endpoint_for_author(item: Mapping[str, str]) -> tuple[str, Mapping[str, Any]]:
    return "works", {"filter": f"author.id:{item['provider_id']}"}


def _materialize_histories(
    job: CollectionJob,
    items: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    references_by_item: dict[str, list[Mapping[str, Any]]] = {item["item_id"]: [] for item in items}
    for reference in job.progress.get("raw_pages", []):
        item_id = str(reference["item_id"])
        if item_id not in references_by_item:
            raise RuntimeError(f"raw page belongs to unknown professor: {item_id}")
        references_by_item[item_id].append(reference)

    completed = set(job.progress.get("completed_item_ids", []))
    all_works: list[dict[str, Any]] = []
    completeness: dict[str, dict[str, Any]] = {}
    for item in items:
        professor_id = item["item_id"]
        references = references_by_item[professor_id]
        if professor_id not in completed:
            raise RuntimeError(f"work history is not complete for {professor_id}")
        records: dict[str, dict[str, Any]] = {}
        first_cursor: str | None = None
        last_cursor: str | None = None
        terminal_cursor: str | None = None
        for index, reference in enumerate(references):
            envelope_path = job.raw_page_store.root_dir / str(reference["path"])
            envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
            if index == 0:
                first_cursor = envelope.get("cursor_in")
            last_cursor = envelope.get("cursor_in")
            terminal_cursor = envelope.get("cursor_out")
            results = envelope.get("response", {}).get("results")
            if not isinstance(results, list):
                raise RuntimeError(f"raw results are malformed for {professor_id}")
            for raw in results:
                if not isinstance(raw, Mapping):
                    raise ValueError(f"work record is not a mapping for {professor_id}")
                work_id = _work_id(raw.get("id"))
                records.setdefault(work_id, normalize_work(raw, professor_id=professor_id))
        if references and terminal_cursor is not None:
            raise RuntimeError(f"work history ended before the terminal cursor for {professor_id}")
        normalized = [records[work_id] for work_id in sorted(records)]
        all_works.extend(normalized)
        completeness[professor_id] = {
            "professor_id": professor_id,
            "openalex_author_id": item["provider_id"],
            "first_cursor": first_cursor,
            "last_cursor": last_cursor,
            "terminal_cursor": terminal_cursor,
            "page_count": len(references),
            "work_count": len(normalized),
            "raw_hashes": [str(reference["checksum"]) for reference in references],
            "collection_complete": True,
        }
    return all_works, completeness


def _write_completeness_marker(destination: Path, marker: Mapping[str, Any]) -> None:
    try:
        atomic_write_json(destination, marker)
    except FileExistsError:
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError(
                f"existing completeness marker is unreadable: {destination}"
            ) from error
        if existing != marker:
            raise RuntimeError(f"existing completeness marker conflicts: {destination}")


def dry_run_plan(config: DatasetConfig, arguments: Any) -> dict[str, Any]:
    plan = stage_plan(SPEC, arguments, config.raw)
    if arguments.input and Path(arguments.input).is_file():
        items = _candidate_items(read_csv(arguments.input))
        selected = items[: arguments.limit]
        plan["author_ids"] = [item["provider_id"] for item in selected]
        plan["estimated_jobs"] = len(selected)
    return plan


def _option_supplied(argv: Sequence[str], option: str) -> bool:
    return any(argument == option or argument.startswith(f"{option}=") for argument in argv)


def _resolve_stage_paths(arguments: Any, config: DatasetConfig, argv: Sequence[str]) -> None:
    paths = config.raw.get("paths", {})
    if not isinstance(paths, Mapping):
        return
    if not _option_supplied(argv, "--output"):
        arguments.output = str(Path(paths.get("raw", "data/raw")) / "author_works.jsonl")
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
        print(json.dumps(dry_run_plan(config, arguments), indent=2, sort_keys=True))
        return 0
    if arguments.restart:
        parser.error(
            "--restart is not yet supported for Stage 4; use a changed setup or output path"
        )

    root = Path.cwd()
    try:
        candidates = read_csv(arguments.input)
        client = OpenAlexClient(config.openalex, UrllibTransport(), arguments.cache_dir)
        collect_author_works(
            candidates,
            client,
            root,
            limit=arguments.limit,
            full_run=arguments.full_run,
            config=config,
            output_path=arguments.output,
            raw_dir=config.raw.get("paths", {}).get("raw", "data/raw"),
            state_dir=arguments.state_dir,
            resume=arguments.resume,
            job_id=arguments.job_id,
            force=arguments.force,
            original_command=shlex.join([sys.executable, __file__, *raw_argv]),
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
