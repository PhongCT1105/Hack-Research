#!/usr/bin/env python3
"""Score distinct, deterministic research-portfolio constructs from OpenAlex metadata."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable, Mapping, Sequence

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


PORTFOLIO_FEATURES_VERSION = "portfolio-features-v1"
SYNTHESIS_DIFFICULTY_VERSION = "synthesis-difficulty-v1"
HIERARCHY_COHERENCE_VERSION = "openalex-topic-hierarchy-v1"

# Dict insertion order is the documented formula order and is retained in output records.
SYNTHESIS_WEIGHTS = {
    "topic_entropy": 0.15,
    "mean_semantic_distance": 0.15,
    "topic_cluster_count": 0.10,
    "method_diversity": 0.10,
    "dataset_population_diversity": 0.10,
    "temporal_research_evolution": 0.10,
    "cross_domain_breadth": 0.10,
    "inverse_topic_coherence": 0.20,
}

SPEC = StageSpec(
    8,
    "score_research_portfolios",
    __doc__,
    "data/interim/scored_candidate_papers.jsonl",
    "data/interim/scored_professor_portfolios.jsonl",
    implemented_locally=True,
)


def topic_entropy(values: Sequence[Any]) -> float | None:
    """Return normalized Shannon entropy for topic IDs or topic-bearing records."""

    topic_ids: list[str] = []
    for value in values:
        if isinstance(value, Mapping):
            if _looks_like_topic(value) and _topic_identifier(value) is not None:
                topic_ids.append(_topic_identifier(value) or "")
                continue
            primary = _primary_topic(value)
            identifier = _topic_identifier(primary) if primary is not None else None
        else:
            identifier = _clean_string(value)
        if identifier is not None:
            topic_ids.append(identifier)
    return _normalized_entropy(topic_ids)


def method_entropy(values: Sequence[Any]) -> float | None:
    """Return normalized Shannon entropy for controlled method-family tags."""

    return _normalized_entropy(
        normalized for value in values if (normalized := _clean_string(value)) is not None
    )


def build_topic_clusters(papers: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group papers deterministically by OpenAlex field hierarchy IDs, without embeddings."""

    clusters: dict[str, dict[str, Any]] = {}
    for index, paper in enumerate(papers):
        topic = _primary_topic(paper)
        if topic is None:
            continue
        cluster_id, level, hierarchy_id, label = _cluster_identity(topic)
        cluster = clusters.setdefault(
            cluster_id,
            {
                "cluster_id": cluster_id,
                "hierarchy_level": level,
                "hierarchy_id": hierarchy_id,
                "label": label,
                "paper_ids": [],
                "topic_ids": [],
            },
        )
        paper_id = _paper_identifier(paper, index)
        cluster["paper_ids"].append(paper_id)
        topic_id = _topic_identifier(topic)
        if topic_id is not None:
            cluster["topic_ids"].append(topic_id)

    result: list[dict[str, Any]] = []
    for cluster_id in sorted(clusters):
        cluster = clusters[cluster_id]
        paper_ids = sorted(set(cluster["paper_ids"]))
        topic_ids = sorted(set(cluster["topic_ids"]))
        result.append(
            {
                **cluster,
                "paper_ids": paper_ids,
                "topic_ids": topic_ids,
                "paper_count": len(paper_ids),
            }
        )
    return result


