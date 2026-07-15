"""Typed access to dataset collection configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"configuration key {name!r} must be a mapping")
    return value


def _string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"configuration key {name!r} must be a non-empty string")
    return value


def _positive_integer(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"configuration key {name!r} must be a positive integer")
    return value


def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"configuration key {name!r} must be a non-empty list")
    return tuple(_string(item, name) for item in value)


@dataclass(frozen=True)
class OpenAlexSettings:
    """Non-secret OpenAlex client settings and environment-variable names."""

    base_url: str
    api_key_environment_variable: str
    mailto_environment_variable: str
    user_agent: str
    per_page: int
    use_cursor_pagination: bool
    maximum_retries: int
    timeout_seconds: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> OpenAlexSettings:
        use_cursor_pagination = value.get("use_cursor_pagination")
        if not isinstance(use_cursor_pagination, bool):
            raise ValueError(
                "configuration key 'providers.openalex.use_cursor_pagination' must be a boolean"
            )
        return cls(
            base_url=_string(value.get("base_url"), "providers.openalex.base_url"),
            api_key_environment_variable=_string(
                value.get("api_key_environment_variable"),
                "providers.openalex.api_key_environment_variable",
            ),
            mailto_environment_variable=_string(
                value.get("mailto_environment_variable"),
                "providers.openalex.mailto_environment_variable",
            ),
            user_agent=_string(value.get("user_agent"), "providers.openalex.user_agent"),
            per_page=_positive_integer(value.get("per_page"), "providers.openalex.per_page"),
            use_cursor_pagination=use_cursor_pagination,
            maximum_retries=_positive_integer(
                value.get("maximum_retries"), "providers.openalex.maximum_retries"
            ),
            timeout_seconds=_positive_integer(
                value.get("timeout_seconds"), "providers.openalex.timeout_seconds"
            ),
        )


@dataclass(frozen=True)
class DatasetConfig:
    """Validated operational settings plus the full backwards-compatible YAML mapping."""

    dataset_version: str
    candidate_pool_version: str
    random_seed: int
    institution_seed_countries: tuple[str, ...]
    institution_seed_types: tuple[str, ...]
    recent_activity_year: int
    raw_envelope_version: str
    safe_author_limit: int
    bundle_version: str
    openalex: OpenAlexSettings
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> DatasetConfig:
        try:
            import yaml
        except ModuleNotFoundError as error:
            raise RuntimeError(
                'PyYAML is required; install project dependencies with pip install -e ".[dev]"'
            ) from error

        config_path = Path(path)
        if not config_path.is_file():
            raise FileNotFoundError(f"configuration not found: {config_path}")
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"configuration must contain a YAML mapping: {config_path}")

        institution_seed = _mapping(loaded.get("institution_seed"), "institution_seed")
        candidate_pool = _mapping(loaded.get("candidate_pool"), "candidate_pool")
        collection = _mapping(loaded.get("collection"), "collection")
        providers = _mapping(loaded.get("providers"), "providers")
        openalex = _mapping(providers.get("openalex"), "providers.openalex")
        random_seed = loaded.get("random_seed")
        if not isinstance(random_seed, int) or isinstance(random_seed, bool):
            raise ValueError("configuration key 'random_seed' must be an integer")

        recent_activity_year = _positive_integer(
            candidate_pool.get("recent_activity_year"), "candidate_pool.recent_activity_year"
        )
        if recent_activity_year < 1900:
            raise ValueError(
                "configuration key 'candidate_pool.recent_activity_year' must be at least 1900"
            )

        return cls(
            dataset_version=_string(loaded.get("dataset_version"), "dataset_version"),
            candidate_pool_version=_string(
                loaded.get("candidate_pool_version"), "candidate_pool_version"
            ),
            random_seed=random_seed,
            institution_seed_countries=_string_tuple(
                institution_seed.get("countries"), "institution_seed.countries"
            ),
            institution_seed_types=_string_tuple(
                institution_seed.get("types"), "institution_seed.types"
            ),
            recent_activity_year=recent_activity_year,
            raw_envelope_version=_string(
                collection.get("raw_envelope_version"), "collection.raw_envelope_version"
            ),
            safe_author_limit=_positive_integer(
                collection.get("safe_author_limit"), "collection.safe_author_limit"
            ),
            bundle_version=_string(collection.get("bundle_version"), "collection.bundle_version"),
            openalex=OpenAlexSettings.from_mapping(openalex),
            raw=loaded,
        )
