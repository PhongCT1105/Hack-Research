from __future__ import annotations

import json
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.openalex_client import Page, RateLimitExhausted  # noqa: E402
from lib.progress import ProgressStore, file_sha256, make_job_id  # noqa: E402
from lib.runner import (  # noqa: E402
    CollectionJob,
    CollectionPaused,
    RawPageStore,
    ResumeMismatchError,
)


ITEM = {
    "item_type": "professor",
    "item_id": "MOCK-01",
    "provider_id": "A100000001",
}
SETUP = {"endpoint": "works", "filter": "author.id:A100000001"}


def page(cursor_in: str, cursor_out: str | None, request_hash: str) -> Page:
    return Page(
        results=[{"id": f"W-{request_hash}"}],
        meta={"next_cursor": cursor_out},
        cursor_in=cursor_in,
        cursor_out=cursor_out,
        request={
            "provider": "openalex",
            "endpoint": "works",
            "params": {"cursor": cursor_in},
        },
        request_hash=request_hash,
        rate_limit={"credits_remaining": 99},
        cache_status="miss",
    )


class StaticClient:
    def __init__(self, pages: list[Page]) -> None:
        self.pages = pages
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def iter_pages(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        start_cursor: str = "*",
    ) -> Iterator[Page]:
        self.calls.append((endpoint, dict(params), start_cursor))
        yield from self.pages


class PageThenRateLimitClient(StaticClient):
    def iter_pages(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        start_cursor: str = "*",
    ) -> Iterator[Page]:
        self.calls.append((endpoint, dict(params), start_cursor))
        yield from self.pages
        raise RateLimitExhausted(
            "credits exhausted",
            rate_limit={"credits_remaining": 0, "resets_in_seconds": 60},
        )


def endpoint_for_author(item: Mapping[str, str]) -> tuple[str, dict[str, str]]:
    return "works", {"filter": f"author.id:{item['provider_id']}"}


def stores(tmp_path: Path, input_checksum: str = "input-checksum") -> tuple[
    str, ProgressStore, RawPageStore
]:
    job_id = make_job_id("04_fetch_author_works", SETUP, input_checksum)
    return (
        job_id,
        ProgressStore(tmp_path / "progress"),
        RawPageStore(
            tmp_path / "raw",
            stage="04_fetch_author_works",
            job_id=job_id,
            envelope_version="raw-page-v1",
            client_version="test-client-v1",
        ),
    )


def create_job(
    tmp_path: Path,
    client: StaticClient,
    *,
    input_checksum: str = "input-checksum",
    setup: Mapping[str, Any] = SETUP,
    resume: bool = False,
    job_id: str | None = None,
) -> CollectionJob:
    calculated_job_id, progress_store, raw_store = stores(tmp_path, input_checksum)
    if job_id is not None and job_id != calculated_job_id:
        raw_store = RawPageStore(
            tmp_path / "raw",
            stage="04_fetch_author_works",
            job_id=job_id,
            envelope_version="raw-page-v1",
            client_version="test-client-v1",
        )
    return CollectionJob.create_or_resume(
        client=client,
        progress_store=progress_store,
        raw_page_store=raw_store,
        stage="04_fetch_author_works",
        setup=setup,
        input_checksum=input_checksum,
        items=[ITEM],
        original_command="python scripts/04_fetch_author_works.py",
        output_path="data/interim/works.jsonl",
        resume=resume,
        job_id=job_id or calculated_job_id,
    )


def load_only_checkpoint(tmp_path: Path) -> dict[str, Any]:
    paths = list((tmp_path / "progress").glob("*.json"))
    assert len(paths) == 1
    return json.loads(paths[0].read_text(encoding="utf-8"))


def test_raw_page_is_persisted_before_cursor_advances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = StaticClient([page("*", "cursor-2", "hash-1"), page("cursor-2", None, "hash-2")])
    job = create_job(tmp_path, client)

    from lib import runner

    original_record_page = runner.record_page

    def assert_raw_exists_before_record(*args: Any, **kwargs: Any) -> None:
        expected_hash = kwargs["request_hash"]
        assert list((tmp_path / "raw").rglob(f"{expected_hash}.json"))
        original_record_page(*args, **kwargs)

    monkeypatch.setattr(runner, "record_page", assert_raw_exists_before_record)
    job.collect_items([ITEM], endpoint_for_author)

    checkpoint = load_only_checkpoint(tmp_path)
    raw_paths = list((tmp_path / "raw").rglob("*.json"))
    assert len(raw_paths) == 2
    assert checkpoint["current_cursor"] is None
    assert checkpoint["completed_item_ids"] == ["MOCK-01"]
    assert checkpoint["pages_written"] == 2
    assert len(checkpoint["raw_pages"]) == 2
    assert all(file_sha256(path) in {ref["checksum"] for ref in checkpoint["raw_pages"]} for path in raw_paths)


