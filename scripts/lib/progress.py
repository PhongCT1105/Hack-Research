"""Local, human-readable checkpoints for resumable collection commands."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence


__all__ = [
    "CHECKPOINT_VERSION",
    "RATE_LIMIT_KEYS",
    "SECRET_KEYS",
    "ProgressStore",
    "canonical_json",
    "complete_item",
    "file_sha256",
    "make_job_id",
    "new_progress",
    "parse_rate_limit_headers",
    "parse_rate_limit_payload",
    "pause_rate_limit",
    "record_page",
    "redact_command",
    "render_status",
    "start_item",
    "strip_secrets",
    "utc_now",
]


CHECKPOINT_VERSION = "collection-progress-v1"
SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "key",
    "password",
    "secret",
    "token",
}
RATE_LIMIT_KEYS = {
    "daily_budget_usd",
    "daily_used_usd",
    "daily_remaining_usd",
    "prepaid_balance_usd",
    "prepaid_remaining_usd",
    "prepaid_expires_at",
    "resets_at",
    "resets_in_seconds",
    "credits_limit",
    "credits_used",
    "credits_remaining",
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def strip_secrets(value: Any) -> Any:
    """Return a JSON-compatible copy with secret-bearing mapping keys removed."""
    if isinstance(value, Mapping):
        return {
            str(key): strip_secrets(item)
            for key, item in value.items()
            if str(key).lower() not in SECRET_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [strip_secrets(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(strip_secrets(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def make_job_id(stage: str, setup: Mapping[str, Any], input_checksum: str) -> str:
    payload = {"stage": stage, "setup": setup, "input_checksum": input_checksum}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_command(command: str) -> str:
    """Remove inline credentials before persisting a reproducible command."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    redacted: list[str] = []
    redact_next = False
    for token in tokens:
        if redact_next:
            redacted.append("[REDACTED]")
            redact_next = False
            continue

        flag, separator, _value = token.partition("=")
        normalized_flag = flag.lower().lstrip("-").replace("-", "_")
        if normalized_flag in SECRET_KEYS:
            if separator:
                redacted.append(f"{flag}=[REDACTED]")
            else:
                redacted.append(token)
                redact_next = True
            continue

        environment_name = flag.lower()
        if separator and environment_name in {
            "openalex_api_key",
            "semantic_scholar_api_key",
            "crossref_api_key",
            "unpaywall_api_key",
        }:
            redacted.append(f"{flag}=[REDACTED]")
            continue
        redacted.append(token)

    safe_command = shlex.join(redacted)
    return re.sub(
        r"(?i)([?&](?:api[_-]?key|token|secret)=)[^&\s]+",
        r"\1[REDACTED]",
        safe_command,
    )


def _resume_command(original_command: str) -> str:
    if "--resume" in original_command.split():
        return original_command
    return f"{original_command} --resume"


def new_progress(
    *,
    job_id: str,
    stage: str,
    setup: Mapping[str, Any],
    input_checksum: str,
    items: Sequence[Mapping[str, str]],
    original_command: str,
    output_path: str,
) -> dict[str, Any]:
    now = utc_now()
    sanitized_items = [dict(strip_secrets(item)) for item in items]
    safe_command = redact_command(original_command)
    return {
        "checkpoint_version": CHECKPOINT_VERSION,
        "job_id": job_id,
        "stage": stage,
        "status": "not_started",
        "original_command": safe_command,
        "resume_command": _resume_command(safe_command),
        "normalized_setup": strip_secrets(setup),
        "input_checksum": input_checksum,
        "output_path": output_path,
        "items": sanitized_items,
        "current_item_index": None,
        "total_items": len(sanitized_items),
        "completed_item_ids": [],
        "current_item": None,
        "current_cursor": None,
        "next_item": sanitized_items[0] if sanitized_items else None,
        "records_written": 0,
        "pages_written": 0,
        "raw_pages": [],
        "last_success_at": None,
        "last_request_hash": None,
        "rate_limit": {},
        "last_error": None,
        "created_at": now,
        "updated_at": now,
    }


