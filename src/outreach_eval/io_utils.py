"""JSONL and run-manifest I/O.

Provenance rule (CLAUDE.md): every generation run gets a manifest row; outputs are
append-only and never hand-edited.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from .schemas import EmailRecord

MANIFEST_FIELDS = [
    "run_id",
    "professor_id",
    "condition",
    "seed",
    "writer_provider",
    "writer_model",
    "verifier_provider",
    "verifier_model",
    "prompt_version",
    "temperature",
    "timestamp",
]


def append_jsonl(path: Path, record: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def read_jsonl(path: Path) -> list[EmailRecord]:
    with path.open(encoding="utf-8") as f:
        return [EmailRecord.model_validate_json(line) for line in f if line.strip()]


def append_manifest_row(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
