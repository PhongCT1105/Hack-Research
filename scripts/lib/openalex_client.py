"""Injected OpenAlex transport with cursor pagination and redacted response caching."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol, runtime_checkable

from .config import OpenAlexSettings
from .io import atomic_write_json


PRIVATE_PARAMETER_NAMES = frozenset(
    {"api_key", "apikey", "key", "token", "access_token", "mailto"}
)


@dataclass(frozen=True)
class HttpResponse:
    """Transport-neutral HTTP response."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes


class TransportError(RuntimeError):
    """A sanitized transport failure that is safe to report or retry."""


@runtime_checkable
class Transport(Protocol):
    """Minimal injectable HTTP transport used by :class:`OpenAlexClient`."""

    def request(
        self,
        base_url: str,
        endpoint: str,
        params: Mapping[str, Any],
        *,
        api_key: str,
        mailto: str | None,
        headers: dict[str, str],
        timeout: int,
    ) -> HttpResponse: ...


class UrllibTransport:
    """Production transport implemented only with the Python standard library."""

    def request(
        self,
        base_url: str,
        endpoint: str,
        params: Mapping[str, Any],
        *,
        api_key: str,
        mailto: str | None,
        headers: dict[str, str],
        timeout: int,
    ) -> HttpResponse:
        import urllib.error
        import urllib.parse
        import urllib.request

        try:
            query = dict(params)
            if mailto:
                query["mailto"] = mailto
            query["api_key"] = api_key
            query_string = urllib.parse.urlencode(sorted(query.items()), doseq=True)
            url = f"{base_url.rstrip('/')}/{endpoint}?{query_string}"
            request = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    status_code = response.getcode()
                    response_headers = dict(response.headers.items())
                    body = response.read()
            except urllib.error.HTTPError as error:
                status_code = error.code
                response_headers = (
                    dict(error.headers.items()) if error.headers is not None else {}
                )
                body = error.read()
        except Exception:
            # Nothing raised below may retain the credential-bearing URL in its
            # cause or context, regardless of which urllib phase failed.
            pass
        else:
            return HttpResponse(
                status_code=status_code,
                headers=response_headers,
                body=body,
            )
        raise TransportError("OpenAlex transport request failed") from None


