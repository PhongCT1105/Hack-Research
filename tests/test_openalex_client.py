from __future__ import annotations

import json
import sys
import traceback
import urllib.request
from collections import deque
from http.client import IncompleteRead
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.lib.config import OpenAlexSettings  # noqa: E402
from scripts.lib.openalex_client import (  # noqa: E402
    AuthenticationError,
    HttpResponse,
    MalformedResponseError,
    OpenAlexClient,
    PermanentRequestError,
    RateLimitExhausted,
    TransportError,
    TransientOpenAlexError,
    UrllibTransport,
)


FIXTURES = Path(__file__).parent / "fixtures" / "openalex"
SECRET = "synthetic-secret-never-persist"


def settings(maximum_retries: int = 2) -> OpenAlexSettings:
    return OpenAlexSettings(
        base_url="https://api.openalex.invalid",
        api_key_environment_variable="OPENALEX_API_KEY",
        mailto_environment_variable="OPENALEX_MAILTO",
        user_agent="outreach-eval-tests/1.0",
        per_page=2,
        use_cursor_pagination=True,
        maximum_retries=maximum_retries,
        timeout_seconds=3,
    )


def fixture_response(name: str, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(
        status_code=200,
        headers=headers or {},
        body=(FIXTURES / name).read_bytes(),
    )


class QueueTransport:
    def __init__(self, *outcomes: HttpResponse | BaseException) -> None:
        self.outcomes = deque(outcomes)
        self.calls: list[dict[str, Any]] = []

    def request(
        self,
        base_url: str,
        endpoint: str,
        params: dict[str, Any],
        *,
        api_key: str,
        mailto: str | None,
        headers: dict[str, str],
        timeout: int,
    ) -> HttpResponse:
        self.calls.append(
            {
                "base_url": base_url,
                "endpoint": endpoint,
                "params": dict(params),
                "api_key": api_key,
                "mailto": mailto,
                "headers": dict(headers),
                "timeout": timeout,
            }
        )
        if not self.outcomes:
            raise AssertionError("unexpected transport request")
        outcome = self.outcomes.popleft()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def synthetic_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENALEX_API_KEY", SECRET)
    monkeypatch.setenv("OPENALEX_MAILTO", "collector@example.invalid")


@pytest.fixture
def fake_transport() -> QueueTransport:
    return QueueTransport(
        fixture_response(
            "institutions_page_1.json",
            {
                "X-RateLimit-Limit": "100000",
                "X-RateLimit-Remaining": "99998",
                "X-RateLimit-Credits-Used": "2",
            },
        ),
        fixture_response("institutions_page_2.json"),
    )


def test_cursor_pagination_uses_next_cursor_and_redacts_key(
    fake_transport: QueueTransport, tmp_path: Path
) -> None:
    client = OpenAlexClient(settings(), fake_transport, tmp_path)

    pages = list(client.iter_pages("institutions", {"filter": "country_code:CA"}))

    assert [page.cursor_in for page in pages] == ["*", "cursor-2"]
    assert [page.cursor_out for page in pages] == ["cursor-2", None]
    assert [len(page.results) for page in pages] == [2, 1]
    assert "secret" not in json.dumps([page.request for page in pages])
    assert all(call["api_key"] == SECRET for call in fake_transport.calls)
    assert all(call["headers"]["User-Agent"] == settings().user_agent for call in fake_transport.calls)
    assert [call["params"]["cursor"] for call in fake_transport.calls] == ["*", "cursor-2"]
    assert pages[0].rate_limit == {
        "credits_limit": 100000,
        "credits_remaining": 99998,
        "credits_used": 2,
    }


def test_successful_response_is_reused_from_redacted_cache(tmp_path: Path) -> None:
    transport = QueueTransport(fixture_response("institutions_page_2.json"))
    first = next(
        OpenAlexClient(settings(), transport, tmp_path).iter_pages(
            "institutions", {"filter": "country_code:CA"}, start_cursor="cursor-2"
        )
    )
    second = next(
        OpenAlexClient(settings(), transport, tmp_path).iter_pages(
            "institutions", {"filter": "country_code:CA"}, start_cursor="cursor-2"
        )
    )

    assert len(transport.calls) == 1
    assert first.request_hash == second.request_hash
    assert [first.cache_status, second.cache_status] == ["miss", "hit"]
    assert not first.cache_hit
    assert second.cache_hit
    cache_text = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.json"))
    assert SECRET not in cache_text


def test_request_hash_is_independent_of_parameter_order_and_secret_values(tmp_path: Path) -> None:
    first_transport = QueueTransport(fixture_response("institutions_page_2.json"))
    first = next(
        OpenAlexClient(settings(), first_transport, tmp_path).iter_pages(
            "institutions",
            {"filter": "country_code:CA", "select": "id,display_name", "api_key": "ignored-1"},
            start_cursor="cursor-2",
        )
    )
    second_transport = QueueTransport()
    second = next(
        OpenAlexClient(settings(), second_transport, tmp_path).iter_pages(
            "institutions",
            {"api_key": "ignored-2", "select": "id,display_name", "filter": "country_code:CA"},
            start_cursor="cursor-2",
        )
    )

    assert first.request_hash == second.request_hash
    assert second.cache_hit
    assert not second_transport.calls
    assert "ignored" not in json.dumps(first.request)


def test_sequence_parameters_are_canonicalized_for_cache_reuse(tmp_path: Path) -> None:
    transport = QueueTransport(fixture_response("institutions_page_2.json"))
    first = next(
        OpenAlexClient(settings(), transport, tmp_path).iter_pages(
            "institutions", {"select": ("id", "display_name")}, start_cursor="cursor-2"
        )
    )
    second = next(
        OpenAlexClient(settings(), transport, tmp_path).iter_pages(
            "institutions", {"select": ["id", "display_name"]}, start_cursor="cursor-2"
        )
    )

    assert first.request_hash == second.request_hash
    assert first.request["params"]["select"] == ["id", "display_name"]
    assert second.cache_hit
    assert len(transport.calls) == 1


def test_caller_mailto_is_excluded_from_request_and_cache_identity(tmp_path: Path) -> None:
    transport = QueueTransport(fixture_response("institutions_page_2.json"))
    first = next(
        OpenAlexClient(settings(), transport, tmp_path).iter_pages(
            "institutions", {"mailto": "first@example.invalid"}, start_cursor="cursor-2"
        )
    )
    second = next(
        OpenAlexClient(settings(), transport, tmp_path).iter_pages(
            "institutions", {"mailto": "second@example.invalid"}, start_cursor="cursor-2"
        )
    )

    assert first.request_hash == second.request_hash
    assert "mailto" not in first.request["params"]
    assert second.cache_hit
    cache_text = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.glob("*.json"))
    assert "first@example.invalid" not in cache_text
    assert "second@example.invalid" not in cache_text


