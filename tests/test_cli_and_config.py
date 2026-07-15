from __future__ import annotations

import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
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


def write_atomic_format(destination: Path, format_name: str, marker: str) -> None:
    from lib.io import atomic_write_csv, atomic_write_json, atomic_write_jsonl

    record = {"id": marker}
    if format_name == "json":
        atomic_write_json(destination, record)
    elif format_name == "jsonl":
        atomic_write_jsonl(destination, [record])
    else:
        atomic_write_csv(destination, [record], fieldnames=("id",))


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


@pytest.mark.parametrize("format_name", ["json", "jsonl", "csv"])
def test_atomic_writers_refuse_existing_destination(tmp_path: Path, format_name: str) -> None:
    destination = tmp_path / f"records.{format_name}"
    destination.write_text("sentinel\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_atomic_format(destination, format_name, "FAKE-NEW")

    assert destination.read_text(encoding="utf-8") == "sentinel\n"


@pytest.mark.parametrize("format_name", ["json", "jsonl", "csv"])
def test_atomic_writers_allow_only_one_concurrent_no_clobber_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, format_name: str
) -> None:
    destination = tmp_path / f"concurrent.{format_name}"
    start_barrier = threading.Barrier(2)
    exists_barrier = threading.Barrier(2)
    original_exists = Path.exists

    def synchronized_exists(path: Path) -> bool:
        if path == destination:
            exists_barrier.wait(timeout=5)
            return False
        return original_exists(path)

    def attempt(marker: str) -> BaseException | None:
        start_barrier.wait(timeout=5)
        try:
            write_atomic_format(destination, format_name, marker)
        except BaseException as error:
            return error
        return None

    with monkeypatch.context() as patch:
        patch.setattr(Path, "exists", synchronized_exists)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, ["FAKE-ONE", "FAKE-TWO"]))

    assert sum(result is None for result in results) == 1
    assert sum(isinstance(result, FileExistsError) for result in results) == 1
    assert all(result is None or isinstance(result, FileExistsError) for result in results)
    published = destination.read_text(encoding="utf-8")
    assert ("FAKE-ONE" in published) != ("FAKE-TWO" in published)


def test_directory_input_checksum_is_creation_order_independent(tmp_path: Path) -> None:
    from lib.io import input_checksum

    files = {
        "alpha.json": '{"id":"FAKE-01"}\n',
        "nested/beta.csv": "id\nFAKE-02\n",
        "nested/deeper/gamma.jsonl": '{"id":"FAKE-03"}\n',
    }
    first = tmp_path / "first"
    second = tmp_path / "second"
    for relative, content in files.items():
        destination = first / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    for relative, content in reversed(files.items()):
        destination = second / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")

    first_checksum = input_checksum(first)
    assert len(first_checksum) == 64
    assert input_checksum(second) == first_checksum

    (second / "nested" / "beta.csv").write_text("id\nFAKE-CHANGED\n", encoding="utf-8")
    assert input_checksum(second) != first_checksum
