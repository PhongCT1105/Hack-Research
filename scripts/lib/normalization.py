"""Loss-aware normalization contracts for raw OpenAlex records."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
from urllib.parse import urlparse


INSTITUTION_CSV_COLUMNS = (
    "institution_id",
    "openalex_id",
    "ror_id",
    "name",
    "country",
    "region",
    "institution_type",
    "works_count",
    "cited_by_count",
    "homepage_url",
)

AUTHOR_CANDIDATE_CSV_COLUMNS = (
    "openalex_author_id",
    "display_name",
    "orcid",
    "last_known_institution",
    "works_count",
    "cited_by_count",
    "h_index",
    "first_publication_year",
    "last_publication_year",
    "primary_domain",
    "primary_field",
    "primary_subfield",
    "candidate_status",
)

CANDIDATE_PAPER_CSV_COLUMNS = (
    "professor_id",
    "paper_id",
    "openalex_work_id",
    "doi",
    "title",
    "publication_year",
    "venue",
    "citation_count",
    "citation_percentile_field_year",
    "abstract_available",
    "full_text_available",
    "open_access",
    "topic_ids",
    "primary_topic",
    "method_tags",
    "complexity_score",
    "complexity_tier",
    "selected",
    "selection_reason",
    "focal",
    "ownership_verified",
)


def canonical_openalex_id(value: str | None) -> str | None:
    """Return an OpenAlex identifier without its provider URL prefix."""

    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("OpenAlex IDs must be strings or null")
    candidate = value.strip()
    if not candidate:
        raise ValueError("OpenAlex IDs must not be empty")

    parsed = urlparse(candidate)
    if parsed.scheme and parsed.netloc:
        hostname = (parsed.hostname or "").lower()
        if hostname not in {"openalex.org", "www.openalex.org", "api.openalex.org"}:
            return candidate
        path_parts = [part for part in parsed.path.split("/") if part]
        if not path_parts:
            raise ValueError("OpenAlex URL does not contain an identifier")
        return path_parts[-1]
    return candidate.rstrip("/")


def normalize_institution(
    raw: Mapping[str, Any], *, institution_id: str | None = None
) -> dict[str, Any]:
    """Normalize one OpenAlex institution without changing the source mapping."""

    record = _copy_entity_tree(raw)
    openalex_id = canonical_openalex_id(_optional_string(raw.get("id")))
    provider_url = _provider_url(_optional_string(raw.get("id")), openalex_id)
    geo = raw.get("geo") if isinstance(raw.get("geo"), Mapping) else {}
    lineage = _collection(raw.get("lineage"))

    record.update(
        {
            "id": openalex_id,
            "institution_id": institution_id or openalex_id,
            "openalex_id": openalex_id,
            "openalex_url": provider_url,
            "ror_id": deepcopy(raw.get("ror")),
            "name": deepcopy(raw.get("display_name")),
            "country": deepcopy(raw.get("country_code")),
            "region": deepcopy(geo.get("region")),
            "institution_type": deepcopy(raw.get("type")),
            "works_count": deepcopy(raw.get("works_count")),
            "cited_by_count": deepcopy(raw.get("cited_by_count")),
            "homepage_url": deepcopy(raw.get("homepage_url")),
            "lineage": _canonical_reference_list(lineage),
            "lineage_urls": _provider_reference_list(lineage),
        }
    )
    return record


def normalize_author(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one OpenAlex author and retain identity-screening evidence."""

    record = _copy_entity_tree(raw)
    openalex_id = canonical_openalex_id(_optional_string(raw.get("id")))
    counts_by_year = _collection(raw.get("counts_by_year"))
    summary_stats = raw.get("summary_stats")
    summary = summary_stats if isinstance(summary_stats, Mapping) else {}
    first_year, last_year = _publication_year_bounds(counts_by_year)
    first_year = _valid_year(summary.get("first_publication_year")) or first_year
    last_year = _valid_year(summary.get("last_publication_year")) or last_year

    institutions = [
        _copy_entity_tree(item)
        for item in _collection(raw.get("last_known_institutions"))
        if isinstance(item, Mapping)
    ]
    affiliations = [
        _copy_entity_tree(item)
        for item in _collection(raw.get("affiliations"))
        if isinstance(item, Mapping)
    ]
    topics = [
        _normalize_topic(item)
        for item in _collection(raw.get("topics"))
        if isinstance(item, Mapping)
    ]
    primary_topic = topics[0] if topics else None

    record.update(
        {
            "id": openalex_id,
            "openalex_author_id": openalex_id,
            "openalex_author_url": _provider_url(_optional_string(raw.get("id")), openalex_id),
            "display_name": deepcopy(raw.get("display_name")),
            "orcid": deepcopy(raw.get("orcid")),
            "last_known_institutions": institutions,
            "last_known_institution": (
                deepcopy(institutions[0].get("display_name")) if institutions else None
            ),
            "affiliations": affiliations,
            "topics": topics,
            "topic_share": _copy_entity_tree(_collection(raw.get("topic_share"))),
            "x_concepts": _copy_entity_tree(_collection(raw.get("x_concepts"))),
            "counts_by_year": deepcopy(counts_by_year),
            "summary_stats": deepcopy(summary_stats),
            "works_count": deepcopy(raw.get("works_count")),
            "cited_by_count": deepcopy(raw.get("cited_by_count")),
            "h_index": deepcopy(summary.get("h_index")),
            "first_publication_year": first_year,
            "last_publication_year": last_year,
            "primary_domain": primary_topic["domain"] if primary_topic else None,
            "primary_field": primary_topic["field"] if primary_topic else None,
            "primary_subfield": primary_topic["subfield"] if primary_topic else None,
            "faculty_status_verified": False,
            "quality_status": "needs_enrichment",
        }
    )
    record["candidate_status"] = author_candidate_status(record)
    return record


