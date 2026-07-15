from __future__ import annotations

import csv
import hashlib
import importlib
import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterator, Mapping

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURES = Path(__file__).parent / "fixtures" / "openalex"
sys.path.insert(0, str(SCRIPTS))

from lib.config import DatasetConfig  # noqa: E402
from lib.openalex_client import Page  # noqa: E402
from lib.progress import ProgressStore, new_progress  # noqa: E402


stage_01 = importlib.import_module("01_fetch_institutions")


def config() -> DatasetConfig:
    loaded = DatasetConfig.load(ROOT / "config" / "dataset.yaml")
    return replace(
        loaded,
        institution_seed_countries=("CA", "DE", "GB"),
        institution_seed_types=("education",),
    )


def write_config(tmp_path: Path, **paths: str) -> Path:
    raw_config = deepcopy(config().raw)
    raw_config["paths"].update(paths)
    destination = tmp_path / "dataset.yaml"
    destination.write_text(yaml.safe_dump(raw_config), encoding="utf-8")
    return destination


def fixture_institution(
    fixture_index: int,
    *,
    openalex_id: str,
    country: str,
    region: str,
) -> dict[str, Any]:
    payload = json.loads((FIXTURES / "institutions_page_1.json").read_text(encoding="utf-8"))
    institution = deepcopy(payload["results"][fixture_index])
    institution.update(
        {
            "id": f"https://openalex.org/{openalex_id}",
            "country_code": country,
            "geo": {"region": region},
            "type": "education",
            "works_count": fixture_index + 10,
            "cited_by_count": fixture_index + 20,
            "homepage_url": None,
            "ror": None,
            "lineage": [f"https://openalex.org/{openalex_id}"],
        }
    )
    return institution


class FixtureClient:
    def __init__(self) -> None:
        first = fixture_institution(
            0,
            openalex_id="I100000001",
            country="CA",
            region="North America",
        )
        second = fixture_institution(
            1,
            openalex_id="I100000002",
            country="DE",
            region="Europe",
        )
        self.pages_by_filter = {
            "country_code:CA,type:education": [[first], []],
            "country_code:DE,type:education": [[second]],
            "country_code:GB,type:education": [[deepcopy(first)]],
        }
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def iter_pages(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        start_cursor: str = "*",
    ) -> Iterator[Page]:
        copied_params = dict(params)
        self.calls.append((endpoint, copied_params, start_cursor))
        filter_value = str(copied_params["filter"])
        start_index = 0 if start_cursor == "*" else int(start_cursor.removeprefix("cursor-")) - 1
        pages = self.pages_by_filter[filter_value]
        for page_index in range(start_index, len(pages)):
            cursor_in = "*" if page_index == 0 else f"cursor-{page_index + 1}"
            cursor_out = f"cursor-{page_index + 2}" if page_index + 1 < len(pages) else None
            request_hash = hashlib.sha256(f"{filter_value}|{cursor_in}".encode("utf-8")).hexdigest()
            yield Page(
                results=deepcopy(pages[page_index]),
                meta={"next_cursor": cursor_out},
                cursor_in=cursor_in,
                cursor_out=cursor_out,
                request={
                    "provider": "openalex",
                    "endpoint": endpoint,
                    "params": {"cursor": cursor_in, **copied_params},
                },
                request_hash=request_hash,
                rate_limit={"credits_remaining": 99},
                cache_status="fixture",
            )


@pytest.fixture
def fake_client() -> FixtureClient:
    return FixtureClient()


def test_stage_1_deduplicates_and_writes_normalized_pool(
    tmp_path: Path, fake_client: FixtureClient
) -> None:
    result = stage_01.collect_institutions(config(), fake_client, tmp_path, limit=3)

    assert [row["openalex_id"] for row in result.rows] == [
        "I100000001",
        "I100000002",
    ]
    assert result.rows[0]["discovery_filters"] == (
        "country_code:CA,type:education|country_code:GB,type:education"
    )
    assert result.summary["regions represented"] == 2
    assert result.job_id
    assert [call[1]["filter"] for call in fake_client.calls] == [
        "country_code:CA,type:education",
        "country_code:DE,type:education",
        "country_code:GB,type:education",
    ]

    output = tmp_path / "data" / "interim" / "institutions.csv"
    summary = tmp_path / "data" / "interim" / "institutions_summary.json"
    with output.open(encoding="utf-8", newline="") as stream:
        written_rows = list(csv.DictReader(stream))
    assert [row["openalex_id"] for row in written_rows] == [
        "I100000001",
        "I100000002",
    ]
    assert written_rows[0]["discovery_filters"] == result.rows[0]["discovery_filters"]
    assert json.loads(summary.read_text(encoding="utf-8")) == result.summary

    checkpoint = json.loads(
        (tmp_path / "data" / "raw" / "progress" / f"{result.job_id}.json").read_text(
            encoding="utf-8"
        )
    )
    assert checkpoint["status"] == "completed"
    assert checkpoint["completed_item_ids"] == [
        "country-CA__type-education",
        "country-DE__type-education",
        "country-GB__type-education",
    ]
    assert len(checkpoint["raw_pages"]) == 4