class OpenAlexError(RuntimeError):
    """Base class for classified OpenAlex request failures."""

    def __init__(
        self,
        message: str,
        *,
        request: Mapping[str, Any] | None = None,
        status_code: int | None = None,
        rate_limit: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.request = dict(request or {})
        self.status_code = status_code
        self.rate_limit = dict(rate_limit or {})


class AuthenticationError(OpenAlexError):
    """Missing, rejected, or unauthorized OpenAlex credentials."""


class PermanentRequestError(OpenAlexError):
    """A request OpenAlex rejected permanently."""


class MalformedResponseError(OpenAlexError):
    """A successful response or cache entry had an incompatible shape."""


class RateLimitExhausted(OpenAlexError):
    """OpenAlex rejected a request because its credit allowance was exhausted."""


class TransientOpenAlexError(OpenAlexError):
    """A retryable transport or server failure exhausted the retry budget."""


@dataclass(frozen=True)
class Page:
    """One validated OpenAlex result page and its redacted provenance."""

    results: list[dict[str, Any]]
    meta: dict[str, Any]
    cursor_in: str
    cursor_out: str | None
    request: dict[str, Any]
    request_hash: str
    rate_limit: dict[str, Any]
    cache_status: str

    @property
    def cache_hit(self) -> bool:
        return self.cache_status == "hit"


class OpenAlexClient:
    """Cursor-paginated OpenAlex client with an injected transport."""

    def __init__(
        self,
        settings: OpenAlexSettings,
        transport: Transport,
        cache_dir: str | Path,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings
        self.transport = transport
        self.cache_dir = Path(cache_dir)
        self._sleep = sleep

    def iter_pages(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        start_cursor: str = "*",
    ) -> Iterator[Page]:
        """Yield validated pages until OpenAlex returns no next cursor."""

        normalized_endpoint = endpoint.strip("/")
        if not normalized_endpoint or "/" in normalized_endpoint:
            raise ValueError("OpenAlex endpoint must be one non-empty path segment")
        if not isinstance(start_cursor, str) or not start_cursor:
            raise ValueError("start_cursor must be a non-empty string")

        cursor = start_cursor
        visited_cursors: set[str] = set()
        while True:
            request = self._canonical_request(normalized_endpoint, params, cursor)
            if cursor in visited_cursors:
                raise MalformedResponseError(
                    "OpenAlex response contains a cursor cycle",
                    request=request,
                )
            visited_cursors.add(cursor)
            request_hash = self._request_hash(request)
            payload, rate_limit, cache_status = self._load_or_fetch(request, request_hash)
            results, meta, next_cursor = self._validate_payload(payload, request)
            yield Page(
                results=results,
                meta=meta,
                cursor_in=cursor,
                cursor_out=next_cursor,
                request=request,
                request_hash=request_hash,
                rate_limit=rate_limit,
                cache_status=cache_status,
            )
            if next_cursor is None:
                return
            cursor = next_cursor

    def _canonical_request(
        self, endpoint: str, params: Mapping[str, Any], cursor: str
    ) -> dict[str, Any]:
        redacted_params: dict[str, Any] = {}
        for key, value in params.items():
            if not isinstance(key, str):
                raise ValueError("OpenAlex request parameter names must be strings")
            if key.lower() in PRIVATE_PARAMETER_NAMES:
                continue
            redacted_params[key] = _canonical_parameter_value(value)
        redacted_params["cursor"] = cursor
        redacted_params["per-page"] = self.settings.per_page
        return {
            "provider": "openalex",
            "endpoint": endpoint,
            "params": {key: redacted_params[key] for key in sorted(redacted_params)},
        }

    @staticmethod
    def _request_hash(request: Mapping[str, Any]) -> str:
        try:
            encoded = json.dumps(
                request,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ValueError("OpenAlex request parameters must be JSON serializable") from error
        return hashlib.sha256(encoded).hexdigest()

    def _load_or_fetch(
        self, request: dict[str, Any], request_hash: str
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        cache_path = self.cache_dir / f"{request_hash}.json"
        if cache_path.is_file():
            payload, rate_limit = self._read_cache(cache_path, request)
            return payload, rate_limit, "hit"

        payload, rate_limit = self._fetch(request)
        self._validate_payload(payload, request)
        cache_entry = {
            "version": 1,
            "request": request,
            "payload": payload,
            "rate_limit": rate_limit,
        }
        try:
            atomic_write_json(cache_path, cache_entry)
        except FileExistsError:
            # Another process populated the same immutable cache entry first; its
            # immutable value wins over the response fetched by this process.
            cached_payload, cached_rate_limit = self._read_cache(cache_path, request)
            return cached_payload, cached_rate_limit, "hit"
        return payload, rate_limit, "miss"

    def _read_cache(
        self, cache_path: Path, request: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            entry = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MalformedResponseError(
                "cached OpenAlex response is not valid JSON",
                request=request,
            ) from error
        if not isinstance(entry, dict) or entry.get("request") != request:
            raise MalformedResponseError(
                "cached OpenAlex response does not match its request",
                request=request,
            )
        payload = entry.get("payload")
        rate_limit = entry.get("rate_limit", {})
        if not isinstance(payload, dict) or not isinstance(rate_limit, dict):
            raise MalformedResponseError(
                "cached OpenAlex response has an incompatible shape",
                request=request,
            )
        self._validate_payload(payload, request)
        return payload, dict(rate_limit)

    def _fetch(
        self, request: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        api_key = os.environ.get(self.settings.api_key_environment_variable)
        if not api_key:
            raise AuthenticationError(
                f"OpenAlex API key environment variable "
                f"{self.settings.api_key_environment_variable!r} is not set",
                request=request,
            )

        for attempt in range(self.settings.maximum_retries + 1):
            transport_failed = False
            try:
                response = self.transport.request(
                    self.settings.base_url,
                    str(request["endpoint"]),
                    dict(request["params"]),
                    api_key=api_key,
                    mailto=os.environ.get(self.settings.mailto_environment_variable),
                    headers={"Accept": "application/json", "User-Agent": self.settings.user_agent},
                    timeout=self.settings.timeout_seconds,
                )
            except Exception:
                # The transport is the only component that receives credentials.
                # Normalize every implementation failure before it can escape.
                transport_failed = True

            if transport_failed:
                if attempt < self.settings.maximum_retries:
                    self._backoff(attempt)
                    continue
                raise TransientOpenAlexError(
                    "OpenAlex transport failed after retry budget was exhausted",
                    request=request,
                ) from None

            rate_limit = _parse_rate_limit_headers(response.headers)
            if 200 <= response.status_code < 300:
                return self._decode_json(response.body, request), rate_limit
            if response.status_code in {401, 403}:
                raise AuthenticationError(
                    f"OpenAlex authentication failed with HTTP {response.status_code}",
                    request=request,
                    status_code=response.status_code,
                    rate_limit=rate_limit,
                )
            if response.status_code == 429:
                raise RateLimitExhausted(
                    "OpenAlex rate limit exhausted with HTTP 429",
                    request=request,
                    status_code=response.status_code,
                    rate_limit=rate_limit,
                )
            if 500 <= response.status_code < 600:
                if attempt < self.settings.maximum_retries:
                    self._backoff(attempt)
                    continue
                raise TransientOpenAlexError(
                    f"OpenAlex server failed with HTTP {response.status_code} "
                    "after retry budget was exhausted",
                    request=request,
                    status_code=response.status_code,
                    rate_limit=rate_limit,
                )
            raise PermanentRequestError(
                f"OpenAlex request failed with HTTP {response.status_code}",
                request=request,
                status_code=response.status_code,
                rate_limit=rate_limit,
            )

        raise AssertionError("unreachable OpenAlex retry state")

    @staticmethod
    def _decode_json(body: bytes, request: Mapping[str, Any]) -> dict[str, Any]:
        try:
            payload = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise MalformedResponseError(
                "OpenAlex returned malformed JSON",
                request=request,
            ) from error
        if not isinstance(payload, dict):
            raise MalformedResponseError(
                "OpenAlex response must be a JSON object",
                request=request,
            )
        return payload

    @staticmethod
    def _validate_payload(
        payload: Mapping[str, Any], request: Mapping[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any], str | None]:
        results = payload.get("results")
        meta = payload.get("meta")
        if not isinstance(results, list) or not all(isinstance(result, dict) for result in results):
            raise MalformedResponseError(
                "OpenAlex response 'results' must be a list of objects",
                request=request,
            )
        if not isinstance(meta, dict):
            raise MalformedResponseError(
                "OpenAlex response 'meta' must be an object",
                request=request,
            )
        next_cursor = meta.get("next_cursor")
        if next_cursor is not None and (not isinstance(next_cursor, str) or not next_cursor):
            raise MalformedResponseError(
                "OpenAlex response 'meta.next_cursor' must be a non-empty string or null",
                request=request,
            )
        return [dict(result) for result in results], dict(meta), next_cursor

    def _backoff(self, attempt: int) -> None:
        self._sleep(float(min(2**attempt, 60)))


def _parse_rate_limit_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    lowered = {str(key).lower(): value for key, value in headers.items()}
    fields = {
        "credits_limit": "x-ratelimit-limit",
        "credits_remaining": "x-ratelimit-remaining",
        "credits_used": "x-ratelimit-credits-used",
        "resets_in_seconds": "x-ratelimit-reset",
    }
    parsed: dict[str, Any] = {}
    for name, header in fields.items():
        value = lowered.get(header)
        if value is None or value == "":
            continue
        try:
            parsed[name] = int(value)
        except (TypeError, ValueError):
            continue
    return parsed


def _canonical_parameter_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return [_canonical_parameter_value(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and isfinite(value):
        return value
    raise ValueError(
        "OpenAlex request parameter values must be JSON scalar values or sequences of scalars"
    )
