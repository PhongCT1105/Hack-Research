#!/usr/bin/env python3
"""Select deterministic 3/2/2/1 representatives and two provisional focal candidates."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from _dataset_cli import (
    StageSpec,
    build_parser,
    configure_logging,
    enforce_author_limit,
    handle_progress_action,
    log_failure,
    read_jsonl,
    resolved_seed,
    stage_plan,
)
from lib.config import DatasetConfig
from lib.io import atomic_write_csv
from lib.normalization import CANDIDATE_PAPER_CSV_COLUMNS
from lib.selection import (
    DEFAULT_MINIMUM_POOL_SIZE,
    DEFAULT_MAXIMUM_POOL_SIZE,
    select_candidate_pool,
    select_focal_candidates,
    select_representative_papers,
    validate_candidate_pool_bounds,
)


SPEC = StageSpec(
    9,
    "select_representative_papers",
    __doc__,
    "data/interim/scored_candidate_papers.jsonl",
    "data/interim/candidate_papers.csv",
    supports_seed=True,
    implemented_locally=True,
)


def select_paper_records(
    records: Sequence[Mapping[str, Any]],
    seed: int,
    *,
    minimum_pool_size: int = DEFAULT_MINIMUM_POOL_SIZE,
    maximum_pool_size: int = DEFAULT_MAXIMUM_POOL_SIZE,
) -> list[dict[str, Any]]:
    """Select and annotate one deterministic candidate pool per professor."""

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise TypeError("every paper record must be a mapping")
        professor_id = _clean_string(record.get("professor_id"))
        if professor_id is None:
            raise ValueError("every paper record must have a non-empty professor_id")
        grouped.setdefault(professor_id, []).append(record)

    output: list[dict[str, Any]] = []
    for professor_id in sorted(grouped):
        pool = select_candidate_pool(
            grouped[professor_id],
            minimum_size=minimum_pool_size,
            maximum_size=maximum_pool_size,
        )
        selected = select_representative_papers(pool, seed)
        selected_by_id = {_paper_id(paper): paper for paper in selected}
        focal_by_id = {_paper_id(paper): paper for paper in select_focal_candidates(selected)}
        for paper in pool:
            paper_id = _paper_id(paper)
            if paper_id in focal_by_id:
                annotated = focal_by_id[paper_id]
            elif paper_id in selected_by_id:
                annotated = deepcopy(selected_by_id[paper_id])
                annotated["focal"] = False
            else:
                annotated = deepcopy(paper)
                annotated["selected"] = False
                annotated["selection_reason"] = None
                annotated["focal"] = False
            output.append(annotated)
    return output


def _candidate_csv_record(paper: Mapping[str, Any]) -> dict[str, Any]:
    popularity = paper.get("popularity")
    complexity = paper.get("complexity")
    return {
        "professor_id": paper.get("professor_id"),
        "paper_id": _paper_id(paper),
        "openalex_work_id": paper.get("openalex_work_id") or _paper_id(paper),
        "doi": paper.get("doi"),
        "title": paper.get("title"),
        "publication_year": paper.get("publication_year"),
        "venue": paper.get("venue"),
        "citation_count": (
            paper.get("citation_count")
            if paper.get("citation_count") is not None
            else paper.get("cited_by_count")
        ),
        "citation_percentile_field_year": (
            popularity.get("field_normalized_citation_percentile")
            if isinstance(popularity, Mapping)
            else paper.get("citation_percentile_field_year")
        ),
        "abstract_available": _abstract_available(paper),
        # Stage 9 does not infer this value from an OA URL or inspect full text.
        "full_text_available": (
            paper.get("full_text_available")
            if isinstance(paper.get("full_text_available"), bool)
            else None
        ),
        "open_access": _open_access(paper),
        "topic_ids": "|".join(sorted(_topic_ids(paper))),
        "primary_topic": _primary_topic(paper),
        "method_tags": "|".join(sorted(_strings(paper.get("method_tags")))),
        "complexity_score": (
            complexity.get("score")
            if isinstance(complexity, Mapping)
            else paper.get("complexity_score")
        ),
        "complexity_tier": (
            complexity.get("tier")
            if isinstance(complexity, Mapping)
            else paper.get("complexity_tier")
        ),
        "selected": paper.get("selected") is True,
        "selection_reason": paper.get("selection_reason"),
        "focal": paper.get("focal") is True,
        "ownership_verified": paper.get("ownership_verified") is True,
    }


def _limit_records_by_profile(
    records: Sequence[Mapping[str, Any]], limit: int
) -> list[Mapping[str, Any]]:
    selected: list[str] = []
    for record in records:
        professor_id = _clean_string(record.get("professor_id"))
        if professor_id is None:
            raise ValueError("every paper record must have a non-empty professor_id")
        if professor_id not in selected and len(selected) < limit:
            selected.append(professor_id)
    selected_set = set(selected)
    return [
        record for record in records if _clean_string(record.get("professor_id")) in selected_set
    ]


def _paper_id(paper: Mapping[str, Any]) -> str:
    for key in ("paper_id", "openalex_work_id", "id"):
        if (value := _clean_string(paper.get(key))) is not None:
            return value
    raise ValueError("every paper must have a non-empty paper_id")


def _topic_ids(paper: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    topics = paper.get("topics")
    if isinstance(topics, (list, tuple)):
        for topic in topics:
            if not isinstance(topic, Mapping):
                continue
            for key in ("topic_id", "id", "topic", "display_name"):
                if (value := _clean_string(topic.get(key))) is not None:
                    values.add(value)
                    break
    return values


def _primary_topic(paper: Mapping[str, Any]) -> str | None:
    value = paper.get("primary_topic")
    if isinstance(value, Mapping):
        for key in ("topic_id", "id", "topic", "display_name"):
            if (candidate := _clean_string(value.get(key))) is not None:
                return candidate
        return None
    return _clean_string(value)


def _strings(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple)):
        return set()
    return {item.strip() for item in value if isinstance(item, str) and item.strip()}


def _abstract_available(paper: Mapping[str, Any]) -> bool:
    abstract = paper.get("reconstructed_abstract")
    return (isinstance(abstract, str) and bool(abstract.strip())) or paper.get(
        "abstract_available"
    ) is True


def _open_access(paper: Mapping[str, Any]) -> bool | None:
    value = paper.get("open_access")
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping) and isinstance(value.get("is_oa"), bool):
        return value["is_oa"]
    return None


def _clean_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


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
        seed = resolved_seed(arguments, config.raw)
        pool_settings = config.raw.get("candidate_papers_per_professor", {})
        minimum_pool_size = (
            pool_settings.get("minimum", DEFAULT_MINIMUM_POOL_SIZE)
            if isinstance(pool_settings, Mapping)
            else DEFAULT_MINIMUM_POOL_SIZE
        )
        maximum_pool_size = (
            pool_settings.get("maximum", DEFAULT_MAXIMUM_POOL_SIZE)
            if isinstance(pool_settings, Mapping)
            else DEFAULT_MAXIMUM_POOL_SIZE
        )
        validate_candidate_pool_bounds(minimum_pool_size, maximum_pool_size)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(str(error))
    if arguments.dry_run:
        plan = stage_plan(SPEC, arguments, config.raw)
        plan["minimum_candidate_pool_size"] = minimum_pool_size
        plan["maximum_candidate_pool_size"] = maximum_pool_size
        plan["focal_selection_status"] = "provisional_metadata_only"
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if arguments.resume or arguments.restart:
        parser.error("Stage 9 is deterministic and does not use collection checkpoints")
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required for paper selection")

    logger = configure_logging(arguments.log_file)
    try:
        records = _limit_records_by_profile(read_jsonl(arguments.input), arguments.limit)
        selected = select_paper_records(
            records,
            seed,
            minimum_pool_size=minimum_pool_size,
            maximum_pool_size=maximum_pool_size,
        )
        csv_records = [_candidate_csv_record(paper) for paper in selected]
        atomic_write_csv(
            Path(arguments.output),
            csv_records,
            fieldnames=CANDIDATE_PAPER_CSV_COLUMNS,
            force=arguments.force,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        log_failure(logger, SPEC, None, error)
        parser.error(str(error))
    print(f"wrote {len(csv_records)} records to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