def test_concurrent_cache_winner_replaces_losing_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.lib import openalex_client

    transport = QueueTransport(fixture_response("institutions_page_2.json"))

    def publish_winner(destination: Path, entry: dict[str, Any]) -> None:
        winner = json.loads(json.dumps(entry))
        winner["payload"]["results"][0]["id"] = "https://openalex.org/I_FAKE_WINNER"
        winner["rate_limit"] = {"credits_remaining": 777}
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(winner), encoding="utf-8")
        raise FileExistsError("synthetic cache race")

    monkeypatch.setattr(openalex_client, "atomic_write_json", publish_winner)

    page = next(
        OpenAlexClient(settings(), transport, tmp_path).iter_pages(
            "institutions", {}, start_cursor="cursor-2"
        )
    )

    assert page.results[0]["id"] == "https://openalex.org/I_FAKE_WINNER"
    assert page.rate_limit == {"credits_remaining": 777}
    assert page.cache_hit


def test_429_raises_rate_limit_with_reset(tmp_path: Path) -> None:
    transport = QueueTransport(
        HttpResponse(
            status_code=429,
            headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "18000"},
            body=b'{"error":"daily credits exhausted"}',
        )
    )

    with pytest.raises(RateLimitExhausted) as caught:
        next(OpenAlexClient(settings(), transport, tmp_path).iter_pages("authors", {}))

    assert caught.value.rate_limit == {"credits_remaining": 0, "resets_in_seconds": 18000}
    assert len(transport.calls) == 1
    assert SECRET not in str(caught.value)


def test_missing_api_key_is_an_authentication_error_before_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENALEX_API_KEY")
    transport = QueueTransport()

    with pytest.raises(AuthenticationError, match="OPENALEX_API_KEY"):
        next(OpenAlexClient(settings(), transport, tmp_path).iter_pages("authors", {}))

    assert not transport.calls


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [(401, AuthenticationError), (403, AuthenticationError), (400, PermanentRequestError), (404, PermanentRequestError)],
)
def test_nonretryable_statuses_are_classified_without_retry(
    tmp_path: Path, status_code: int, error_type: type[BaseException]
) -> None:
    transport = QueueTransport(HttpResponse(status_code, {}, b'{"error":"synthetic"}'))

    with pytest.raises(error_type):
        next(OpenAlexClient(settings(), transport, tmp_path).iter_pages("works", {}))

    assert len(transport.calls) == 1