def test_stage_1_dry_run_prints_filters_without_constructing_client(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def reject_client_construction(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("dry-run must not construct an OpenAlex client")

    monkeypatch.setattr(stage_01, "OpenAlexClient", reject_client_construction)

    exit_code = stage_01.main(
        [
            "--config",
            str(ROOT / "config" / "dataset.yaml"),
            "--dry-run",
            "--limit",
            "3",
        ]
    )

    assert exit_code == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["estimated_jobs"] == 14
    assert plan["limit"] == 3
    assert plan["filters"][0] == "country_code:AU,type:education"
    assert plan["filters"][-1] == "country_code:US,type:healthcare"


def test_stage_1_limit_does_not_count_unique_omissions_as_duplicates(
    tmp_path: Path, fake_client: FixtureClient
) -> None:
    result = stage_01.collect_institutions(config(), fake_client, tmp_path, limit=1)

    assert [row["openalex_id"] for row in result.rows] == ["I100000001"]
    assert result.summary["duplicates removed"] == 1
    assert result.summary["institutions omitted by limit"] == 1


def test_stage_1_uses_configured_raw_progress_and_interim_paths(
    tmp_path: Path, fake_client: FixtureClient
) -> None:
    configured = config()
    raw_config = deepcopy(configured.raw)
    raw_config["paths"].update(
        {
            "raw": "custom/raw",
            "progress": "custom/state",
            "interim": "custom/interim",
        }
    )

    result = stage_01.collect_institutions(
        replace(configured, raw=raw_config), fake_client, tmp_path, limit=3
    )

    assert result.output_path == tmp_path / "custom/interim/institutions.csv"
    assert list((tmp_path / "custom/raw/pages").rglob("*.json"))
    assert (tmp_path / "custom/state" / f"{result.job_id}.json").is_file()


def test_stage_1_main_uses_configured_output_and_progress_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = write_config(
        tmp_path,
        interim="configured/interim",
        progress="configured/progress",
    )
    monkeypatch.chdir(tmp_path)

    assert stage_01.main(["--config", str(config_path), "--dry-run", "--limit", "1"]) == 0

    plan = json.loads(capsys.readouterr().out)
    assert plan["output"] == "configured/interim/institutions.csv"
    assert plan["state_dir"] == "configured/progress"


def test_stage_1_main_explicit_paths_override_configured_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = write_config(
        tmp_path,
        interim="configured/interim",
        progress="configured/progress",
    )
    monkeypatch.chdir(tmp_path)

    assert (
        stage_01.main(
            [
                "--config",
                str(config_path),
                "--dry-run",
                "--limit",
                "1",
                "--output",
                "explicit/institutions.csv",
                "--state-dir=explicit/progress",
            ]
        )
        == 0
    )

    plan = json.loads(capsys.readouterr().out)
    assert plan["output"] == "explicit/institutions.csv"
    assert plan["state_dir"] == "explicit/progress"


def test_stage_1_status_uses_configured_progress_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = write_config(tmp_path, progress="configured/progress")
    job_id = "a" * 64
    progress = new_progress(
        job_id=job_id,
        stage="01_fetch_institutions",
        setup={"endpoint": "institutions"},
        input_checksum="no-input",
        items=[],
        original_command="python scripts/01_fetch_institutions.py",
        output_path="configured/interim/institutions.csv",
    )
    ProgressStore(tmp_path / "configured/progress").save(progress)
    monkeypatch.chdir(tmp_path)

    assert stage_01.main(["--config", str(config_path), "--status", "--job-id", job_id]) == 0
    assert f"Job ID: {job_id}" in capsys.readouterr().out


def test_stage_1_skips_blank_non_string_and_malformed_institution_ids(
    tmp_path: Path, fake_client: FixtureClient
) -> None:
    fake_client.pages_by_filter["country_code:CA,type:education"][0].extend(
        [
            {"id": "", "display_name": "Blank ID"},
            {"id": 42, "display_name": "Non-string ID"},
            {"id": "https://openalex.org/", "display_name": "Malformed ID"},
            {"id": "not-an-institution-id", "display_name": "Wrong ID shape"},
        ]
    )

    result = stage_01.collect_institutions(config(), fake_client, tmp_path, limit=3)

    assert [row["openalex_id"] for row in result.rows] == [
        "I100000001",
        "I100000002",
    ]
    assert result.summary["invalid records skipped"] == 4
    assert result.output_path.is_file()
    assert result.summary_path.is_file()
