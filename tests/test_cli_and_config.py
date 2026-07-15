from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def run_script(name: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / name), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_author_limit_requires_full_run() -> None:
    from _dataset_cli import enforce_author_limit

    with pytest.raises(ValueError, match="--full-run"):
        enforce_author_limit(11, full_run=False)
    assert enforce_author_limit(11, full_run=True) == 11


def test_author_limit_defaults_to_safe_limit_and_rejects_nonpositive_values() -> None:
    from _dataset_cli import enforce_author_limit

    assert enforce_author_limit(None, full_run=False) == 10
    with pytest.raises(ValueError, match="at least 1"):
        enforce_author_limit(0, full_run=False)


def test_dry_run_exposes_new_operational_flags() -> None:
    result = run_script("02_fetch_author_candidates.py", "--dry-run", "--limit", "10")
    assert result.returncode == 0, result.stderr
    plan = json.loads(result.stdout)
    assert plan["limit"] == 10
    assert plan["full_run"] is False


def test_dry_run_rejects_unsafe_author_limit_without_full_run() -> None:
    result = run_script("02_fetch_author_candidates.py", "--dry-run", "--limit", "11")
    assert result.returncode == 2
    assert "--full-run" in result.stderr


def test_dataset_config_loads_typed_operational_settings() -> None:
    from lib.config import DatasetConfig

    config = DatasetConfig.load(ROOT / "config" / "dataset.yaml")

    assert config.dataset_version == "benchmark-v1"
    assert config.safe_author_limit == 10
    assert config.recent_activity_year >= 2000
    assert config.institution_seed_countries
    assert config.institution_seed_types
    assert config.raw_envelope_version
    assert config.bundle_version
    assert config.openalex.api_key_environment_variable == "OPENALEX_API_KEY"
    assert config.openalex.mailto_environment_variable == "OPENALEX_MAILTO"
    assert config.openalex.user_agent


def test_atomic_io_round_trips_and_refuses_overwrite(tmp_path: Path) -> None:
    from lib.io import (
        atomic_write_csv,
        atomic_write_json,
        atomic_write_jsonl,
        read_csv,
        read_jsonl,
    )

    json_path = tmp_path / "nested" / "record.json"
    jsonl_path = tmp_path / "records.jsonl"
    csv_path = tmp_path / "records.csv"
    records = [{"id": "FAKE-01", "score": 1}, {"id": "FAKE-02", "score": 2}]

    atomic_write_json(json_path, {"version": 1})
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"version": 1}
    with pytest.raises(FileExistsError):
        atomic_write_json(json_path, {"version": 2})

    atomic_write_jsonl(jsonl_path, records)
    assert read_jsonl(jsonl_path) == records

    atomic_write_csv(csv_path, records, fieldnames=("id", "score"))
    assert read_csv(csv_path) == [
        {"id": "FAKE-01", "score": "1"},
        {"id": "FAKE-02", "score": "2"},
    ]


def test_input_checksum_changes_with_file_content(tmp_path: Path) -> None:
    from lib.io import input_checksum

    source = tmp_path / "input.jsonl"
    source.write_text('{"id":"FAKE-01"}\n', encoding="utf-8")
    first = input_checksum(source)
    source.write_text('{"id":"FAKE-02"}\n', encoding="utf-8")

    assert len(first) == 64
    assert input_checksum(source) != first
