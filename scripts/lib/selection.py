"""Deterministic paper-pool, representative-paper, and provisional focal selection."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
import random
from typing import Any, Iterable, Mapping, Sequence


PAPER_SELECTION_VERSION = "representative-papers-v1"
FOCAL_SELECTION_VERSION = "provisional-focal-metadata-v1"
SELECTION_SLOTS = (
    ("recent", 3),
    ("influential", 2),
    ("diversifying", 2),
    ("random", 1),
)
DEFAULT_MAXIMUM_POOL_SIZE = 30


def select_candidate_pool(
    papers: Sequence[Mapping[str, Any]],
    *,
    maximum_size: int = DEFAULT_MAXIMUM_POOL_SIZE,
) -> list[dict[str, Any]]:
    """Return at most ``maximum_size`` deterministic, explicitly eligible paper copies.

    Retractions, paratext, records explicitly marked ineligible, and records carrying an
    unresolved OpenAlex identity-consistency status are excluded. When a complete history is
    larger than the configured pool, recency and normalized influence are both represented
    before the remaining places greedily add topic/method coverage.
    """

    if isinstance(maximum_size, bool) or not isinstance(maximum_size, int) or maximum_size < 8:
        raise ValueError("maximum_size must be an integer of at least 8")
    materialized = _materialize_unique(papers)
    eligible = [paper for paper in materialized if _candidate_is_eligible(paper)]
    if len(eligible) <= maximum_size:
        return sorted(eligible, key=_paper_id)

    recent_target = maximum_size // 2
    influential_target = maximum_size // 3
    chosen: list[dict[str, Any]] = []
    chosen_ids: set[str] = set()
    _take_ranked(_recent_ranking(eligible), recent_target, "candidate", chosen, chosen_ids)
    _take_ranked(_influence_ranking(eligible), influential_target, "candidate", chosen, chosen_ids)
    while len(chosen) < maximum_size:
        remaining = [paper for paper in eligible if _paper_id(paper) not in chosen_ids]
        if not remaining:
            break
        next_paper, _ = _most_diversifying(remaining, chosen)
        _append_copy(next_paper, "candidate", chosen, chosen_ids)
    return sorted(chosen, key=_paper_id)


def select_representative_papers(
    papers: Sequence[Mapping[str, Any]], seed: int
) -> list[dict[str, Any]]:
    """Allocate eight unique papers to deterministic 3/2/2/1 primary-reason slots."""

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer")
    materialized = _materialize_unique(papers)
    if len(materialized) < 8:
        raise ValueError("representative selection requires at least 8 unique papers")

    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    _take_ranked(_recent_ranking(materialized), 3, "recent", selected, selected_ids, seed)
    _take_ranked(
        _influence_ranking(materialized),
        2,
        "influential",
        selected,
        selected_ids,
        seed,
    )

    for _ in range(2):
        remaining = [paper for paper in materialized if _paper_id(paper) not in selected_ids]
        next_paper, marginal_gain = _most_diversifying(remaining, selected)
        _append_copy(
            next_paper,
            "diversifying",
            selected,
            selected_ids,
            seed,
            diversity_contribution=marginal_gain,
        )

    remaining = sorted(
        (paper for paper in materialized if _paper_id(paper) not in selected_ids),
        key=_paper_id,
    )
    random_paper = random.Random(seed).choice(remaining)
    _append_copy(random_paper, "random", selected, selected_ids, seed)
    return selected


def select_focal_candidates(
    selected: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Rank two provisional focal candidates using metadata only.

    The rank consumes OA-location metadata, reconstructed-abstract availability, within-OpenAlex
    consistency, and topic/method coverage. It deliberately does not inspect or consume any
    ``full_text_available`` field.
    """

    materialized = _materialize_unique(selected)
    if len(materialized) < 2:
        raise ValueError("focal selection requires at least 2 unique selected papers")

    coverage_by_id = _coverage_potential(materialized)
    focal: list[dict[str, Any]] = []
    chosen_ids: set[str] = set()
    covered: set[str] = set()
    universe = set().union(*(_coverage_tokens(paper) for paper in materialized))

    for _ in range(2):
        ranked: list[tuple[float, str, Mapping[str, Any], dict[str, Any]]] = []
        for paper in materialized:
            paper_id = _paper_id(paper)
            if paper_id in chosen_ids:
                continue
            oa_score, oa_location = _oa_location_score(paper)
            abstract_available = _has_abstract(paper)
            consistent = _is_openalex_consistent(paper)
            tokens = _coverage_tokens(paper)
            marginal_coverage = len(tokens - covered) / len(universe) if universe else 0.0
            coverage_score = (coverage_by_id[paper_id] + marginal_coverage) / 2.0
            score = (
                0.35 * oa_score
                + 0.25 * float(abstract_available)
                + 0.25 * float(consistent)
                + 0.15 * coverage_score
            )
            evidence = {
                "provisional": True,
                "full_text_inspected": False,
                "basis": [
                    "openalex_oa_location_metadata",
                    "abstract_availability",
                    "openalex_consistency",
                    "topic_method_coverage",
                ],
                "oa_location_available": oa_location,
                "abstract_available": abstract_available,
                "openalex_consistent": consistent,
                "coverage_score": coverage_score,
                "score": score,
                "selection_version": FOCAL_SELECTION_VERSION,
            }
            ranked.append((-score, paper_id, paper, evidence))
        _, _, chosen, evidence = min(ranked)
        updated = deepcopy(dict(chosen))
        updated["focal"] = True
        updated["focal_status"] = "provisional_candidate"
        updated["focal_selection"] = evidence
        focal.append(updated)
        chosen_id = _paper_id(chosen)
        chosen_ids.add(chosen_id)
        covered.update(_coverage_tokens(chosen))
    return focal


