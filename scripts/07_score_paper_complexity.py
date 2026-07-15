#!/usr/bin/env python3
"""Score field/year-normalized paper complexity with popularity kept separate."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from _dataset_cli import (
    StageSpec,
    build_parser,
    configure_logging,
    enforce_author_limit,
    handle_progress_action,
    log_failure,
    read_jsonl,
    stage_plan,
    write_jsonl_atomic,
)
from lib.config import DatasetConfig
from lib.features import (
    PAPER_FEATURES_VERSION,
    ComplexityComponents,
    PaperFeatures,
    extract_paper_features,
    percentile_rank,
    score_paper_complexity,
)


PAPER_COMPLEXITY_VERSION = "paper-complexity-v1"
DEFAULT_MINIMUM_STRATUM_SIZE = 3

SPEC = StageSpec(
    7,
    "score_paper_complexity",
    __doc__,
    "data/interim/reconciled_candidate_papers.jsonl",
    "data/interim/scored_candidate_papers.jsonl",
    implemented_locally=True,
)


@dataclass(frozen=True)
class _PaperContext:
    features: PaperFeatures
    field: str | None
    domain: str | None
    year: int | None
    citation_count: int | None


_WEIGHTED_ATTRIBUTES = {
    "technical_vocabulary_density": "technical_vocabulary_density",
    "method_count": "method_count",
    "dataset_population_count": "dataset_or_population_count",
    "result_experiment_count": "result_or_experiment_count",
    "interdisciplinary_breadth": "interdisciplinary_breadth",
    "readability_difficulty": "readability_difficulty",
}


def score_paper_records(
    records: Sequence[Mapping[str, Any]],
    *,
    minimum_stratum_size: int = DEFAULT_MINIMUM_STRATUM_SIZE,
) -> list[dict[str, Any]]:
    """Return scored copies using deterministic, recorded normalization fallbacks."""

    if isinstance(minimum_stratum_size, bool) or minimum_stratum_size < 1:
        raise ValueError("minimum_stratum_size must be at least 1")
    contexts = [_paper_context(record) for record in records]
    transformed: list[dict[str, Any]] = []
    scores: list[float | None] = []

    for index, (record, context) in enumerate(zip(records, contexts, strict=True)):
        pool_indices, stratum = _complexity_pool(
            contexts, index, minimum_stratum_size=minimum_stratum_size
        )
        normalized = {
            schema_name: _normalized_feature(contexts, index, pool_indices, attribute)
            for schema_name, attribute in _WEIGHTED_ATTRIBUTES.items()
        }
        components = ComplexityComponents(
            normalized["technical_vocabulary_density"],
            normalized["method_count"],
            normalized["dataset_population_count"],
            normalized["result_experiment_count"],
            normalized["interdisciplinary_breadth"],
            normalized["readability_difficulty"],
            context.features.research_objective_count,
            context.features.qualification_hedging_density,
        )
        score = score_paper_complexity(components) if context.features.available else None
        scores.append(score)

        updated = deepcopy(dict(record))
        updated["method_tags"] = list(context.features.method_indicators)
        updated["dataset_population_tags"] = list(context.features.dataset_or_population_indicators)
        updated["paper_features"] = _serialize_features(context.features)
        updated["complexity"] = {
            "score": score,
            "tier": None,
            "score_version": PAPER_COMPLEXITY_VERSION,
            "normalization_stratum": stratum,
            "components": {
                **normalized,
                "research_objective_count": context.features.research_objective_count,
                "qualification_hedging_density": (context.features.qualification_hedging_density),
            },
        }
        updated["complexity_score"] = score
        updated["complexity_tier"] = None
        updated["popularity"] = _score_popularity(
            contexts,
            index,
            minimum_stratum_size=minimum_stratum_size,
        )
        transformed.append(updated)

    available_scores = [score for score in scores if score is not None]
    for updated, score in zip(transformed, scores, strict=True):
        score_percentile = percentile_rank(score, available_scores)
        tier = _complexity_tier(score_percentile)
        updated["complexity"]["pool_percentile"] = score_percentile
        updated["complexity"]["tier"] = tier
        updated["complexity_tier"] = tier
    return transformed


def _paper_context(record: Mapping[str, Any]) -> _PaperContext:
    topics_value = record.get("topics")
    topics = (
        [topic for topic in topics_value if isinstance(topic, Mapping)]
        if isinstance(topics_value, (list, tuple))
        else []
    )
    text_value = record.get("reconstructed_abstract")
    text = text_value if isinstance(text_value, str) else None
    field = _classification(record, "field")
    domain = _classification(record, "domain")
    year_value = record.get("publication_year")
    year = (
        year_value
        if isinstance(year_value, int) and not isinstance(year_value, bool) and year_value > 0
        else None
    )
    return _PaperContext(
        features=extract_paper_features(text, topics),
        field=field,
        domain=domain,
        year=year,
        citation_count=_citation_count(record),
    )


def _classification(record: Mapping[str, Any], level: str) -> str | None:
    direct = _name(record.get(level))
    if direct is not None:
        return direct
    primary_topic = record.get("primary_topic")
    if isinstance(primary_topic, Mapping):
        return _name(primary_topic.get(level))
    return None


def _name(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("display_name") or value.get("name")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _citation_count(record: Mapping[str, Any]) -> int | None:
    for key in ("cited_by_count", "citation_count"):
        value = record.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _complexity_pool(
    contexts: Sequence[_PaperContext], index: int, *, minimum_stratum_size: int
) -> tuple[list[int], str]:
    return _select_pool(
        contexts,
        index,
        minimum_stratum_size=minimum_stratum_size,
        eligible=lambda context: context.features.available,
    )


def _select_pool(
    contexts: Sequence[_PaperContext],
    index: int,
    *,
    minimum_stratum_size: int,
    eligible: Callable[[_PaperContext], bool],
) -> tuple[list[int], str]:
    target = contexts[index]
    candidates: list[tuple[str, Callable[[_PaperContext], bool]]] = []
    if target.field is not None and target.year is not None:
        candidates.append(
            (
                f"field_year:{target.field}:{target.year}",
                lambda context: context.field == target.field and context.year == target.year,
            )
        )
    if target.domain is not None and target.year is not None:
        candidates.append(
            (
                f"domain_year:{target.domain}:{target.year}",
                lambda context: context.domain == target.domain and context.year == target.year,
            )
        )
    if target.year is not None:
        candidates.append(
            (f"publication_year:{target.year}", lambda context: context.year == target.year)
        )

    for label, matches in candidates:
        members = [
            candidate_index
            for candidate_index, context in enumerate(contexts)
            if eligible(context) and matches(context)
        ]
        if len(members) >= minimum_stratum_size:
            return members, label
    return [index for index, context in enumerate(contexts) if eligible(context)], "global"


def _normalized_feature(
    contexts: Sequence[_PaperContext],
    index: int,
    pool_indices: Sequence[int],
    attribute: str,
) -> float | None:
    value = getattr(contexts[index].features, attribute)
    values = [getattr(contexts[pool_index].features, attribute) for pool_index in pool_indices]
    return percentile_rank(value, values)


def _score_popularity(
    contexts: Sequence[_PaperContext], index: int, *, minimum_stratum_size: int
) -> dict[str, Any]:
    target = contexts[index]
    field_pool, field_stratum = _select_pool(
        contexts,
        index,
        minimum_stratum_size=minimum_stratum_size,
        eligible=lambda context: context.citation_count is not None,
    )
    if target.year is not None:
        year_pool = [
            candidate_index
            for candidate_index, context in enumerate(contexts)
            if context.citation_count is not None and context.year == target.year
        ]
    else:
        year_pool = []
    if len(year_pool) < minimum_stratum_size:
        year_pool = [
            candidate_index
            for candidate_index, context in enumerate(contexts)
            if context.citation_count is not None
        ]
        year_stratum = "global"
    else:
        year_stratum = f"publication_year:{target.year}"

    return {
        "raw_citation_count": target.citation_count,
        "openalex_cited_by_count": target.citation_count,
        "field_normalized_citation_percentile": percentile_rank(
            target.citation_count,
            [contexts[pool_index].citation_count for pool_index in field_pool],
        ),
        "year_normalized_citation_percentile": percentile_rank(
            target.citation_count,
            [contexts[pool_index].citation_count for pool_index in year_pool],
        ),
        "normalization_stratum": f"field={field_stratum};year={year_stratum}",
    }


def _serialize_features(features: PaperFeatures) -> dict[str, Any]:
    return {
        "feature_version": PAPER_FEATURES_VERSION,
        "available": features.available,
        "raw_counts": {
            "word_count": features.word_count,
            "sentence_count": features.sentence_count,
            "syllable_count": features.syllable_count,
            "technical_vocabulary_count": features.technical_vocabulary_count,
            "method_count": features.method_count,
            "dataset_population_count": features.dataset_or_population_count,
            "result_experiment_count": features.result_or_experiment_count,
            "interdisciplinary_breadth": features.interdisciplinary_breadth,
            "research_objective_count": features.research_objective_count,
            "qualification_hedging_count": features.qualification_hedging_count,
        },
        "densities": {
            "technical_vocabulary_density": features.technical_vocabulary_density,
            "qualification_hedging_density": features.qualification_hedging_density,
        },
        "readability_difficulty": features.readability_difficulty,
        "controlled_indicators": {
            "method": list(features.method_indicators),
            "dataset_population": list(features.dataset_or_population_indicators),
            "result_experiment": list(features.result_or_experiment_indicators),
            "research_objective": list(features.research_objective_indicators),
            "qualification_hedging": list(features.qualification_hedging_indicators),
        },
    }


def _complexity_tier(percentile: float | None) -> str | None:
    if percentile is None:
        return None
    if percentile < 30.0:
        return "low"
    if percentile < 70.0:
        return "medium"
    return "high"


def _limit_records_by_profile(
    records: Sequence[Mapping[str, Any]], limit: int
) -> list[Mapping[str, Any]]:
    selected_profiles: list[str] = []
    selected_profile_set: set[str] = set()
    for record in records:
        professor_id = record.get("professor_id")
        if not isinstance(professor_id, str) or not professor_id.strip():
            raise ValueError("every paper record must have a non-empty professor_id")
        normalized_id = professor_id.strip()
        if normalized_id not in selected_profile_set and len(selected_profiles) < limit:
            selected_profiles.append(normalized_id)
            selected_profile_set.add(normalized_id)
    return [
        record
        for record in records
        if isinstance(record.get("professor_id"), str)
        and record["professor_id"].strip() in selected_profile_set
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(SPEC)
    parser.add_argument(
        "--minimum-stratum-size",
        type=int,
        default=DEFAULT_MINIMUM_STRATUM_SIZE,
        help="Minimum comparison-pool size before using a narrower normalization stratum",
    )
    arguments = parser.parse_args(argv)
    progress_result = handle_progress_action(arguments, parser)
    if progress_result is not None:
        return progress_result
    try:
        config = DatasetConfig.load(arguments.config)
        arguments.limit = enforce_author_limit(
            arguments.limit, arguments.full_run, config.safe_author_limit
        )
        if arguments.minimum_stratum_size < 1:
            raise ValueError("--minimum-stratum-size must be at least 1")
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    if arguments.dry_run:
        plan = stage_plan(SPEC, arguments, config.raw)
        plan["minimum_stratum_size"] = arguments.minimum_stratum_size
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if arguments.resume or arguments.restart:
        parser.error("Stage 7 is deterministic and does not use collection checkpoints")
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required for paper scoring")

    logger = configure_logging(arguments.log_file)
    try:
        records = _limit_records_by_profile(read_jsonl(arguments.input), arguments.limit)
        scored = score_paper_records(records, minimum_stratum_size=arguments.minimum_stratum_size)
        write_jsonl_atomic(Path(arguments.output), scored, force=arguments.force)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        log_failure(logger, SPEC, None, error)
        parser.error(str(error))
    print(f"wrote {len(scored)} records to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
