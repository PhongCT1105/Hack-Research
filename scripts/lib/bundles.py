"""Anonymous provisional OpenAlex profile bundles and stable enrichment tasks."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import re
from typing import Any, Mapping, Sequence
import unicodedata

from .normalization import canonical_openalex_id


BUNDLE_SCHEMA_VERSION = "1.0.0"
GLOBAL_ENRICHMENT_TASKS = (
    "verify_faculty_status",
    "resolve_author_identity",
    "reconcile_crossref_metadata",
    "reconcile_semantic_scholar_ownership",
    "review_topic_coherence",
    "review_synthesis_difficulty",
)
FOCAL_ENRICHMENT_TASKS = (
    "retrieve_legal_full_text",
    "extract_focal_passages",
)
MISSING_FINAL_GATES = (*GLOBAL_ENRICHMENT_TASKS, *FOCAL_ENRICHMENT_TASKS)
PORTFOLIO_DIMENSIONS = (
    "visibility",
    "research_breadth",
    "topic_coherence_aid",
    "method_diversity",
    "paper_complexity",
    "synthesis_difficulty",
)
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "author",
        "authors",
        "authorship",
        "authorships",
        "displayname",
        "facultytitle",
        "name",
        "passage",
        "passages",
        "passagetext",
        "reconstructedabstract",
        "abstractinvertedindex",
    }
)


def build_openalex_bundle(
    profile: Mapping[str, Any],
    selected_papers: Sequence[Mapping[str, Any]],
    focal_ids: Sequence[str],
    provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Build one anonymous, explicitly non-final OpenAlex profile bundle.

    Inputs are copied into a smaller public/provisional contract. Author and institution display
    names, authorship lists, abstracts, and passages are deliberately not copied.
    """

    if not isinstance(profile, Mapping):
        raise TypeError("profile must be a mapping")
    if not isinstance(provenance, Mapping):
        raise TypeError("provenance must be a mapping")

    professor_id = _required_string(profile.get("professor_id"), "professor_id")
    dataset_version = _required_string(profile.get("dataset_version"), "dataset_version")
    candidate_pool_version = _required_string(
        profile.get("candidate_pool_version") or provenance.get("candidate_pool_version"),
        "candidate_pool_version",
    )
    bundle_version = _required_string(
        profile.get("bundle_version") or provenance.get("bundle_version"), "bundle_version"
    )
    author_id = _required_openalex_id(
        profile.get("openalex_author_id") or profile.get("openalex_id") or profile.get("id"),
        "A",
        "openalex_author_id",
    )

    papers = _selected_paper_records(selected_papers, professor_id)
    selected_ids = [paper["paper_id"] for paper in papers]
    focal_paper_ids = _focal_paper_ids(focal_ids, selected_ids)
    focal_set = set(focal_paper_ids)
    for paper in papers:
        paper["focal"] = paper["paper_id"] in focal_set
    normalized_provenance = _provenance(provenance, author_id, papers)

    bundle: dict[str, Any] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "dataset_version": dataset_version,
        "candidate_pool_version": candidate_pool_version,
        "bundle_version": bundle_version,
        "professor_id": professor_id,
        "openalex_author_id": author_id,
        "openalex_author_url": f"https://openalex.org/{author_id}",
        "openalex_profile": _openalex_profile(profile),
        "portfolio_dimensions": _portfolio_dimensions(profile),
        "openalex_consistency": _openalex_consistency(profile),
        "selected_papers": papers,
        "focal_paper_ids": focal_paper_ids,
        "provenance": normalized_provenance,
        "missing_final_gates": list(MISSING_FINAL_GATES),
        "enrichment_tasks": [],
        "final_evidence_packet_ready": False,
    }
    bundle["enrichment_tasks"] = build_enrichment_tasks(bundle)
    return bundle