def _materialize_unique(papers: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(papers, (str, bytes)):
        raise TypeError("papers must be a sequence of mappings")
    materialized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for paper in papers:
        if not isinstance(paper, Mapping):
            raise TypeError("every paper must be a mapping")
        copied = deepcopy(dict(paper))
        paper_id = _paper_id(copied)
        if paper_id in seen:
            raise ValueError(f"duplicate paper_id {paper_id}")
        seen.add(paper_id)
        materialized.append(copied)
    return materialized


def _paper_id(paper: Mapping[str, Any]) -> str:
    for key in ("paper_id", "openalex_work_id", "id"):
        value = paper.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise ValueError("every paper must have a non-empty paper_id")


def _candidate_is_eligible(paper: Mapping[str, Any]) -> bool:
    if paper.get("is_retracted") is True or paper.get("is_paratext") is True:
        return False
    if paper.get("eligible") is False:
        return False
    status = _clean_string(paper.get("eligibility_status"))
    if status is not None and status.casefold().startswith(("ineligible", "rejected")):
        return False
    return _clean_string(paper.get("consistency_status")) != "needs_identity_review"


def _recent_ranking(papers: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        papers,
        key=lambda paper: (
            -(_publication_date_key(paper) or -1),
            _paper_id(paper),
        ),
    )


def _publication_date_key(paper: Mapping[str, Any]) -> int | None:
    value = paper.get("publication_date")
    if isinstance(value, str):
        digits = value.replace("-", "")
        if len(digits) == 8 and digits.isdigit():
            return int(digits)
    year = paper.get("publication_year")
    if isinstance(year, int) and not isinstance(year, bool) and 0 < year <= 9999:
        return year * 10_000
    return None


def _influence_ranking(papers: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        papers,
        key=lambda paper: (
            -(_influence_score(paper) if _influence_score(paper) is not None else -1.0),
            _paper_id(paper),
        ),
    )


def _influence_score(paper: Mapping[str, Any]) -> float | None:
    popularity = paper.get("popularity")
    if isinstance(popularity, Mapping):
        for key in (
            "field_normalized_citation_percentile",
            "year_normalized_citation_percentile",
        ):
            if (score := _finite_number(popularity.get(key))) is not None:
                return score
    for key in ("citation_percentile_field_year", "field_normalized_citation_percentile"):
        if (score := _finite_number(paper.get(key))) is not None:
            return score
    return None


def _most_diversifying(
    remaining: Sequence[Mapping[str, Any]], selected: Sequence[Mapping[str, Any]]
) -> tuple[Mapping[str, Any], float]:
    if not remaining:
        raise ValueError("not enough unselected papers to fill selection slots")
    covered = set().union(*(_coverage_tokens(paper) for paper in selected)) if selected else set()
    ranked = []
    for paper in remaining:
        tokens = _coverage_tokens(paper)
        marginal = len(tokens - covered)
        ranked.append((-marginal, -len(tokens), _paper_id(paper), paper))
    negative_marginal, _, _, chosen = min(ranked)
    universe = covered | _coverage_tokens(chosen)
    contribution = -negative_marginal / len(universe) if universe else 0.0
    return chosen, contribution


def _coverage_tokens(paper: Mapping[str, Any]) -> set[str]:
    tokens: set[str] = set()
    topics = paper.get("topics")
    if isinstance(topics, (list, tuple)):
        for topic in topics:
            identifier = _topic_identifier(topic)
            if identifier is not None:
                tokens.add(f"topic:{identifier}")
    primary = _topic_identifier(paper.get("primary_topic"))
    if primary is not None:
        tokens.add(f"topic:{primary}")
    methods = paper.get("method_tags")
    if isinstance(methods, (list, tuple)):
        for method in methods:
            if (normalized := _identifier(method)) is not None:
                tokens.add(f"method:{normalized}")
    return tokens


def _topic_identifier(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for key in ("topic_id", "id", "topic", "display_name", "name"):
            if (identifier := _identifier(value.get(key))) is not None:
                return identifier
        return None
    return _identifier(value)


def _identifier(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().casefold()


def _coverage_potential(papers: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    token_counts = Counter(token for paper in papers for token in _coverage_tokens(paper))
    raw = {
        _paper_id(paper): sum(1.0 / token_counts[token] for token in _coverage_tokens(paper))
        for paper in papers
    }
    maximum = max(raw.values(), default=0.0)
    return {paper_id: value / maximum if maximum else 0.0 for paper_id, value in raw.items()}


def _oa_location_score(paper: Mapping[str, Any]) -> tuple[float, bool]:
    location_scores = []
    for location in _oa_locations(paper):
        if _http_url(location.get("pdf_url")):
            location_scores.append(1.0)
        elif any(_http_url(location.get(key)) for key in ("landing_page_url", "url", "source_url")):
            location_scores.append(0.9)
    if location_scores:
        return max(location_scores), True
    if _open_access_observation(paper) is True:
        return 0.5, False
    return 0.0, False


def _oa_locations(paper: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if _open_access_observation(paper) is False:
        return []
    locations: list[Mapping[str, Any]] = []
    best = paper.get("best_oa_location")
    if isinstance(best, Mapping):
        locations.append(best)
    primary = paper.get("primary_location")
    if isinstance(primary, Mapping) and primary.get("is_oa") is True:
        locations.append(primary)
    value = paper.get("locations")
    if isinstance(value, (list, tuple)):
        locations.extend(
            location
            for location in value
            if isinstance(location, Mapping) and location.get("is_oa") is True
        )
    return locations


def _open_access_observation(paper: Mapping[str, Any]) -> bool | None:
    value = paper.get("open_access")
    if isinstance(value, bool):
        return value
    if not isinstance(value, Mapping):
        return None
    flag = value.get("is_oa") if isinstance(value.get("is_oa"), bool) else None
    status_value = _clean_string(value.get("oa_status"))
    status = status_value.casefold() if status_value is not None else None
    status_flag = (
        status in {"diamond", "gold", "green", "hybrid", "bronze"}
        if status in {"diamond", "gold", "green", "hybrid", "bronze", "closed"}
        else None
    )
    if flag is not None and status_flag is not None and flag != status_flag:
        return None
    return flag if flag is not None else status_flag


def _http_url(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold().startswith(("http://", "https://"))


def _has_abstract(paper: Mapping[str, Any]) -> bool:
    value = paper.get("reconstructed_abstract")
    if isinstance(value, str) and value.strip():
        return True
    return paper.get("abstract_available") is True


def _is_openalex_consistent(paper: Mapping[str, Any]) -> bool:
    if _clean_string(paper.get("consistency_status")) == "openalex_consistent":
        return True
    value = paper.get("openalex_consistency")
    return (
        isinstance(value, Mapping) and _clean_string(value.get("status")) == "openalex_consistent"
    )


def _clean_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _take_ranked(
    ranked: Sequence[Mapping[str, Any]],
    count: int,
    reason: str,
    selected: list[dict[str, Any]],
    selected_ids: set[str],
    seed: int | None = None,
) -> None:
    before = len(selected)
    for paper in ranked:
        if _paper_id(paper) in selected_ids:
            continue
        _append_copy(paper, reason, selected, selected_ids, seed)
        if len(selected) - before == count:
            return
    raise ValueError(f"not enough unselected papers to fill {reason} slots")


def _append_copy(
    paper: Mapping[str, Any],
    reason: str,
    selected: list[dict[str, Any]],
    selected_ids: set[str],
    seed: int | None = None,
    *,
    diversity_contribution: float | None = None,
) -> None:
    updated = deepcopy(dict(paper))
    if reason != "candidate":
        updated["selected"] = True
        updated["selection_reason"] = reason
        updated["selection_seed"] = seed
        updated["selection_version"] = PAPER_SELECTION_VERSION
        updated["diversity_contribution"] = diversity_contribution
    selected.append(updated)
    selected_ids.add(_paper_id(paper))