class ProgressStore:
    """Atomic JSON persistence for independent collection jobs."""

    def __init__(self, state_dir: str | Path = "data/raw/progress") -> None:
        self.state_dir = Path(state_dir)

    def path_for(self, job_id: str) -> Path:
        if not job_id or any(character not in "0123456789abcdef" for character in job_id.lower()):
            raise ValueError("job_id must be a hexadecimal string")
        return self.state_dir / f"{job_id}.json"

    def save(self, progress: Mapping[str, Any]) -> Path:
        sanitized = strip_secrets(progress)
        job_id = str(sanitized.get("job_id", ""))
        destination = self.path_for(job_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(sanitized, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(destination)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return destination

    def load(self, job_id: str) -> dict[str, Any]:
        value = json.loads(self.path_for(job_id).read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"checkpoint is not a JSON object: {job_id}")
        if value.get("checkpoint_version") != CHECKPOINT_VERSION:
            raise ValueError(f"unsupported checkpoint version for job {job_id}")
        return value

    def list_job_ids(self) -> list[str]:
        if not self.state_dir.is_dir():
            return []
        return sorted(path.stem for path in self.state_dir.glob("*.json"))


def _item_after(progress: Mapping[str, Any], index: int) -> Mapping[str, str] | None:
    items = progress.get("items", [])
    next_index = index + 1
    return items[next_index] if next_index < len(items) else None


def start_item(progress: MutableMapping[str, Any], index: int, cursor: str | None = None) -> None:
    items = progress.get("items", [])
    if index < 0 or index >= len(items):
        raise IndexError(f"item index out of range: {index}")
    progress["status"] = "running"
    progress["current_item_index"] = index
    progress["current_item"] = items[index]
    progress["current_cursor"] = cursor
    progress["next_item"] = _item_after(progress, index)
    progress["updated_at"] = utc_now()


def record_page(
    progress: MutableMapping[str, Any],
    *,
    record_count: int,
    next_cursor: str | None,
    request_hash: str,
    rate_limit: Mapping[str, Any] | None = None,
    raw_page: Mapping[str, Any] | None = None,
) -> None:
    if not progress.get("current_item"):
        raise ValueError("cannot record a page without a current item")
    if record_count < 0:
        raise ValueError("record_count cannot be negative")
    progress["records_written"] = int(progress.get("records_written", 0)) + record_count
    progress["pages_written"] = int(progress.get("pages_written", 0)) + 1
    progress["current_cursor"] = next_cursor
    progress["last_request_hash"] = request_hash
    progress["last_success_at"] = utc_now()
    if raw_page is not None:
        progress.setdefault("raw_pages", []).append(dict(strip_secrets(raw_page)))
    if rate_limit is not None:
        progress["rate_limit"] = dict(strip_secrets(rate_limit))
    progress["updated_at"] = utc_now()


def complete_item(progress: MutableMapping[str, Any]) -> None:
    current = progress.get("current_item")
    index = progress.get("current_item_index")
    if not current or index is None:
        raise ValueError("cannot complete an item when none is active")
    item_id = current.get("item_id")
    completed = progress.setdefault("completed_item_ids", [])
    if item_id not in completed:
        completed.append(item_id)
    progress["current_item"] = None
    progress["current_cursor"] = None
    progress["next_item"] = _item_after(progress, int(index))
    progress["status"] = "completed" if len(completed) == progress.get("total_items") else "running"
    progress["updated_at"] = utc_now()


def pause_rate_limit(
    progress: MutableMapping[str, Any], rate_limit: Mapping[str, Any], error: str | None = None
) -> None:
    merged = dict(progress.get("rate_limit", {}))
    merged.update(strip_secrets(rate_limit))
    progress["rate_limit"] = merged
    progress["status"] = "paused_rate_limit"
    progress["last_error"] = error
    progress["updated_at"] = utc_now()


def _integer(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_rate_limit_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    lowered = {str(key).lower(): value for key, value in headers.items()}
    parsed = {
        "credits_limit": _integer(lowered.get("x-ratelimit-limit")),
        "credits_remaining": _integer(lowered.get("x-ratelimit-remaining")),
        "credits_used": _integer(lowered.get("x-ratelimit-credits-used")),
        "resets_in_seconds": _integer(lowered.get("x-ratelimit-reset")),
    }
    return {key: value for key, value in parsed.items() if value is not None}


def parse_rate_limit_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    raw = payload.get("rate_limit", {})
    if not isinstance(raw, Mapping):
        return {}
    return {key: raw[key] for key in RATE_LIMIT_KEYS if key in raw}


def render_status(progress: Mapping[str, Any]) -> str:
    lines = [
        f"Job ID: {progress.get('job_id', '')}",
        f"Stage: {progress.get('stage', '')}",
        f"Status: {progress.get('status', '')}",
        f"Original command: {progress.get('original_command', '')}",
        (
            "Completed items: "
            f"{len(progress.get('completed_item_ids', []))}/{progress.get('total_items', 0)}"
        ),
    ]
    current = progress.get("current_item")
    if current:
        kind = str(current.get("item_type", "item")).capitalize()
        lines.append(
            f"Current {kind.lower()}: {current.get('item_id', '')} "
            f"({current.get('provider_id', '')})"
        )
    else:
        lines.append("Current item: none")
    lines.append(f"Cursor saved: {'yes' if progress.get('current_cursor') else 'no'}")
    next_item = progress.get("next_item")
    if next_item:
        kind = str(next_item.get("item_type", "item")).capitalize()
        lines.append(
            f"Next {kind.lower()}: {next_item.get('item_id', '')} "
            f"({next_item.get('provider_id', '')})"
        )
    else:
        lines.append("Next item: none")
    lines.extend(
        [
            f"Records written: {progress.get('records_written', 0)}",
            f"Pages written: {progress.get('pages_written', 0)}",
            f"Last success: {progress.get('last_success_at') or 'none'}",
        ]
    )
    rate_limit = progress.get("rate_limit", {})
    lines.append(f"Credits remaining: {rate_limit.get('credits_remaining', 'unknown')}")
    lines.append(
        f"Provider reset: {rate_limit.get('resets_at') or rate_limit.get('resets_in_seconds') or 'unknown'}"
    )
    lines.append(f"Resume command: {progress.get('resume_command', '')}")
    return "\n".join(lines)