def author_candidate_status(
    author: Mapping[str, Any],
    *,
    minimum_works: int = 8,
    recent_activity_year: int = 2021,
    require_institution: bool = True,
    require_topics: bool = True,
) -> str:
    """Classify an author using only observable OpenAlex candidate signals."""

    works_count = author.get("works_count")
    if (
        not isinstance(works_count, int)
        or isinstance(works_count, bool)
        or works_count < minimum_works
    ):
        return "ineligible_insufficient_works"

    last_year = author.get("last_publication_year")
    if (
        not isinstance(last_year, int)
        or isinstance(last_year, bool)
        or last_year < recent_activity_year
    ):
        return "ineligible_no_recent_activity"

    if require_institution and not _collection(author.get("last_known_institutions")):
        return "ineligible_no_institution"
    if require_topics and not _collection(author.get("topics")):
        return "ineligible_no_topics"
    return "eligible"


def normalize_work(raw: Mapping[str, Any], *, professor_id: str) -> dict[str, Any]:
    """Normalize one OpenAlex work while retaining publication evidence fields."""

    record = _copy_entity_tree(raw)
    openalex_id = canonical_openalex_id(_optional_string(raw.get("id")))
    topics = [
        _normalize_topic(item)
        for item in _collection(raw.get("topics"))
        if isinstance(item, Mapping)
    ]
    primary_topic_raw = raw.get("primary_topic")
    primary_topic = (
        _normalize_topic(primary_topic_raw) if isinstance(primary_topic_raw, Mapping) else None
    )
    primary_location = _copy_optional_mapping(raw.get("primary_location"))
    referenced_works = _collection(raw.get("referenced_works"))
    related_works = _collection(raw.get("related_works"))
    source = (
        primary_location.get("source")
        if isinstance(primary_location, Mapping)
        and isinstance(primary_location.get("source"), Mapping)
        else {}
    )

    record.update(
        {
            "id": openalex_id,
            "professor_id": professor_id,
            "paper_id": openalex_id,
            "openalex_work_id": openalex_id,
            "openalex_work_url": _provider_url(_optional_string(raw.get("id")), openalex_id),
            "doi": deepcopy(raw.get("doi")),
            "title": deepcopy(raw.get("title")),
            "publication_year": deepcopy(raw.get("publication_year")),
            "publication_date": deepcopy(raw.get("publication_date")),
            "type": deepcopy(raw.get("type")),
            "type_crossref": deepcopy(raw.get("type_crossref")),
            "language": deepcopy(raw.get("language")),
            "venue": deepcopy(source.get("display_name")),
            "primary_location": primary_location,
            "locations": [
                _copy_entity_tree(item)
                for item in _collection(raw.get("locations"))
                if isinstance(item, Mapping)
            ],
            "best_oa_location": _copy_optional_mapping(raw.get("best_oa_location")),
            "open_access": _copy_optional_mapping(raw.get("open_access")),
            "authorships": [
                _copy_entity_tree(item)
                for item in _collection(raw.get("authorships"))
                if isinstance(item, Mapping)
            ],
            "abstract_inverted_index": deepcopy(raw.get("abstract_inverted_index")),
            "topics": topics,
            "primary_topic": primary_topic,
            "keywords": _copy_entity_tree(_collection(raw.get("keywords"))),
            "concepts": _copy_entity_tree(_collection(raw.get("concepts"))),
            "mesh": _copy_entity_tree(_collection(raw.get("mesh"))),
            "cited_by_count": deepcopy(raw.get("cited_by_count")),
            "citation_count": deepcopy(raw.get("cited_by_count")),
            "referenced_works": _canonical_reference_list(referenced_works),
            "referenced_work_urls": _provider_reference_list(referenced_works),
            "related_works": _canonical_reference_list(related_works),
            "related_work_urls": _provider_reference_list(related_works),
            "counts_by_year": deepcopy(_collection(raw.get("counts_by_year"))),
            "is_retracted": deepcopy(raw.get("is_retracted")),
            "is_paratext": deepcopy(raw.get("is_paratext")),
        }
    )
    return record