def score_portfolio(papers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate one professor's papers while keeping benchmark constructs separate."""

    materialized = list(papers)
    if any(not isinstance(paper, Mapping) for paper in materialized):
        raise TypeError("portfolio papers must be mappings")

    topics_by_paper = [_paper_topics(paper) for paper in materialized]
    primary_topics = [_primary_topic(paper) for paper in materialized]
    primary_topics_available = [topic for topic in primary_topics if topic is not None]
    primary_cluster_ids = [_cluster_identity(topic)[0] for topic in primary_topics_available]
    clusters = build_topic_clusters(materialized)
    topic_ids = [
        identifier
        for topics in topics_by_paper
        for topic in topics
        if (identifier := _topic_identifier(topic)) is not None
    ]
    subfield_ids = _hierarchy_values(topics_by_paper, "subfield")
    field_ids = _hierarchy_values(topics_by_paper, "field")
    domain_ids = _hierarchy_values(topics_by_paper, "domain")

    method_tags_by_paper = [_controlled_tags(paper, "method") for paper in materialized]
    dataset_tags_by_paper = [
        _controlled_tags(paper, "dataset_population") for paper in materialized
    ]
    method_tags = [tag for tags in method_tags_by_paper for tag in tags]
    dataset_tags = [tag for tags in dataset_tags_by_paper for tag in tags]

    research_breadth = _research_breadth(
        paper_count=len(materialized),
        topic_ids=topic_ids,
        subfield_ids=subfield_ids,
        field_ids=field_ids,
        cluster_ids=primary_cluster_ids,
        clusters=clusters,
    )
    topic_coherence = _topic_coherence(primary_topics_available, clusters)
    method_diversity = _method_diversity(method_tags, method_tags_by_paper)
    dataset_distribution = _tag_distribution(dataset_tags, dataset_tags_by_paper)
    temporal_distribution = _temporal_distribution(materialized)
    collaboration_distribution = _collaboration_distribution(materialized)
    open_access_distribution = _open_access_distribution(materialized)
    paper_complexity = _paper_complexity(materialized)
    visibility = _visibility(materialized)
    evidence_completeness = _evidence_completeness(materialized)

    synthesis_components = {
        "topic_entropy": research_breadth["components"]["normalized_topic_entropy"],
        # Embeddings are intentionally absent from v1; missingness is explicit below.
        "mean_semantic_distance": None,
        "topic_cluster_count": _normalized_count(len(clusters), len(primary_topics_available)),
        "method_diversity": method_diversity["score"],
        "dataset_population_diversity": dataset_distribution["entropy"],
        "temporal_research_evolution": _temporal_research_evolution(materialized, primary_topics),
        "cross_domain_breadth": _normalized_count(
            len(set(domain_ids)), len(primary_topics_available)
        ),
        "inverse_topic_coherence": (
            None if topic_coherence["score"] is None else 1.0 - topic_coherence["score"]
        ),
    }
    synthesis_difficulty = _synthesis_difficulty(synthesis_components)

    professor_ids = {
        professor_id
        for paper in materialized
        if (professor_id := _clean_string(paper.get("professor_id"))) is not None
    }
    if len(professor_ids) > 1:
        raise ValueError("score_portfolio cannot mix records from multiple professors")

    return {
        "professor_id": next(iter(professor_ids), None),
        "paper_count": len(materialized),
        "paper_ids": [_paper_identifier(paper, index) for index, paper in enumerate(materialized)],
        "feature_version": PORTFOLIO_FEATURES_VERSION,
        "research_breadth": research_breadth,
        "topic_coherence_aid": topic_coherence,
        "method_diversity": method_diversity,
        "paper_complexity": paper_complexity,
        "synthesis_difficulty": synthesis_difficulty,
        "visibility": visibility,
        "evidence_completeness": evidence_completeness,
        "temporal_distribution": temporal_distribution,
        "collaboration_distribution": collaboration_distribution,
        "open_access_distribution": open_access_distribution,
        "dataset_population_distribution": dataset_distribution,
        "topic_clusters": clusters,
    }


def score_portfolios(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Group paper records by professor ID and score groups in first-seen order."""

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        if not isinstance(record, Mapping):
            raise TypeError("portfolio records must be mappings")
        professor_id = _clean_string(record.get("professor_id"))
        if professor_id is None:
            raise ValueError("every paper record must have a non-empty professor_id")
        grouped.setdefault(professor_id, []).append(record)
    return [score_portfolio(papers) for papers in grouped.values()]


def _research_breadth(
    *,
    paper_count: int,
    topic_ids: Sequence[str],
    subfield_ids: Sequence[str],
    field_ids: Sequence[str],
    cluster_ids: Sequence[str],
    clusters: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    entropy = topic_entropy(topic_ids)
    components = {
        "normalized_topic_entropy": entropy,
        "normalized_unique_topic_count": _normalized_unique_count(topic_ids, paper_count),
        "normalized_unique_subfield_count": _normalized_unique_count(subfield_ids, paper_count),
        "normalized_unique_field_count": _normalized_unique_count(field_ids, paper_count),
        "normalized_topic_cluster_balance": _normalized_entropy(cluster_ids),
    }
    score = _weighted_available_mean(
        components,
        {
            "normalized_topic_entropy": 0.35,
            "normalized_unique_topic_count": 0.25,
            "normalized_unique_subfield_count": 0.20,
            "normalized_unique_field_count": 0.10,
            "normalized_topic_cluster_balance": 0.10,
        },
    )[0]
    return {
        "score": score,
        "tier": None,
        "components": components,
        "unique_topic_count": len(set(topic_ids)),
        "unique_subfield_count": len(set(subfield_ids)),
        "unique_field_count": len(set(field_ids)),
        "topic_entropy": entropy,
        "topic_cluster_distribution": {
            cluster["cluster_id"]: cluster["paper_count"] for cluster in clusters
        },
    }


def _topic_coherence(
    topics: Sequence[Mapping[str, Any]], clusters: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    similarities = [
        _topic_similarity(left, right)
        for index, left in enumerate(topics)
        for right in topics[index + 1 :]
    ]
    within: list[float] = []
    between: list[float] = []
    for index, left in enumerate(topics):
        left_cluster = _cluster_identity(left)[0]
        for right in topics[index + 1 :]:
            similarity = _topic_similarity(left, right)
            if left_cluster == _cluster_identity(right)[0]:
                within.append(similarity)
            else:
                between.append(similarity)
    score = fmean(similarities) if similarities else (1.0 if topics else None)
    return {
        "score": score,
        "tier": None,
        "human_reviewed": False,
        "method": HIERARCHY_COHERENCE_VERSION,
        "embedding_model": None,
        "components": {
            "mean_hierarchy_similarity": score,
            "within_cluster_similarity": fmean(within) if within else None,
            "between_cluster_similarity": fmean(between) if between else None,
            "cluster_count": len(clusters) if topics else None,
            "pair_count": len(similarities),
        },
    }


def _method_diversity(
    tags: Sequence[str], tags_by_paper: Sequence[Sequence[str]]
) -> dict[str, Any]:
    entropy = method_entropy(tags)
    papers_with_tags = sum(bool(paper_tags) for paper_tags in tags_by_paper)
    distinct_score = _normalized_unique_count(tags, papers_with_tags)
    components = {
        "normalized_distinct_method_count": distinct_score,
        "normalized_method_entropy": entropy,
    }
    score = _weighted_available_mean(
        components,
        {
            "normalized_distinct_method_count": 0.50,
            "normalized_method_entropy": 0.50,
        },
    )[0]
    return {
        "score": score,
        "tier": None,
        "tags": sorted(set(tags)),
        "count": len(set(tags)),
        "entropy": entropy,
        "counts": dict(sorted(Counter(tags).items())),
        "components": components,
    }


def _tag_distribution(
    tags: Sequence[str], tags_by_paper: Sequence[Sequence[str]]
) -> dict[str, Any]:
    return {
        "tags": sorted(set(tags)),
        "count": len(set(tags)),
        "entropy": _normalized_entropy(tags),
        "counts": dict(sorted(Counter(tags).items())),
        "papers_available": sum(bool(paper_tags) for paper_tags in tags_by_paper),
        "papers_missing": sum(not paper_tags for paper_tags in tags_by_paper),
    }


def _temporal_distribution(papers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    years = [year for paper in papers if (year := _year(paper.get("publication_year"))) is not None]
    counts = Counter(years)
    first = min(years) if years else None
    last = max(years) if years else None
    return {
        "first_publication_year": first,
        "last_publication_year": last,
        "publication_span_years": last - first if first is not None and last is not None else None,
        "counts_by_year": {str(year): counts[year] for year in sorted(counts)},
        "papers_available": len(years),
        "papers_missing": len(papers) - len(years),
    }


def _collaboration_distribution(papers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    author_counts: list[int] = []
    unique_authors: set[str] = set()
    portfolio_author_ids = {
        author_id for paper in papers if (author_id := _portfolio_author_id(paper)) is not None
    }
    multi_institution: list[bool] = []
    for paper in papers:
        authorships = _mappings(paper.get("authorships"))
        if authorships:
            author_counts.append(len(authorships))
        institution_ids: set[str] = set()
        for authorship in authorships:
            author = authorship.get("author")
            if isinstance(author, Mapping):
                author_id = _clean_string(author.get("id"))
                if author_id is not None:
                    unique_authors.add(author_id)
            for institution in _mappings(authorship.get("institutions")):
                institution_id = _clean_string(institution.get("id"))
                if institution_id is not None:
                    institution_ids.add(institution_id)
        if authorships:
            multi_institution.append(len(institution_ids) > 1)
    return {
        "mean_author_count": fmean(author_counts) if author_counts else None,
        "minimum_author_count": min(author_counts) if author_counts else None,
        "maximum_author_count": max(author_counts) if author_counts else None,
        "unique_author_count": len(unique_authors) if author_counts else None,
        "unique_collaborator_count": (
            len(unique_authors - portfolio_author_ids) if author_counts else None
        ),
        "multi_institution_rate": (
            sum(multi_institution) / len(multi_institution) if multi_institution else None
        ),
        "papers_available": len(author_counts),
        "papers_missing": len(papers) - len(author_counts),
    }


def _open_access_distribution(papers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    flags: list[bool] = []
    statuses: Counter[str] = Counter()
    for paper in papers:
        open_access = paper.get("open_access")
        if not isinstance(open_access, Mapping):
            continue
        is_oa = open_access.get("is_oa")
        if isinstance(is_oa, bool):
            flags.append(is_oa)
        status = _clean_string(open_access.get("oa_status"))
        if status is not None:
            statuses[status] += 1
    return {
        "rate": sum(flags) / len(flags) if flags else None,
        "status_counts": dict(sorted(statuses.items())),
        "papers_available": len(flags),
        "papers_missing": len(papers) - len(flags),
    }


def _paper_complexity(papers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    scores = [score for paper in papers if (score := _complexity_score(paper)) is not None]
    distribution = _numeric_distribution(scores, len(papers))
    return {
        "score": distribution["mean"],
        "tier": None,
        "distribution": distribution,
    }


def _visibility(papers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    field_values: list[float] = []
    year_values: list[float] = []
    for paper in papers:
        popularity = paper.get("popularity")
        if not isinstance(popularity, Mapping):
            continue
        field = _percentile(popularity.get("field_normalized_citation_percentile"))
        year = _percentile(popularity.get("year_normalized_citation_percentile"))
        if field is not None:
            field_values.append(field)
        if year is not None:
            year_values.append(year)
    components = {
        "mean_field_normalized_citation_percentile": (
            fmean(field_values) / 100.0 if field_values else None
        ),
        "mean_year_normalized_citation_percentile": (
            fmean(year_values) / 100.0 if year_values else None
        ),
    }
    values = [value for value in components.values() if value is not None]
    return {
        "score": fmean(values) if values else None,
        "tier": None,
        "components": components,
        "components_available": len(values),
        "missing_components": [name for name, value in components.items() if value is None],
    }


def _evidence_completeness(papers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not papers:
        rates = {
            "usable_abstract_rate": None,
            "authorship_metadata_rate": None,
            "topic_metadata_rate": None,
            "open_access_metadata_rate": None,
            "complexity_metadata_rate": None,
        }
        return {"score": None, "components": rates, "paper_count": 0}
    denominator = len(papers)
    rates = {
        "usable_abstract_rate": sum(
            _clean_string(paper.get("reconstructed_abstract")) is not None for paper in papers
        )
        / denominator,
        "authorship_metadata_rate": sum(
            bool(_mappings(paper.get("authorships"))) for paper in papers
        )
        / denominator,
        "topic_metadata_rate": sum(bool(_paper_topics(paper)) for paper in papers) / denominator,
        "open_access_metadata_rate": sum(
            isinstance(paper.get("open_access"), Mapping) for paper in papers
        )
        / denominator,
        "complexity_metadata_rate": sum(_complexity_score(paper) is not None for paper in papers)
        / denominator,
    }
    return {"score": fmean(rates.values()), "components": rates, "paper_count": denominator}


def _synthesis_difficulty(components: Mapping[str, float | None]) -> dict[str, Any]:
    score, denominator, available, missing = _weighted_available_mean(components, SYNTHESIS_WEIGHTS)
    return {
        "score": score,
        "tier": None,
        "provisional_tier": _synthesis_tier(score),
        "score_version": SYNTHESIS_DIFFICULTY_VERSION,
        "human_reviewed": False,
        "components": dict(components),
        "component_weights": dict(SYNTHESIS_WEIGHTS),
        "available_components": available,
        "missing_components": missing,
        "weight_denominator": denominator,
    }


def _weighted_available_mean(
    components: Mapping[str, float | None], weights: Mapping[str, float]
) -> tuple[float | None, float, list[str], list[str]]:
    available = [name for name in weights if components.get(name) is not None]
    missing = [name for name in weights if components.get(name) is None]
    denominator = math.fsum(weights[name] for name in available)
    if denominator == 0.0:
        return None, 0.0, available, missing
    score = math.fsum(float(components[name]) * weights[name] for name in available) / denominator
    return score, denominator, available, missing


def _temporal_research_evolution(
    papers: Sequence[Mapping[str, Any]], topics: Sequence[Mapping[str, Any] | None]
) -> float | None:
    dated = sorted(
        (
            (year, _paper_identifier(paper, index), topic)
            for index, (paper, topic) in enumerate(zip(papers, topics, strict=True))
            if topic is not None and (year := _year(paper.get("publication_year"))) is not None
        ),
        key=lambda item: (item[0], item[1]),
    )
    if len(dated) < 2 or dated[0][0] == dated[-1][0]:
        return None
    distances = [
        1.0 - _topic_similarity(left[2], right[2])
        for left, right in zip(dated, dated[1:], strict=False)
    ]
    return fmean(distances)


def _topic_similarity(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    left_topic = _topic_identifier(left)
    right_topic = _topic_identifier(right)
    if left_topic is not None and left_topic == right_topic:
        return 1.0
    for level, similarity in (("subfield", 0.85), ("field", 0.70), ("domain", 0.60)):
        left_value = _hierarchy_identifier(left, level)
        right_value = _hierarchy_identifier(right, level)
        if left_value is not None and left_value == right_value:
            return similarity
    return 0.0


def _paper_topics(paper: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    topics = _mappings(paper.get("topics"))
    primary = paper.get("primary_topic")
    if isinstance(primary, Mapping):
        topics = [primary, *topics]
    deduplicated: dict[str, Mapping[str, Any]] = {}
    for index, topic in enumerate(topics):
        key = _topic_identifier(topic) or f"missing-id:{index}:{_topic_label(topic)}"
        deduplicated.setdefault(key, topic)
    return list(deduplicated.values())


def _primary_topic(paper: Mapping[str, Any]) -> Mapping[str, Any] | None:
    primary = paper.get("primary_topic")
    if isinstance(primary, Mapping) and _topic_has_hierarchy(primary):
        return primary
    topics = _paper_topics_without_primary(paper)
    return topics[0] if topics else None


def _paper_topics_without_primary(paper: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [topic for topic in _mappings(paper.get("topics")) if _topic_has_hierarchy(topic)]


def _topic_has_hierarchy(topic: Mapping[str, Any]) -> bool:
    return _topic_identifier(topic) is not None or any(
        _hierarchy_identifier(topic, level) is not None for level in ("subfield", "field", "domain")
    )


def _looks_like_topic(value: Mapping[str, Any]) -> bool:
    if any(
        key in value
        for key in (
            "primary_topic",
            "topics",
            "paper_id",
            "openalex_work_id",
            "publication_year",
            "professor_id",
        )
    ):
        return False
    return any(
        key in value
        for key in (
            "id",
            "topic_id",
            "topic",
            "display_name",
            "subfield",
            "subfield_id",
            "field",
            "field_id",
            "domain",
            "domain_id",
        )
    )


def _topic_identifier(topic: Mapping[str, Any] | None) -> str | None:
    if topic is None:
        return None
    for key in ("topic_id", "id", "topic", "display_name"):
        if (identifier := _identifier_value(topic.get(key))) is not None:
            return identifier
    return None


def _hierarchy_identifier(topic: Mapping[str, Any], level: str) -> str | None:
    direct = _identifier_value(topic.get(f"{level}_id"))
    if direct is not None:
        return direct
    value = topic.get(level)
    if isinstance(value, Mapping):
        return _identifier_value(value.get("id")) or _identifier_value(value.get("display_name"))
    return _identifier_value(value)


def _cluster_identity(topic: Mapping[str, Any]) -> tuple[str, str, str, str | None]:
    for level in ("field", "subfield", "domain"):
        identifier = _hierarchy_identifier(topic, level)
        if identifier is not None:
            return (
                f"{level}:{identifier}",
                level,
                identifier,
                _hierarchy_label(topic, level),
            )
    identifier = _topic_identifier(topic) or "unknown"
    return f"topic:{identifier}", "topic", identifier, _topic_label(topic)


def _hierarchy_label(topic: Mapping[str, Any], level: str) -> str | None:
    value = topic.get(level)
    if isinstance(value, Mapping):
        return _clean_string(value.get("display_name")) or _clean_string(value.get("name"))
    return _clean_string(value)


def _topic_label(topic: Mapping[str, Any]) -> str | None:
    return _clean_string(topic.get("topic")) or _clean_string(topic.get("display_name"))


def _hierarchy_values(
    topics_by_paper: Sequence[Sequence[Mapping[str, Any]]], level: str
) -> list[str]:
    return [
        identifier
        for topics in topics_by_paper
        for topic in topics
        if (identifier := _hierarchy_identifier(topic, level)) is not None
    ]


def _controlled_tags(paper: Mapping[str, Any], kind: str) -> list[str]:
    direct_key = "method_tags" if kind == "method" else "dataset_population_tags"
    direct = _strings(paper.get(direct_key))
    if direct:
        return sorted(set(direct))
    paper_features = paper.get("paper_features")
    if not isinstance(paper_features, Mapping):
        return []
    indicators = paper_features.get("controlled_indicators")
    if not isinstance(indicators, Mapping):
        return []
    return sorted(set(_strings(indicators.get(kind))))


def _complexity_score(paper: Mapping[str, Any]) -> float | None:
    complexity = paper.get("complexity")
    value = complexity.get("score") if isinstance(complexity, Mapping) else None
    if value is None:
        value = paper.get("complexity_score")
    return _bounded_number(value, minimum=0.0, maximum=100.0)


def _portfolio_author_id(paper: Mapping[str, Any]) -> str | None:
    direct = _clean_string(paper.get("openalex_author_id"))
    if direct is not None:
        return direct
    consistency = paper.get("openalex_consistency")
    if isinstance(consistency, Mapping):
        return _clean_string(consistency.get("expected_author_id"))
    return None


def _numeric_distribution(values: Sequence[float], total: int) -> dict[str, Any]:
    return {
        "mean": fmean(values) if values else None,
        "median": median(values) if values else None,
        "minimum": min(values) if values else None,
        "maximum": max(values) if values else None,
        "papers_available": len(values),
        "papers_missing": total - len(values),
    }


def _normalized_entropy(values: Iterable[str]) -> float | None:
    counts = Counter(values)
    total = sum(counts.values())
    if total == 0:
        return None
    if len(counts) == 1:
        return 0.0
    entropy = -math.fsum((count / total) * math.log2(count / total) for count in counts.values())
    return entropy / math.log2(len(counts))


def _normalized_unique_count(values: Sequence[str], denominator: int) -> float | None:
    if not values or denominator < 1:
        return None
    return min(1.0, len(set(values)) / denominator)


def _normalized_count(count: int, observations: int) -> float | None:
    if observations < 1 or count < 1:
        return None
    if observations == 1:
        return 0.0
    return min(1.0, (count - 1) / (observations - 1))


def _synthesis_tier(score: float | None) -> str | None:
    if score is None:
        return None
    if score < 0.33:
        return "low"
    if score < 0.67:
        return "medium"
    return "high"


def _paper_identifier(paper: Mapping[str, Any], index: int) -> str:
    for key in ("paper_id", "openalex_work_id", "id"):
        if (identifier := _clean_string(paper.get(key))) is not None:
            return identifier
    return f"paper-index-{index}"


def _identifier_value(value: Any) -> str | None:
    if isinstance(value, Mapping):
        value = value.get("id") or value.get("display_name") or value.get("name")
    return _clean_string(value)


def _clean_string(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _strings(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [normalized for item in value if (normalized := _clean_string(item)) is not None]


def _mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _year(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 9999:
        return value
    return None


def _percentile(value: Any) -> float | None:
    return _bounded_number(value, minimum=0.0, maximum=100.0)


def _bounded_number(value: Any, *, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric) or not minimum <= numeric <= maximum:
        return None
    return numeric


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
    except (OSError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    if arguments.dry_run:
        print(json.dumps(stage_plan(SPEC, arguments, config.raw), indent=2, sort_keys=True))
        return 0
    if arguments.resume or arguments.restart:
        parser.error("Stage 8 is deterministic and does not use collection checkpoints")
    if not arguments.input or not arguments.output:
        parser.error("--input and --output are required for portfolio scoring")

    logger = configure_logging(arguments.log_file)
    try:
        records = _limit_records_by_profile(read_jsonl(arguments.input), arguments.limit)
        scored = score_portfolios(records)
        write_jsonl_atomic(Path(arguments.output), scored, force=arguments.force)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        log_failure(logger, SPEC, None, error)
        parser.error(str(error))
    print(f"wrote {len(scored)} records to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