def build_enrichment_tasks(bundle: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return deterministic pending tasks for every gate absent from a provisional bundle."""

    if not isinstance(bundle, Mapping):
        raise TypeError("bundle must be a mapping")
    bundle_version = _required_string(bundle.get("bundle_version"), "bundle_version")
    professor_id = _required_string(bundle.get("professor_id"), "professor_id")
    focal_ids = _focal_paper_ids(
        bundle.get("focal_paper_ids"),
        [
            _required_string(paper.get("paper_id"), "selected paper_id")
            for paper in _mapping_sequence(bundle.get("selected_papers"), "selected_papers")
        ],
    )

    tasks: list[dict[str, Any]] = []
    for task_type in GLOBAL_ENRICHMENT_TASKS:
        tasks.append(_task(bundle_version, professor_id, task_type))
    for paper_id in focal_ids:
        for task_type in FOCAL_ENRICHMENT_TASKS:
            tasks.append(_task(bundle_version, professor_id, task_type, paper_id))
    return tasks


def validate_enrichment_tasks(bundle: Mapping[str, Any]) -> None:
    """Require exactly the deterministic global and per-focal tasks for this bundle."""

    if not isinstance(bundle, Mapping):
        raise TypeError("bundle must be a mapping")
    actual = _mapping_sequence(bundle.get("enrichment_tasks"), "enrichment_tasks")
    expected = build_enrichment_tasks(bundle)
    if len(actual) != len(expected):
        raise ValueError(f"enrichment task count must be exactly {len(expected)}")

    task_ids = [_required_string(task.get("task_id"), "enrichment task_id") for task in actual]
    if len(set(task_ids)) != len(task_ids):
        raise ValueError("enrichment task IDs must be unique")

    expected_by_scope = {(task["task_type"], task.get("paper_id")): task for task in expected}
    actual_by_scope: dict[tuple[str, Any], Mapping[str, Any]] = {}
    for task in actual:
        task_type = _required_string(task.get("task_type"), "enrichment task_type")
        scope = (task_type, task.get("paper_id"))
        if scope in actual_by_scope:
            raise ValueError(f"enrichment task scope is repeated: {scope!r}")
        actual_by_scope[scope] = task

    if set(actual_by_scope) != set(expected_by_scope):
        raise ValueError("enrichment task types and focal-paper scopes do not match required gates")
    for scope, expected_task in expected_by_scope.items():
        if actual_by_scope[scope].get("task_id") != expected_task["task_id"]:
            raise ValueError(f"enrichment task has an invalid stable hash: {scope!r}")


def validate_openalex_bundle_semantics(bundle: Mapping[str, Any]) -> None:
    """Validate cross-field invariants that JSON Schema cannot express."""

    if not isinstance(bundle, Mapping):
        raise TypeError("bundle must be a mapping")
    _validate_anonymous_keys(bundle)
    papers = _mapping_sequence(bundle.get("selected_papers"), "selected_papers")
    if len(papers) != 8:
        raise ValueError("selected_papers must contain exactly 8 records")
    paper_ids = [_paper_work_id(paper) for paper in papers]
    if len(set(paper_ids)) != len(paper_ids):
        raise ValueError("selected paper OpenAlex work IDs must be unique")
    focal_ids = _focal_paper_ids(bundle.get("focal_paper_ids"), paper_ids)
    focal_set = set(focal_ids)
    if any(
        (paper.get("focal") is True) != (_paper_work_id(paper) in focal_set) for paper in papers
    ):
        raise ValueError("selected paper focal flags must match focal_paper_ids")
    if set(bundle.get("missing_final_gates", ())) != set(MISSING_FINAL_GATES):
        raise ValueError("missing_final_gates must enumerate every provisional enrichment gate")
    validate_enrichment_tasks(bundle)


def _task(
    bundle_version: str,
    professor_id: str,
    task_type: str,
    paper_id: str | None = None,
) -> dict[str, Any]:
    identity = [bundle_version, professor_id, task_type, paper_id]
    encoded = json.dumps(identity, ensure_ascii=True, separators=(",", ":"))
    task = {
        "task_id": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        "task_type": task_type,
        "status": "pending",
        "required_for_final": True,
    }
    if paper_id is not None:
        task["paper_id"] = paper_id
    return task


def _selected_paper_records(
    selected_papers: Sequence[Mapping[str, Any]], professor_id: str
) -> list[dict[str, Any]]:
    papers = _mapping_sequence(selected_papers, "selected_papers")
    if len(papers) != 8:
        raise ValueError("selected_papers must contain exactly 8 records")

    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in papers:
        source_professor_id = source.get("professor_id")
        if (
            source_professor_id is not None
            and _required_string(source_professor_id, "selected paper professor_id") != professor_id
        ):
            raise ValueError("selected paper professor_id does not match bundle professor_id")
        work_id = _paper_work_id(source)
        paper_id = work_id
        if paper_id in seen:
            raise ValueError(f"duplicate selected paper_id {paper_id}")
        seen.add(paper_id)

        record: dict[str, Any] = {
            "paper_id": paper_id,
            "openalex_work_id": work_id,
            "openalex_url": f"https://openalex.org/{work_id}",
            "title": _required_string(source.get("title"), f"title for {paper_id}"),
        }
        _copy_if_present(
            record,
            source,
            (
                "doi",
                "publication_year",
                "publication_date",
                "work_type",
                "type",
                "venue",
                "language",
                "primary_topic",
                "topics",
                "method_tags",
                "dataset_population_tags",
                "popularity",
                "complexity",
                "availability",
                "open_access",
                "best_oa_location",
                "selection",
                "selection_reason",
                "focal_selection",
                "consistency_status",
                "consistency_issue_codes",
            ),
        )
        record["selected"] = True
        record["focal"] = source.get("focal") is True
        output.append(record)
    return output


def _focal_paper_ids(value: Any, selected_ids: Sequence[str]) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("focal_ids must be a sequence of OpenAlex work IDs")
    focal_ids = [_required_openalex_id(item, "W", "focal paper ID") for item in value]
    if len(focal_ids) != 2 or len(set(focal_ids)) != 2:
        raise ValueError("focal_ids must contain exactly 2 unique paper IDs")
    if not set(focal_ids).issubset(set(selected_ids)):
        raise ValueError("every focal paper must be selected")
    return focal_ids


def _paper_work_id(paper: Mapping[str, Any]) -> str:
    candidates: dict[str, str] = {}
    for key in ("paper_id", "openalex_work_id", "openalex_url", "id"):
        value = paper.get(key)
        if value is None:
            continue
        candidates[key] = _required_openalex_id(value, "W", f"selected paper {key}")
    if not candidates:
        raise ValueError("selected paper must contain an OpenAlex work identifier")
    if len(set(candidates.values())) != 1:
        raise ValueError(
            "selected paper identifiers must reference the same OpenAlex work: "
            + ", ".join(f"{key}={value}" for key, value in candidates.items())
        )
    return next(iter(candidates.values()))


def _openalex_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "institutions": _institutions(profile),
        "topic_ids": _topic_ids(profile.get("primary_topics") or profile.get("topics") or []),
    }
    _copy_if_present(
        result,
        profile,
        (
            "works_count",
            "cited_by_count",
            "h_index",
            "first_publication_year",
            "last_publication_year",
            "primary_domain",
            "primary_field",
            "primary_subfield",
            "orcid",
        ),
    )
    career = profile.get("career_estimate")
    if not isinstance(career, Mapping):
        career = {
            "stage": profile.get("career_stage"),
            "source": profile.get("career_stage_source") or "estimated_from_first_publication_year",
            "first_publication_year": profile.get("first_publication_year"),
        }
    result["career_estimate"] = _sanitize_value(career)
    return result


def _institutions(profile: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = (
        profile.get("last_known_institutions")
        or profile.get("institutions")
        or ([profile["institution"]] if isinstance(profile.get("institution"), Mapping) else [])
    )
    if isinstance(value, Mapping):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    institutions: list[dict[str, Any]] = []
    for institution in value:
        if not isinstance(institution, Mapping):
            continue
        raw_id = (
            institution.get("openalex_id")
            or institution.get("institution_id")
            or institution.get("id")
        )
        if not isinstance(raw_id, str) or not raw_id.strip():
            continue
        institution_id = _required_openalex_id(raw_id, "I", "OpenAlex institution ID")
        normalized: dict[str, Any] = {
            "openalex_institution_id": institution_id,
            "openalex_url": f"https://openalex.org/{institution_id}",
        }
        aliases = {
            "country": "country_code",
            "country_code": "country_code",
            "region": "region",
            "type": "institution_type",
            "institution_type": "institution_type",
            "ror": "ror_id",
            "ror_id": "ror_id",
        }
        for source_key, destination_key in aliases.items():
            if source_key in institution and destination_key not in normalized:
                normalized[destination_key] = _sanitize_value(institution[source_key])
        institutions.append(normalized)
    return institutions


def _topic_ids(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    output: list[str] = []
    for topic in value:
        raw = topic
        if isinstance(topic, Mapping):
            raw = topic.get("topic_id") or topic.get("id") or topic.get("openalex_id")
        if not isinstance(raw, str) or not raw.strip():
            continue
        identifier = canonical_openalex_id(raw)
        if identifier is not None and identifier.startswith("T") and identifier not in output:
            output.append(identifier)
    return output


def _portfolio_dimensions(profile: Mapping[str, Any]) -> dict[str, Any]:
    container = profile.get("portfolio_dimensions")
    if not isinstance(container, Mapping):
        container = profile
    output: dict[str, Any] = {}
    for dimension in PORTFOLIO_DIMENSIONS:
        aliases = (
            ("topic_coherence_aid", "topic_coherence")
            if dimension == "topic_coherence_aid"
            else (dimension,)
        )
        value = next((container[key] for key in aliases if key in container), None)
        if isinstance(value, Mapping):
            output[dimension] = _sanitize_value(value)
        else:
            output[dimension] = {
                "score": _sanitize_value(value),
                "components": {},
                "missing": True,
            }
    return output


def _openalex_consistency(profile: Mapping[str, Any]) -> dict[str, Any]:
    value = profile.get("openalex_consistency")
    if not isinstance(value, Mapping):
        value = {
            "status": profile.get("consistency_status") or "unassessed",
            "issue_codes": profile.get("consistency_issue_codes") or [],
            "scope": "within_openalex",
            "externally_verified": False,
        }
    result = _sanitize_value(value)
    assert isinstance(result, dict)
    result.setdefault("status", "unassessed")
    result.setdefault("issue_codes", [])
    result["scope"] = "within_openalex"
    result["externally_verified"] = False
    return result


def _provenance(
    provenance: Mapping[str, Any], author_id: str, papers: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    raw_hashes = provenance.get("raw_source_hashes") or provenance.get("raw_hashes")
    if not isinstance(raw_hashes, (list, tuple)) or not raw_hashes:
        raise ValueError("provenance must contain raw_source_hashes")
    normalized_hashes: list[str] = []
    for value in raw_hashes:
        checksum = _required_string(value, "raw source hash").lower()
        if not _SHA256.fullmatch(checksum):
            raise ValueError("raw source hashes must be 64-character SHA-256 hex digests")
        if checksum not in normalized_hashes:
            normalized_hashes.append(checksum)

    supplied_urls = provenance.get("openalex_urls") or provenance.get("source_urls") or []
    if isinstance(supplied_urls, str):
        supplied_urls = [supplied_urls]
    if not isinstance(supplied_urls, (list, tuple)):
        raise TypeError("provenance OpenAlex URLs must be a sequence")
    urls = [f"https://openalex.org/{author_id}"]
    urls.extend(str(paper["openalex_url"]) for paper in papers)
    for value in supplied_urls:
        url = _required_string(value, "OpenAlex provenance URL")
        identifier = canonical_openalex_id(url)
        if identifier is None or identifier[:1] not in {"A", "I", "T", "W", "S"}:
            raise ValueError(f"not a canonical OpenAlex entity URL: {url}")
        urls.append(f"https://openalex.org/{identifier}")

    result: dict[str, Any] = {
        "raw_source_hashes": normalized_hashes,
        "openalex_urls": list(dict.fromkeys(urls)),
        "retrieved_at": _required_string(provenance.get("retrieved_at"), "retrieved_at"),
        "collection_code_version": _required_string(
            provenance.get("collection_code_version"), "collection_code_version"
        ),
    }
    for key in ("raw_envelope_version", "job_id"):
        if key in provenance:
            result[key] = _sanitize_value(provenance[key])
    return result


def _mapping_sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{label} must be a sequence of mappings")
    if any(not isinstance(item, Mapping) for item in value):
        raise TypeError(f"every {label} item must be a mapping")
    return list(value)


def _required_openalex_id(value: Any, prefix: str, label: str) -> str:
    identifier = canonical_openalex_id(_required_string(value, label))
    if identifier is None or not re.fullmatch(rf"{prefix}[0-9]+", identifier):
        raise ValueError(f"{label} must be a canonical OpenAlex {prefix} identifier")
    return identifier


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _copy_if_present(
    destination: dict[str, Any], source: Mapping[str, Any], keys: Sequence[str]
) -> None:
    for key in keys:
        if key in source:
            destination[key] = _sanitize_value(source[key])


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_value(item)
            for key, item in value.items()
            if not _is_forbidden_metadata_key(key)
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value]
    return deepcopy(value)


def _validate_anonymous_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _is_forbidden_metadata_key(key):
                raise ValueError(f"forbidden bundle key at {path}: {key!r}")
            _validate_anonymous_keys(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_anonymous_keys(item, f"{path}[{index}]")


def _is_forbidden_metadata_key(value: Any) -> bool:
    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    token = "".join(character for character in normalized if character.isalnum())
    return token in _FORBIDDEN_KEY_TOKENS