def _normalize_topic(raw: Mapping[str, Any]) -> dict[str, Any]:
    topic = deepcopy(dict(raw))
    topic_id = canonical_openalex_id(_optional_string(raw.get("id")))
    topic_name = deepcopy(raw.get("display_name"))
    topic.pop("id", None)
    topic.pop("display_name", None)
    for level in ("subfield", "field", "domain"):
        hierarchy = raw.get(level) if isinstance(raw.get(level), Mapping) else {}
        hierarchy_id = canonical_openalex_id(_optional_string(hierarchy.get("id")))
        topic[level] = deepcopy(hierarchy.get("display_name"))
        topic[f"{level}_id"] = hierarchy_id
        topic[f"{level}_url"] = _provider_url(_optional_string(hierarchy.get("id")), hierarchy_id)
    topic.update(
        {
            "topic_id": topic_id,
            "topic": topic_name,
            "topic_url": _provider_url(_optional_string(raw.get("id")), topic_id),
        }
    )
    return topic


def _publication_year_bounds(counts_by_year: list[Any]) -> tuple[int | None, int | None]:
    years = [
        year
        for item in counts_by_year
        if isinstance(item, Mapping)
        and (year := _valid_year(item.get("year"))) is not None
        and isinstance(item.get("works_count"), int)
        and not isinstance(item.get("works_count"), bool)
        and item["works_count"] > 0
    ]
    return (min(years), max(years)) if years else (None, None)


def _valid_year(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 9999:
        return value
    return None


def _copy_optional_mapping(value: Any) -> dict[str, Any] | None:
    return _copy_entity_tree(value) if isinstance(value, Mapping) else None


def _copy_entity_tree(value: Any) -> Any:
    if isinstance(value, Mapping):
        copied = {key: _copy_entity_tree(item) for key, item in value.items()}
        identifier = _optional_string(value.get("id"))
        if identifier is not None and _is_openalex_url(identifier):
            copied["id"] = canonical_openalex_id(identifier)
            copied["openalex_url"] = identifier
        for key, item in value.items():
            if isinstance(item, str) and _is_openalex_url(item):
                if key == "openalex":
                    copied[key] = canonical_openalex_id(item)
                    copied["openalex_url"] = item
                elif key.endswith("_id"):
                    copied[key] = canonical_openalex_id(item)
                    copied[f"{key[:-3]}_url"] = item
                elif key in {"funder", "host_organization"}:
                    copied[key] = canonical_openalex_id(item)
                    copied[f"{key}_url"] = item
            elif isinstance(item, (list, tuple)):
                url_key = _identifier_list_url_key(key)
                if url_key is not None:
                    copied[key] = _canonical_reference_list(list(item))
                    copied[url_key] = _provider_reference_list(list(item))
        return copied
    if isinstance(value, list):
        return [_copy_entity_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_copy_entity_tree(item) for item in value)
    return deepcopy(value)


def _collection(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _canonical_reference_list(values: list[Any]) -> list[Any]:
    return [
        canonical_openalex_id(value) if isinstance(value, str) else deepcopy(value)
        for value in values
    ]


def _provider_reference_list(values: list[Any]) -> list[Any]:
    return [
        _provider_url(value, canonical_openalex_id(value))
        if isinstance(value, str)
        else deepcopy(value)
        for value in values
    ]


def _identifier_list_url_key(key: Any) -> str | None:
    if not isinstance(key, str):
        return None
    if key.endswith("_ids"):
        return f"{key[:-4]}_urls"
    if key == "lineage" or key.endswith("_lineage"):
        return f"{key}_urls"
    return None


def _provider_url(value: str | None, canonical_id: str | None) -> str | None:
    if value is None or canonical_id is None:
        return None
    return value if _is_openalex_url(value) else f"https://openalex.org/{canonical_id}"


def _is_openalex_url(value: str) -> bool:
    parsed = urlparse(value)
    return (parsed.hostname or "").lower() in {
        "openalex.org",
        "www.openalex.org",
        "api.openalex.org",
    }


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None