def test_resume_rejects_changed_input_checksum(tmp_path: Path) -> None:
    original = create_job(tmp_path, StaticClient([]), input_checksum="first")

    with pytest.raises(ResumeMismatchError, match="input checksum"):
        create_job(
            tmp_path,
            StaticClient([]),
            input_checksum="second",
            resume=True,
            job_id=original.progress["job_id"],
        )


def test_resume_rejects_changed_normalized_setup(tmp_path: Path) -> None:
    original = create_job(tmp_path, StaticClient([]))

    with pytest.raises(ResumeMismatchError, match="normalized setup"):
        create_job(
            tmp_path,
            StaticClient([]),
            setup={**SETUP, "filter": "author.id:A100000002"},
            resume=True,
            job_id=original.progress["job_id"],
        )


def test_resume_rejects_changed_checkpoint_version(tmp_path: Path) -> None:
    job = create_job(tmp_path, StaticClient([]))
    checkpoint_path = job.progress_store.path_for(job.progress["job_id"])
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    checkpoint["checkpoint_version"] = "future-version"
    checkpoint_path.write_text(json.dumps(checkpoint), encoding="utf-8")

    with pytest.raises(ResumeMismatchError, match="checkpoint version"):
        create_job(
            tmp_path,
            StaticClient([]),
            resume=True,
            job_id=job.progress["job_id"],
        )


def test_resume_rejects_corrupted_referenced_raw_page(tmp_path: Path) -> None:
    first_client = PageThenRateLimitClient([page("*", "cursor-2", "hash-1")])
    job = create_job(tmp_path, first_client)
    with pytest.raises(CollectionPaused):
        job.collect_items([ITEM], endpoint_for_author)
    raw_path = next((tmp_path / "raw").rglob("*.json"))
    raw_path.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ResumeMismatchError, match="raw-page checksum"):
        create_job(
            tmp_path,
            StaticClient([]),
            resume=True,
            job_id=job.progress["job_id"],
        )


def test_rate_limit_pause_is_saved_and_raises_exit_75(tmp_path: Path) -> None:
    job = create_job(tmp_path, PageThenRateLimitClient([]))

    with pytest.raises(CollectionPaused) as caught:
        job.collect_items([ITEM], endpoint_for_author)

    checkpoint = load_only_checkpoint(tmp_path)
    assert caught.value.code == 75
    assert caught.value.exit_code == 75
    assert checkpoint["status"] == "paused_rate_limit"
    assert checkpoint["rate_limit"] == {"credits_remaining": 0, "resets_in_seconds": 60}
    assert checkpoint["current_cursor"] == "*"


def test_resume_continues_at_exact_saved_cursor(tmp_path: Path) -> None:
    first_client = PageThenRateLimitClient([page("*", "cursor-2", "hash-1")])
    first_job = create_job(tmp_path, first_client)
    with pytest.raises(CollectionPaused):
        first_job.collect_items([ITEM], endpoint_for_author)

    second_client = StaticClient([page("cursor-2", None, "hash-2")])
    resumed = create_job(
        tmp_path,
        second_client,
        resume=True,
        job_id=first_job.progress["job_id"],
    )
    resumed.collect_items([ITEM], endpoint_for_author)

    assert second_client.calls[0][2] == "cursor-2"
    checkpoint = load_only_checkpoint(tmp_path)
    assert checkpoint["completed_item_ids"] == ["MOCK-01"]
    assert checkpoint["records_written"] == 2
    assert checkpoint["pages_written"] == 2


def test_raw_page_envelope_is_redacted_and_immutable(tmp_path: Path) -> None:
    job_id, _progress_store, raw_store = stores(tmp_path)
    unsafe_page = page("*", None, "hash-1")
    unsafe_page.request["params"]["api_key"] = "secret"
    unsafe_page.results[0]["key"] = "legitimate-response-value"

    reference = raw_store.persist(unsafe_page, "MOCK-01")
    envelope_path = tmp_path / "raw" / reference["path"]
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))

    assert envelope["job_id"] == job_id
    assert envelope["response"] == {"results": unsafe_page.results, "meta": unsafe_page.meta}
    assert envelope["response_checksum"]
    assert "secret" not in envelope_path.read_text(encoding="utf-8")
    assert raw_store.persist(unsafe_page, "MOCK-01") == reference