def test_transient_status_retries_with_a_bound_and_can_recover(tmp_path: Path) -> None:
    transport = QueueTransport(
        HttpResponse(503, {}, b'{"error":"synthetic outage"}'),
        OSError("synthetic connection reset"),
        fixture_response("institutions_page_2.json"),
    )
    delays: list[float] = []

    page = next(
        OpenAlexClient(settings(maximum_retries=2), transport, tmp_path, sleep=delays.append).iter_pages(
            "institutions", {}, start_cursor="cursor-2"
        )
    )

    assert len(page.results) == 1
    assert len(transport.calls) == 3
    assert delays == [1.0, 2.0]


def test_transient_status_raises_after_retry_budget_is_exhausted(tmp_path: Path) -> None:
    transport = QueueTransport(
        HttpResponse(500, {}, b"first"),
        HttpResponse(502, {}, b"second"),
        HttpResponse(503, {}, b"third"),
    )

    with pytest.raises(TransientOpenAlexError):
        next(
            OpenAlexClient(settings(maximum_retries=2), transport, tmp_path, sleep=lambda _: None)
            .iter_pages("works", {})
        )

    assert len(transport.calls) == 3


def test_transport_failure_traceback_never_contains_secret_url(tmp_path: Path) -> None:
    failures = [
        RuntimeError(f"failed URL https://api.openalex.invalid/works?api_key={SECRET}"),
        RuntimeError(f"failed URL https://api.openalex.invalid/works?api_key={SECRET}"),
    ]
    transport = QueueTransport(*failures)

    with pytest.raises(TransientOpenAlexError) as caught:
        next(
            OpenAlexClient(settings(maximum_retries=1), transport, tmp_path, sleep=lambda _: None)
            .iter_pages("works", {})
        )

    rendered = "".join(traceback.format_exception(caught.value))
    assert SECRET not in rendered
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_urllib_transport_normalizes_incomplete_body_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenResponse:
        headers: dict[str, str] = {}

        def __enter__(self) -> BrokenResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def getcode(self) -> int:
            return 200

        def read(self) -> bytes:
            raise IncompleteRead(b"partial", 100)

    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: BrokenResponse())

    with pytest.raises(TransportError, match="transport request failed") as caught:
        UrllibTransport().request(
            "https://api.openalex.invalid",
            "works",
            {"cursor": "*", "per-page": 2},
            api_key=SECRET,
            mailto="collector@example.invalid",
            headers={"User-Agent": "outreach-eval-tests/1.0"},
            timeout=3,
        )

    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert SECRET not in "".join(traceback.format_exception(caught.value))


def test_urllib_transport_sanitizes_secret_bearing_construction_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_with_url(url: str, **kwargs: Any) -> None:
        raise OSError(f"could not construct request for {url}")

    monkeypatch.setattr(urllib.request, "Request", fail_with_url)

    with pytest.raises(TransportError) as caught:
        UrllibTransport().request(
            "https://api.openalex.invalid",
            "works",
            {"cursor": "*", "per-page": 2},
            api_key=SECRET,
            mailto=None,
            headers={"User-Agent": "outreach-eval-tests/1.0"},
            timeout=3,
        )

    assert caught.value.__context__ is None
    assert SECRET not in "".join(traceback.format_exception(caught.value))


def test_cursor_pagination_rejects_nonadjacent_cycles(tmp_path: Path) -> None:
    def response(cursor: str) -> HttpResponse:
        payload = {
            "meta": {"next_cursor": cursor},
            "results": [{"id": f"https://openalex.org/I_FAKE_{cursor}"}],
        }
        return HttpResponse(200, {}, json.dumps(payload).encode("utf-8"))

    transport = QueueTransport(response("B"), response("A"))
    pages = OpenAlexClient(settings(), transport, tmp_path).iter_pages(
        "institutions", {}, start_cursor="A"
    )

    assert next(pages).cursor_out == "B"
    assert next(pages).cursor_out == "A"
    with pytest.raises(MalformedResponseError, match="cursor cycle"):
        next(pages)
    assert len(transport.calls) == 2


@pytest.mark.parametrize(
    "body",
    [
        b"not-json",
        b"[]",
        b'{"meta": {}, "results": {}}',
        b'{"meta": [], "results": []}',
        b'{"meta": {"next_cursor": 42}, "results": []}',
    ],
)
def test_malformed_success_response_is_not_cached_or_retried(tmp_path: Path, body: bytes) -> None:
    transport = QueueTransport(HttpResponse(200, {}, body))

    with pytest.raises(MalformedResponseError):
        next(OpenAlexClient(settings(), transport, tmp_path).iter_pages("works", {}))

    assert len(transport.calls) == 1
    assert not list(tmp_path.glob("*.json"))
