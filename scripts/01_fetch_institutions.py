#!/usr/bin/env python3
"""Collect a geographically and institutionally varied OpenAlex institution pool."""

from __future__ import annotations

import json
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from _dataset_cli import StageSpec, build_parser, handle_progress_action, stage_plan
from lib.config import DatasetConfig
from lib.io import atomic_write_csv, atomic_write_json
from lib.normalization import (
    INSTITUTION_CSV_COLUMNS,
    canonical_openalex_id,
    normalize_institution,
)
from lib.openalex_client import OpenAlexClient, UrllibTransport
from lib.progress import ProgressStore, make_job_id
from lib.runner import CollectionJob, PageClient, RawPageStore


STAGE = "01_fetch_institutions"
CLIENT_VERSION = "openalex-client-v1"
DISCOVERY_FILTER_COLUMN = "discovery_filters"
INSTITUTION_OUTPUT_COLUMNS = (*INSTITUTION_CSV_COLUMNS, DISCOVERY_FILTER_COLUMN)
SPEC = StageSpec(
    1,
    "fetch_institutions",
    __doc__ or "Collect OpenAlex institutions",
    None,
    "data/interim/institutions.csv",
    "openalex",
    implemented_locally=True,
)


@dataclass(frozen=True)
class InstitutionCollectionResult:
    """Materialized Stage 1 outputs and their stable collection identity."""

    rows: list[dict[str, Any]]
    summary: dict[str, Any]
    job_id: str
    output_path: Path
    summary_path: Path


def configured_filters(config: DatasetConfig) -> list[str]:
    """Return deterministic OpenAlex filters for every configured seed pairing."""

    return [
        f"country_code:{country},type:{institution_type}"
        for country in sorted(set(config.institution_seed_countries))
        for institution_type in sorted(set(config.institution_seed_types))
    ]


def collect_institutions(
    config: DatasetConfig,
    client: PageClient,
    workspace_root: str | Path,
    *,
    limit: int | None = None,
    output_path: str | Path | None = None,
    raw_dir: str | Path | None = None,
    state_dir: str | Path | None = None,
    seed: int | None = None,
    resume: bool = False,
    job_id: str | None = None,
    force: bool = False,
    original_command: str = "python scripts/01_fetch_institutions.py",
) -> InstitutionCollectionResult:
    """Collect, checkpoint, deduplicate, normalize, and publish Stage 1."""

    root = Path(workspace_root)
    resolved_limit = _institution_limit(config, limit)
    resolved_seed = config.random_seed if seed is None else seed
    filters = configured_filters(config)
    items = [_filter_item(filter_value) for filter_value in filters]
    setup = {
        "endpoint": "institutions",
        "filters": filters,
        "dataset_version": config.dataset_version,
        "candidate_pool_version": config.candidate_pool_version,
        "limit": resolved_limit,
        "seed": resolved_seed,
    }
    input_checksum = "no-input"
    calculated_job_id = make_job_id(STAGE, setup, input_checksum)
    resolved_job_id = job_id or calculated_job_id

    paths = config.raw.get("paths", {})
    configured_raw = paths.get("raw", "data/raw") if isinstance(paths, Mapping) else "data/raw"
    configured_interim = (
        paths.get("interim", "data/interim") if isinstance(paths, Mapping) else "data/interim"
    )
    configured_progress = (
        paths.get("progress", Path(configured_raw) / "progress")
        if isinstance(paths, Mapping)
        else Path(configured_raw) / "progress"
    )
    raw_root = _resolve_path(root, raw_dir or configured_raw)
    progress_root = _resolve_path(root, state_dir or configured_progress)
    destination = _resolve_path(
        root, output_path or (Path(configured_interim) / "institutions.csv")
    )
    summary_path = destination.with_name(f"{destination.stem}_summary.json")

    raw_page_store = RawPageStore(
        raw_root / "pages",
        stage=STAGE,
        job_id=resolved_job_id,
        envelope_version=config.raw_envelope_version,
        client_version=CLIENT_VERSION,
    )
    job = CollectionJob.create_or_resume(
        client=client,
        progress_store=ProgressStore(progress_root),
        raw_page_store=raw_page_store,
        stage=STAGE,
        setup=setup,
        input_checksum=input_checksum,
        items=items,
        original_command=original_command,
        output_path=str(destination),
        resume=resume,
        job_id=resolved_job_id,
    )
    job.collect_items(items, _endpoint_for_filter)

    all_rows, valid_record_count, invalid_record_count = _materialize_rows(job, items)
    rows = all_rows[:resolved_limit]
    summary = _collection_summary(
        rows,
        job_id=resolved_job_id,
        filters=filters,
        fetched_records=int(job.progress.get("records_written", 0)),
        valid_records=valid_record_count,
        invalid_records=invalid_record_count,
        distinct_records=len(all_rows),
        limit=resolved_limit,
    )
    atomic_write_csv(
        destination,
        rows,
        fieldnames=INSTITUTION_OUTPUT_COLUMNS,
        force=force,
    )
    atomic_write_json(summary_path, summary, force=force)
    return InstitutionCollectionResult(
        rows=rows,
        summary=summary,
        job_id=resolved_job_id,
        output_path=destination,
        summary_path=summary_path,
    )


