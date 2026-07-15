"""Durable item/page orchestration for collection commands."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

from .io import atomic_write_json
from .openalex_client import Page, RateLimitExhausted
from .progress import (
    CHECKPOINT_VERSION,
    ProgressStore,
    canonical_json,
    complete_item,
    file_sha256,
    make_job_id,
    new_progress,
    pause_rate_limit,
    record_page,
    start_item,
    strip_secrets,
    utc_now,
)


class ResumeMismatchError(RuntimeError):
    """A saved job is incompatible with the requested resume operation."""


class CollectionPaused(SystemExit):
    """The process must stop after saving an exhausted-rate-limit checkpoint."""

    exit_code = 75

    def __init__(self, message: str, rate_limit: Mapping[str, Any]) -> None:
        super().__init__(self.exit_code)
        self.message = message
        self.rate_limit = dict(strip_secrets(rate_limit))


class PageClient(Protocol):
    def iter_pages(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        start_cursor: str = "*",
    ) -> Iterator[Page]: ...


RawPageReference = dict[str, str]
EndpointResolver = Callable[[Mapping[str, str]], tuple[str, Mapping[str, Any]]]


def _value_checksum(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_path_segment(value: str, label: str) -> str:
    if not value or value in {".", ".."}:
        raise ValueError(f"{label} must be non-empty")
    if re.fullmatch(r"[A-Za-z0-9._-]+", value):
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{label}-{digest}"


class RawPageStore:
    """Immutable raw response envelopes scoped to one collection job."""

    def __init__(
        self,
        root_dir: str | Path,
        *,
        stage: str,
        job_id: str,
        envelope_version: str,
        client_version: str,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.stage = stage
        self.job_id = job_id
        self.envelope_version = envelope_version
        self.client_version = client_version
        self._stage_segment = _safe_path_segment(stage, "stage")
        self._job_segment = _safe_path_segment(job_id, "job")

    def persist(self, page: Page, item_id: str) -> RawPageReference:
        """Persist a page envelope before returning its checkpoint reference."""
        item_segment = _safe_path_segment(item_id, "item")
        request_hash = _safe_path_segment(page.request_hash, "request")
        relative = Path(self._stage_segment) / self._job_segment / item_segment
        relative /= f"{request_hash}.json"
        destination = self.root_dir / relative
        response = {"results": page.results, "meta": page.meta}
        response_checksum = _value_checksum(response)
        envelope = {
            "envelope_version": self.envelope_version,
            "retrieved_at": utc_now(),
            "provider": "openalex",
            "job_id": self.job_id,
            "item_id": item_id,
            "request": strip_secrets(page.request),
            "http_status": 200,
            "request_hash": page.request_hash,
            "response_checksum": response_checksum,
            "cursor_in": page.cursor_in,
            "cursor_out": page.cursor_out,
            "client_version": self.client_version,
            "rate_limit": strip_secrets(page.rate_limit),
            "response": response,
        }

        try:
            atomic_write_json(destination, envelope)
        except FileExistsError:
            self._validate_existing(destination, envelope)

        return {
            "path": relative.as_posix(),
            "checksum": file_sha256(destination),
            "response_checksum": response_checksum,
            "request_hash": page.request_hash,
            "item_id": item_id,
        }

    @staticmethod
    def _validate_existing(destination: Path, expected: Mapping[str, Any]) -> None:
        try:
            existing = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError(f"existing raw page is unreadable: {destination}") from error
        if not isinstance(existing, dict):
            raise RuntimeError(f"existing raw page is not an envelope: {destination}")
        existing_response_checksum = _value_checksum(existing.get("response"))
        identity_fields = (
            "envelope_version",
            "provider",
            "job_id",
            "item_id",
            "request",
            "http_status",
            "request_hash",
            "response_checksum",
            "cursor_in",
            "cursor_out",
            "client_version",
            "response",
        )
        if existing_response_checksum != existing.get("response_checksum") or any(
            existing.get(field) != expected.get(field) for field in identity_fields
        ):
            raise RuntimeError(f"immutable raw page conflicts with response: {destination}")

    def verify(self, reference: Mapping[str, Any]) -> None:
        relative_value = reference.get("path")
        checksum = reference.get("checksum")
        if not isinstance(relative_value, str) or not isinstance(checksum, str):
            raise ResumeMismatchError("raw-page reference is incomplete")
        relative = Path(relative_value)
        if relative.is_absolute() or ".." in relative.parts:
            raise ResumeMismatchError("raw-page reference escapes the raw directory")
        destination = self.root_dir / relative
        expected_prefix = Path(self._stage_segment) / self._job_segment
        if relative.parts[:2] != expected_prefix.parts:
            raise ResumeMismatchError("raw-page reference belongs to another job")
        if not destination.is_file():
            raise ResumeMismatchError(f"referenced raw page is missing: {relative_value}")
        if file_sha256(destination) != checksum:
            raise ResumeMismatchError(f"raw-page checksum mismatch: {relative_value}")
        try:
            envelope = json.loads(destination.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResumeMismatchError(f"raw page is unreadable: {relative_value}") from error
        if not isinstance(envelope, dict) or "response" not in envelope:
            raise ResumeMismatchError(f"raw page envelope is malformed: {relative_value}")
        response_checksum = _value_checksum(envelope["response"])
        if (
            envelope.get("response_checksum") != response_checksum
            or reference.get("response_checksum") != response_checksum
        ):
            raise ResumeMismatchError(f"raw response checksum mismatch: {relative_value}")


class CollectionJob:
    """Checkpointed collection loop that advances only after raw persistence."""

    def __init__(
        self,
        *,
        client: PageClient,
        progress_store: ProgressStore,
        raw_page_store: RawPageStore,
        progress: dict[str, Any],
    ) -> None:
        self.client = client
        self.progress_store = progress_store
        self.raw_page_store = raw_page_store
        self.progress = progress

    @classmethod
    def create_or_resume(
        cls,
        *,
        client: PageClient,
        progress_store: ProgressStore,
        raw_page_store: RawPageStore,
        stage: str,
        setup: Mapping[str, Any],
        input_checksum: str,
        items: Sequence[Mapping[str, str]],
        original_command: str,
        output_path: str,
        resume: bool = False,
        job_id: str | None = None,
    ) -> CollectionJob:
        normalized_setup = strip_secrets(setup)
        calculated_job_id = make_job_id(stage, normalized_setup, input_checksum)
        resolved_job_id = job_id or calculated_job_id
        if raw_page_store.job_id != resolved_job_id or raw_page_store.stage != stage:
            raise ValueError("raw page store does not match the collection job")

        if resume:
            progress = cls._load_for_resume(progress_store, resolved_job_id)
            cls._validate_resume(
                progress,
                stage=stage,
                setup=normalized_setup,
                input_checksum=input_checksum,
                raw_page_store=raw_page_store,
            )
        else:
            if resolved_job_id != calculated_job_id:
                raise ValueError("new job ID does not match stage, setup, and input checksum")
            checkpoint_path = progress_store.path_for(resolved_job_id)
            if checkpoint_path.exists():
                raise FileExistsError(
                    f"checkpoint already exists; use resume: {checkpoint_path}"
                )
            progress = new_progress(
                job_id=resolved_job_id,
                stage=stage,
                setup=normalized_setup,
                input_checksum=input_checksum,
                items=items,
                original_command=original_command,
                output_path=output_path,
            )
            progress_store.save(progress)

        return cls(
            client=client,
            progress_store=progress_store,
            raw_page_store=raw_page_store,
            progress=progress,
        )

    @staticmethod
    def _load_for_resume(progress_store: ProgressStore, job_id: str) -> dict[str, Any]:
        checkpoint_path = progress_store.path_for(job_id)
        try:
            progress = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise ResumeMismatchError(f"checkpoint does not exist for job {job_id}") from error
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResumeMismatchError(f"checkpoint is unreadable for job {job_id}") from error
        if not isinstance(progress, dict):
            raise ResumeMismatchError("checkpoint is not a JSON object")
        return progress

    @staticmethod
    def _validate_resume(
        progress: Mapping[str, Any],
        *,
        stage: str,
        setup: Any,
        input_checksum: str,
        raw_page_store: RawPageStore,
    ) -> None:
        if progress.get("checkpoint_version") != CHECKPOINT_VERSION:
            raise ResumeMismatchError("checkpoint version does not match this runner")
        if progress.get("job_id") != raw_page_store.job_id or progress.get("stage") != stage:
            raise ResumeMismatchError("checkpoint job identity does not match")
        if canonical_json(progress.get("normalized_setup")) != canonical_json(setup):
            raise ResumeMismatchError("normalized setup does not match checkpoint")
        if progress.get("input_checksum") != input_checksum:
            raise ResumeMismatchError("input checksum does not match checkpoint")
        expected_job_id = make_job_id(stage, setup, input_checksum)
        if progress.get("job_id") != expected_job_id:
            raise ResumeMismatchError("checkpoint job ID does not match its inputs")
        raw_pages = progress.get("raw_pages", [])
        if not isinstance(raw_pages, list):
            raise ResumeMismatchError("raw-page references are malformed")
        for reference in raw_pages:
            if not isinstance(reference, Mapping):
                raise ResumeMismatchError("raw-page reference is malformed")
            raw_page_store.verify(reference)

    def collect_items(
        self,
        items: Sequence[Mapping[str, str]],
        endpoint_for_item: EndpointResolver,
    ) -> None:
        stored_items = self.progress.get("items")
        sanitized_items = [dict(strip_secrets(item)) for item in items]
        if stored_items != sanitized_items:
            raise ResumeMismatchError("collection items do not match checkpoint")

        completed = set(self.progress.get("completed_item_ids", []))
        for index, item in enumerate(sanitized_items):
            item_id = item.get("item_id")
            if item_id in completed:
                continue

            current = self.progress.get("current_item")
            if current is not None:
                if current != item or self.progress.get("current_item_index") != index:
                    raise ResumeMismatchError("active checkpoint item does not match input order")
                start_cursor = self.progress.get("current_cursor")
                if start_cursor is None:
                    complete_item(self.progress)
                    self.progress_store.save(self.progress)
                    completed.add(item_id)
                    continue
                start_item(self.progress, index, cursor=start_cursor)
                self.progress_store.save(self.progress)
            else:
                start_cursor = "*"
                start_item(self.progress, index, cursor=start_cursor)
                self.progress_store.save(self.progress)

            endpoint, params = endpoint_for_item(item)
            try:
                for page in self.client.iter_pages(endpoint, params, start_cursor=start_cursor):
                    reference = self.raw_page_store.persist(page, str(item_id))
                    record_page(
                        self.progress,
                        record_count=len(page.results),
                        next_cursor=page.cursor_out,
                        request_hash=page.request_hash,
                        rate_limit=page.rate_limit,
                        raw_page=reference,
                    )
                    self.progress_store.save(self.progress)
            except RateLimitExhausted as error:
                pause_rate_limit(self.progress, error.rate_limit, error=str(error))
                self.progress_store.save(self.progress)
                raise CollectionPaused(str(error), error.rate_limit) from None

            complete_item(self.progress)
            self.progress_store.save(self.progress)
            completed.add(item_id)
