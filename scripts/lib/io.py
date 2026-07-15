"""Atomic file operations and deterministic input checksums."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def _atomic_text_write(destination: Path, content: str, force: bool) -> None:
    if destination.exists() and not force:
        raise FileExistsError(f"refusing to overwrite existing output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_json(destination: str | Path, value: Any, force: bool = False) -> None:
    content = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _atomic_text_write(Path(destination), content, force)


def atomic_write_jsonl(
    destination: str | Path,
    records: Iterable[Mapping[str, Any]],
    force: bool = False,
) -> None:
    content = "".join(
        json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n" for record in records
    )
    _atomic_text_write(Path(destination), content, force)


def atomic_write_csv(
    destination: str | Path,
    records: Iterable[Mapping[str, Any]],
    fieldnames: Sequence[str] | None = None,
    force: bool = False,
) -> None:
    materialized = list(records)
    resolved_fieldnames = list(fieldnames or (materialized[0].keys() if materialized else ()))
    stream = io.StringIO(newline="")
    if resolved_fieldnames:
        writer = csv.DictWriter(stream, fieldnames=resolved_fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)
    _atomic_text_write(Path(destination), stream.getvalue(), force)


def read_jsonl(source: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        Path(source).read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL line {line_number} is not an object")
        records.append(value)
    return records


def read_csv(source: str | Path) -> list[dict[str, str]]:
    with Path(source).open(encoding="utf-8", newline="") as stream:
        return [dict(row) for row in csv.DictReader(stream)]


def input_checksum(source: str | Path | None) -> str:
    """Return a stable SHA-256 for an input file or directory tree."""

    if source is None:
        return "no-input"
    path = Path(source)
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    if path.is_dir():
        digest = hashlib.sha256()
        for child in sorted(item for item in path.rglob("*") if item.is_file()):
            relative = child.relative_to(path).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(bytes.fromhex(input_checksum(child)))
        return digest.hexdigest()
    raise FileNotFoundError(f"input not found: {path}")