def _institution_limit(config: DatasetConfig, limit: int | None) -> int:
    institution_seed = config.raw.get("institution_seed", {})
    configured_limit = (
        institution_seed.get("limit", 50) if isinstance(institution_seed, Mapping) else 50
    )
    resolved = configured_limit if limit is None else limit
    if not isinstance(resolved, int) or isinstance(resolved, bool) or resolved < 1:
        raise ValueError("institution limit must be a positive integer")
    return resolved


def _resolve_path(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def _filter_item(filter_value: str) -> dict[str, str]:
    country_filter, type_filter = filter_value.split(",", maxsplit=1)
    country = country_filter.split(":", maxsplit=1)[1]
    institution_type = type_filter.split(":", maxsplit=1)[1]
    return {
        "item_type": "filter",
        "item_id": f"country-{country}__type-{institution_type}",
        "provider_id": filter_value,
        "country": country,
        "institution_type": institution_type,
        "filter": filter_value,
    }


def _endpoint_for_filter(item: Mapping[str, str]) -> tuple[str, Mapping[str, Any]]:
    return "institutions", {"filter": item["filter"]}


def _materialize_rows(
    job: CollectionJob,
    items: Sequence[Mapping[str, str]],
) -> tuple[list[dict[str, Any]], int, int]:
    filters_by_item = {item["item_id"]: item["filter"] for item in items}
    records: dict[str, dict[str, Any]] = {}
    discoveries: dict[str, set[str]] = {}
    valid_records = 0
    invalid_records = 0

    for reference in job.progress.get("raw_pages", []):
        envelope_path = job.raw_page_store.root_dir / str(reference["path"])
        envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
        results = envelope.get("response", {}).get("results", [])
        filter_value = filters_by_item[str(reference["item_id"])]
        for raw in results:
            if not isinstance(raw, Mapping):
                invalid_records += 1
                continue
            openalex_id = canonical_openalex_id(raw.get("id"))
            if not openalex_id:
                invalid_records += 1
                continue
            valid_records += 1
            if openalex_id not in records:
                records[openalex_id] = normalize_institution(raw)
            discoveries.setdefault(openalex_id, set()).add(filter_value)

    rows: list[dict[str, Any]] = []
    for openalex_id in sorted(records):
        normalized = records[openalex_id]
        row = {column: normalized.get(column) for column in INSTITUTION_CSV_COLUMNS}
        row[DISCOVERY_FILTER_COLUMN] = "|".join(sorted(discoveries[openalex_id]))
        rows.append(row)
    return rows, valid_records, invalid_records


def _collection_summary(
    rows: Sequence[Mapping[str, Any]],
    *,
    job_id: str,
    filters: Sequence[str],
    fetched_records: int,
    valid_records: int,
    invalid_records: int,
    distinct_records: int,
    limit: int,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "filters": list(filters),
        "estimated jobs": len(filters),
        "records fetched": fetched_records,
        "valid records": valid_records,
        "invalid records skipped": invalid_records,
        "duplicates removed": max(valid_records - distinct_records, 0),
        "institutions omitted by limit": max(distinct_records - len(rows), 0),
        "institution limit": limit,
        "institutions collected": len(rows),
        "countries represented": len({row["country"] for row in rows if row.get("country")}),
        "regions represented": len({row["region"] for row in rows if row.get("region")}),
        "institution types represented": len(
            {row["institution_type"] for row in rows if row.get("institution_type")}
        ),
    }


def dry_run_plan(config: DatasetConfig, arguments: Any) -> dict[str, Any]:
    plan = stage_plan(SPEC, arguments, config.raw)
    filters = configured_filters(config)
    plan.update(
        {
            "filters": filters,
            "estimated_jobs": len(filters),
            "limit": _institution_limit(config, arguments.limit),
        }
    )
    return plan


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(SPEC)
    arguments = parser.parse_args(argv)
    progress_result = handle_progress_action(arguments, parser)
    if progress_result is not None:
        return progress_result
    try:
        config = DatasetConfig.load(arguments.config)
        arguments.limit = _institution_limit(config, arguments.limit)
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))

    if arguments.dry_run:
        print(json.dumps(dry_run_plan(config, arguments), indent=2, sort_keys=True))
        return 0

    if arguments.restart:
        parser.error(
            "--restart is not yet supported for Stage 1; use a changed setup or output path"
        )

    root = Path.cwd()
    raw_path = config.raw.get("paths", {}).get("raw", "data/raw")
    try:
        client = OpenAlexClient(config.openalex, UrllibTransport(), arguments.cache_dir)
        collect_institutions(
            config,
            client,
            root,
            limit=arguments.limit,
            output_path=arguments.output,
            raw_dir=raw_path,
            state_dir=arguments.state_dir,
            seed=arguments.seed,
            resume=arguments.resume,
            job_id=arguments.job_id,
            force=arguments.force,
            original_command=shlex.join([sys.executable, __file__, *(argv or sys.argv[1:])]),
        )
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
