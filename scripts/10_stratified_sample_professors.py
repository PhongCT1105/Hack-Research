#!/usr/bin/env python3
"""Select a deterministic provisional professor sample from OpenAlex-derived candidates."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Any, Mapping, Sequence

from _dataset_cli import (
    StageSpec,
    build_parser,
    handle_progress_action,
    resolved_seed,
    stage_plan,
)
from lib.config import DatasetConfig
from lib.io import atomic_write_csv, atomic_write_json, read_csv


ALGORITHM_VERSION = "constrained-margins-v1"
CANDIDATE_POOL_VERSION = "candidate-pool-v1"
INSTITUTION_CONCENTRATION_WEIGHT = 0.05
REGION_CONCENTRATION_WEIGHT = 0.02
HUMAN_REVIEW_DIMENSIONS = frozenset({"domain", "research_breadth", "synthesis_difficulty"})
BLOCKING_CONSISTENCY_STATUSES = frozenset({"needs_identity_review"})
BLOCKING_CONSISTENCY_ISSUES = frozenset(
    {
        "cross_profile_work_overlap",
        "expected_author_missing",
        "implausible_topic_mixture",
        "inconsistent_author_entries",
    }
)

SPEC = StageSpec(
    10,
    "stratified_sample_professors",
    __doc__,
    "data/interim/verified_professors.csv",
    "data/final/verified_professors.csv",
    supports_seed=True,
    implemented_locally=True,
)


@dataclass(frozen=True)
class SamplingResult:
    """Selection and audit details for one deterministic sampling run."""

    selected_ids: tuple[str, ...]
    objective: float
    objective_components: dict[str, float]
    target_distribution: dict[str, dict[str, int]]
    achieved_distribution: dict[str, dict[str, int]]
    unmet_targets: dict[str, dict[str, int]]
    exclusion_reasons: dict[str, tuple[str, ...]]
    reason_counts: dict[str, int]
    provisional_dimensions: tuple[str, ...]
    seed: int
    algorithm_version: str = ALGORITHM_VERSION
    candidate_pool_version: str = CANDIDATE_POOL_VERSION

    @property
    def exclusions(self) -> dict[str, tuple[str, ...]]:
        """Alias the explicit per-candidate exclusion reasons."""

        return self.exclusion_reasons

    @property
    def report(self) -> dict[str, Any]:
        """Return a JSON-serializable target, outcome, and exclusion report."""

        provisional = set(self.provisional_dimensions)
        return {
            "algorithm_version": self.algorithm_version,
            "candidate_pool_version": self.candidate_pool_version,
            "seed": self.seed,
            "selected_ids": list(self.selected_ids),
            "objective": self.objective,
            "objective_components": dict(self.objective_components),
            "target_distribution": _copy_distribution(self.target_distribution),
            "achieved_distribution": _copy_distribution(self.achieved_distribution),
            "unmet_targets": _copy_distribution(self.unmet_targets),
            "exclusions": {
                professor_id: list(reasons)
                for professor_id, reasons in self.exclusion_reasons.items()
            },
            "reason_counts": dict(self.reason_counts),
            "provisional_dimensions": list(self.provisional_dimensions),
            "target_status": {
                dimension: (
                    "provisional_human_review_required"
                    if dimension in provisional
                    else "openalex_derived"
                )
                for dimension in self.target_distribution
            },
        }


def sample_professors(
    candidates: Sequence[Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, int]],
    seed: int,
    limit: int,
) -> SamplingResult:
    """Greedily minimize normalized target deviation and concentration penalties.

    Eligibility is deliberately limited to gates observable in the local OpenAlex pipeline:
    exactly eight selected papers, an explicit complete-work-history marker, and no blocking
    within-OpenAlex identity-consistency finding. Human-review-dependent target values remain
    provisional aids; they are never represented as final reviewed labels.
    """

    _validate_control_values(seed, limit)
    normalized_targets = _normalize_targets(targets)
    candidates_by_id = _materialize_candidates(candidates)

    eligible: dict[str, Mapping[str, Any]] = {}
    exclusions: dict[str, tuple[str, ...]] = {}
    for professor_id, candidate in candidates_by_id.items():
        reasons = _hard_gate_reasons(candidate)
        if reasons:
            exclusions[professor_id] = reasons
        else:
            eligible[professor_id] = candidate

    seeded_order = sorted(eligible)
    random.Random(seed).shuffle(seeded_order)
    seeded_rank = {professor_id: rank for rank, professor_id in enumerate(seeded_order)}

    selected_ids: list[str] = []
    remaining = set(eligible)
    selection_limit = min(limit, len(remaining))
    while len(selected_ids) < selection_limit:
        ranked: list[tuple[float, int, str]] = []
        for professor_id in remaining:
            tentative = [*selected_ids, professor_id]
            objective, _ = _objective(tentative, eligible, normalized_targets)
            ranked.append((objective, seeded_rank[professor_id], professor_id))
        _, _, chosen_id = min(ranked)
        selected_ids.append(chosen_id)
        remaining.remove(chosen_id)

    for professor_id in sorted(remaining):
        exclusions[professor_id] = ("not_selected_by_optimizer",)

    achieved = _achieved_distribution(selected_ids, eligible, normalized_targets)
    unmet = _unmet_targets(normalized_targets, achieved)
    objective, objective_components = _objective(selected_ids, eligible, normalized_targets)
    ordered_exclusions = {
        professor_id: exclusions[professor_id] for professor_id in sorted(exclusions)
    }
    reason_counts = Counter(reason for reasons in ordered_exclusions.values() for reason in reasons)
    provisional_dimensions = tuple(
        dimension for dimension in normalized_targets if dimension in HUMAN_REVIEW_DIMENSIONS
    )
    return SamplingResult(
        selected_ids=tuple(selected_ids),
        objective=objective,
        objective_components=objective_components,
        target_distribution=normalized_targets,
        achieved_distribution=achieved,
        unmet_targets=unmet,
        exclusion_reasons=ordered_exclusions,
        reason_counts=dict(sorted(reason_counts.items())),
        provisional_dimensions=provisional_dimensions,
        seed=seed,
    )


def _validate_control_values(seed: int, limit: int) -> None:
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise TypeError("limit must be an integer")
    if limit < 1:
        raise ValueError("limit must be at least 1")


def _normalize_targets(
    targets: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, int]]:
    if not isinstance(targets, Mapping):
        raise TypeError("targets must be a mapping")
    normalized: dict[str, dict[str, int]] = {}
    for raw_dimension, raw_cells in targets.items():
        dimension = _required_string(raw_dimension, "target dimension")
        if not isinstance(raw_cells, Mapping):
            raise TypeError(f"target dimension {dimension!r} must be a mapping")
        cells: dict[str, int] = {}
        for raw_cell, count in raw_cells.items():
            cell = _required_string(raw_cell, f"target cell in {dimension}")
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(
                    f"target count for {dimension}.{cell} must be a non-negative integer"
                )
            cells[cell] = count
        normalized[dimension] = {cell: cells[cell] for cell in sorted(cells)}
    return {dimension: normalized[dimension] for dimension in sorted(normalized)}


def _materialize_candidates(
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    if isinstance(candidates, (str, bytes)) or not isinstance(candidates, Sequence):
        raise TypeError("candidates must be a sequence of mappings")
    materialized: dict[str, Mapping[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise TypeError("every candidate must be a mapping")
        professor_id = _required_string(candidate.get("professor_id"), "professor_id")
        if professor_id in materialized:
            raise ValueError(f"duplicate professor_id {professor_id}")
        materialized[professor_id] = candidate
    return {professor_id: materialized[professor_id] for professor_id in sorted(materialized)}


def _hard_gate_reasons(candidate: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    if _selected_paper_count(candidate) != 8:
        reasons.append("selected_paper_count_not_eight")
    if not _collection_complete(candidate):
        reasons.append("incomplete_work_history")
    if _has_blocking_consistency_issue(candidate):
        reasons.append("blocking_openalex_consistency_issue")
    return tuple(reasons)


def _selected_paper_count(candidate: Mapping[str, Any]) -> int | None:
    selected = candidate.get("selected_papers")
    if isinstance(selected, int) and not isinstance(selected, bool):
        return selected
    if isinstance(selected, (list, tuple)):
        return _unique_paper_count(selected)
    selected_ids = candidate.get("selected_paper_ids")
    if isinstance(selected_ids, (list, tuple)):
        return len(
            {paper_id for item in selected_ids if (paper_id := _clean_string(item)) is not None}
        )
    papers = candidate.get("papers")
    if isinstance(papers, (list, tuple)):
        return _unique_paper_count(
            [
                paper
                for paper in papers
                if isinstance(paper, Mapping) and paper.get("selected") is True
            ]
        )
    value = candidate.get("selected_paper_count")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _unique_paper_count(papers: Sequence[Any]) -> int:
    identities: set[str] = set()
    unidentified = 0
    for paper in papers:
        if isinstance(paper, str):
            paper_id = _clean_string(paper)
        elif isinstance(paper, Mapping):
            paper_id = next(
                (
                    value
                    for key in ("paper_id", "openalex_work_id", "id")
                    if (value := _clean_string(paper.get(key))) is not None
                ),
                None,
            )
        else:
            paper_id = None
        if paper_id is None:
            unidentified += 1
        else:
            identities.add(paper_id)
    return len(identities) + unidentified


def _collection_complete(candidate: Mapping[str, Any]) -> bool:
    if candidate.get("collection_complete") is True:
        return True
    for key in ("work_history", "completeness", "work_history_completeness"):
        value = candidate.get(key)
        if isinstance(value, Mapping) and value.get("collection_complete") is True:
            return True
    return False


def _has_blocking_consistency_issue(candidate: Mapping[str, Any]) -> bool:
    if candidate.get("blocking_openalex_issue") is True:
        return True
    statuses = {_clean_string(candidate.get("consistency_status"))}
    issue_codes = _string_values(candidate.get("consistency_issue_codes"))
    consistency = candidate.get("openalex_consistency")
    if isinstance(consistency, Mapping):
        statuses.add(_clean_string(consistency.get("status")))
        issue_codes.update(_string_values(consistency.get("issue_codes")))
        if consistency.get("blocking") is True:
            return True
    statuses.discard(None)
    return bool(
        BLOCKING_CONSISTENCY_STATUSES.intersection(statuses)
        or BLOCKING_CONSISTENCY_ISSUES.intersection(issue_codes)
    )


def _objective(
    selected_ids: Sequence[str],
    candidates: Mapping[str, Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, int]],
) -> tuple[float, dict[str, float]]:
    achieved = _achieved_distribution(selected_ids, candidates, targets)
    margin_deviation = sum(
        abs(achieved[dimension][cell] - target) / max(target, 1)
        for dimension, cells in targets.items()
        for cell, target in cells.items()
    )
    institution_counts = Counter(
        value
        for professor_id in selected_ids
        if (value := _institution(candidates[professor_id])) is not None
    )
    region_counts = Counter(
        value
        for professor_id in selected_ids
        if (value := _region(candidates[professor_id])) is not None
    )
    institution_penalty = INSTITUTION_CONCENTRATION_WEIGHT * sum(
        max(0, count - 1) for count in institution_counts.values()
    )
    region_penalty = REGION_CONCENTRATION_WEIGHT * sum(
        max(0, count - 1) for count in region_counts.values()
    )
    components = {
        "normalized_margin_deviation": margin_deviation,
        "institution_concentration_penalty": institution_penalty,
        "region_concentration_penalty": region_penalty,
    }
    return sum(components.values()), components


def _achieved_distribution(
    selected_ids: Sequence[str],
    candidates: Mapping[str, Mapping[str, Any]],
    targets: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, int]]:
    achieved = {dimension: {cell: 0 for cell in cells} for dimension, cells in targets.items()}
    for professor_id in selected_ids:
        candidate = candidates[professor_id]
        for dimension, cells in targets.items():
            value = _dimension_value(candidate, dimension)
            if value in cells:
                achieved[dimension][value] += 1
    return achieved


def _unmet_targets(
    targets: Mapping[str, Mapping[str, int]],
    achieved: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, int]]:
    unmet: dict[str, dict[str, int]] = {}
    for dimension, cells in targets.items():
        gaps = {
            cell: target - achieved[dimension][cell]
            for cell, target in cells.items()
            if achieved[dimension][cell] < target
        }
        if gaps:
            unmet[dimension] = gaps
    return unmet


def _dimension_value(candidate: Mapping[str, Any], dimension: str) -> str | None:
    dimensions = candidate.get("sampling_dimensions")
    value = dimensions.get(dimension) if isinstance(dimensions, Mapping) else None
    if value is None:
        value = candidate.get(dimension)
    if isinstance(value, Mapping):
        for key in ("reviewed_tier", "tier", "provisional_tier", "value", "label"):
            if (nested := _clean_string(value.get(key))) is not None:
                return nested
        return None
    if (cleaned := _clean_string(value)) is not None:
        return cleaned
    for key in (f"{dimension}_tier", f"provisional_{dimension}"):
        if (fallback := _clean_string(candidate.get(key))) is not None:
            return fallback
    return None


def _institution(candidate: Mapping[str, Any]) -> str | None:
    for key in ("institution_id", "openalex_institution_id", "institution"):
        value = candidate.get(key)
        if isinstance(value, Mapping):
            for nested_key in ("institution_id", "openalex_id", "id", "display_name"):
                if (nested := _clean_string(value.get(nested_key))) is not None:
                    return nested
        elif (cleaned := _clean_string(value)) is not None:
            return cleaned
    return None


def _region(candidate: Mapping[str, Any]) -> str | None:
    for key in ("region", "country_code", "country"):
        if (value := _clean_string(candidate.get(key))) is not None:
            return value
    return None


def _copy_distribution(
    value: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, int]]:
    return {dimension: dict(cells) for dimension, cells in value.items()}


def _required_string(value: Any, label: str) -> str:
    if (cleaned := _clean_string(value)) is None:
        raise ValueError(f"{label} must be a non-empty string")
    return cleaned


def _clean_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _string_values(value: Any) -> set[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()
    return {cleaned for item in value if (cleaned := _clean_string(item)) is not None}


def _sampling_targets(config: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    dimensions = {
        "domain": "domains",
        "career_stage": "career_stage",
        "visibility": "visibility",
        "research_breadth": "research_breadth",
        "paper_complexity": "paper_complexity",
        "synthesis_difficulty": "synthesis_difficulty",
    }
    targets: dict[str, dict[str, int]] = {}
    for dimension, config_key in dimensions.items():
        value = config.get(config_key)
        if not isinstance(value, Mapping):
            continue
        cells = {
            str(cell): count
            for cell, count in value.items()
            if isinstance(count, int) and not isinstance(count, bool) and count >= 0
        }
        if cells:
            targets[dimension] = cells
    return _normalize_targets(targets)


def _typed_candidate(row: Mapping[str, str]) -> dict[str, Any]:
    candidate: dict[str, Any] = dict(row)
    count = row.get("selected_paper_count")
    if isinstance(count, str) and count.strip().isdigit():
        candidate["selected_paper_count"] = int(count)
    for key in ("collection_complete", "blocking_openalex_issue"):
        value = row.get(key)
        if isinstance(value, str) and value.strip().casefold() in {"true", "false"}:
            candidate[key] = value.strip().casefold() == "true"
    for key in (
        "selected_papers",
        "selected_paper_ids",
        "papers",
        "work_history",
        "completeness",
        "work_history_completeness",
        "openalex_consistency",
        "sampling_dimensions",
    ):
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            candidate[key] = json.loads(value)
        except json.JSONDecodeError:
            continue
    return candidate


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser(SPEC)
    arguments = parser.parse_args(argv)
    progress_result = handle_progress_action(arguments, parser)
    if progress_result is not None:
        return progress_result
    try:
        config = DatasetConfig.load(arguments.config)
        targets = _sampling_targets(config.raw)
        configured_limit = config.raw.get("target_professors", 100)
        if isinstance(configured_limit, bool) or not isinstance(configured_limit, int):
            raise ValueError("target_professors must be an integer")
        arguments.limit = configured_limit if arguments.limit is None else arguments.limit
        _validate_control_values(resolved_seed(arguments, config.raw), arguments.limit)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(str(error))

    seed = resolved_seed(arguments, config.raw)
    if arguments.dry_run:
        plan = stage_plan(SPEC, arguments, config.raw)
        plan["algorithm_version"] = ALGORITHM_VERSION
        plan["candidate_pool_version"] = CANDIDATE_POOL_VERSION
        plan["target_dimensions"] = list(targets)
        plan["provisional_dimensions"] = [
            dimension for dimension in targets if dimension in HUMAN_REVIEW_DIMENSIONS
        ]
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if arguments.resume or arguments.restart:
        parser.error("Stage 10 is deterministic and does not use collection checkpoints")
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required for professor sampling")

    try:
        raw_candidates = read_csv(arguments.input)
        typed_candidates = [_typed_candidate(row) for row in raw_candidates]
        result = sample_professors(typed_candidates, targets, seed, arguments.limit)
        rows_by_id = {
            _required_string(row.get("professor_id"), "professor_id"): row for row in raw_candidates
        }
        selected_rows: list[dict[str, Any]] = []
        for selection_order, professor_id in enumerate(result.selected_ids, start=1):
            selected = dict(rows_by_id[professor_id])
            selected["sampling_selected"] = True
            selected["sampling_order"] = selection_order
            selected["sampling_seed"] = seed
            selected["sampling_algorithm_version"] = ALGORITHM_VERSION
            selected["sampling_status"] = "provisional_openalex_sample"
            selected_rows.append(selected)
        atomic_write_csv(arguments.output, selected_rows, force=arguments.force)
        report_path = Path(arguments.output).with_suffix(".sampling_report.json")
        atomic_write_json(report_path, result.report, force=arguments.force)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
