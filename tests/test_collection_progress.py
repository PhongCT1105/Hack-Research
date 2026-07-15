from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _collection_progress import (  # noqa: E402
    ProgressStore,
    complete_item,
    make_job_id,
    new_progress,
    parse_rate_limit_headers,
    parse_rate_limit_payload,
    pause_rate_limit,
    record_page,
    render_status,
    start_item,
)


SYNTHETIC_ITEMS = [
    {"item_type": "professor", "item_id": "MOCK-01", "provider_id": "A100000001"},
    {"item_type": "professor", "item_id": "MOCK-02", "provider_id": "A100000002"},
    {"item_type": "professor", "item_id": "MOCK-03", "provider_id": "A100000003"},
    {"item_type": "professor", "item_id": "MOCK-04", "provider_id": "A100000004"},
]


class CollectionProgressTests(unittest.TestCase):
    def test_job_id_ignores_api_key_but_changes_with_filter(self) -> None:
        first = make_job_id(
            "04_fetch_author_works",
            {"endpoint": "works", "filter": "author.id:A1", "api_key": "secret-one"},
            "input-checksum",
        )
        changed_key = make_job_id(
            "04_fetch_author_works",
            {"endpoint": "works", "filter": "author.id:A1", "api_key": "secret-two"},
            "input-checksum",
        )
        changed_filter = make_job_id(
            "04_fetch_author_works",
            {"endpoint": "works", "filter": "author.id:A2", "api_key": "secret-one"},
            "input-checksum",
        )

        self.assertEqual(first, changed_key)
        self.assertNotEqual(first, changed_filter)
        self.assertEqual(len(first), 64)

    def test_progress_store_keeps_different_commands_separate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ProgressStore(directory)
            first = self._new_progress(filter_value="author.id:A1")
            second = self._new_progress(filter_value="author.id:A2")

            store.save(first)
            store.save(second)

            self.assertEqual(store.load(first["job_id"]), first)
            self.assertEqual(store.load(second["job_id"]), second)
            self.assertEqual(store.list_job_ids(), sorted([first["job_id"], second["job_id"]]))
            state_text = (Path(directory) / f"{first['job_id']}.json").read_text()
            self.assertNotIn("secret-api-key", state_text)

    def test_saved_commands_redact_inline_api_key(self) -> None:
        setup = {"endpoint": "works", "filter": "author.id:A1"}
        progress = new_progress(
            job_id=make_job_id("04_fetch_author_works", setup, "input-checksum"),
            stage="04_fetch_author_works",
            setup=setup,
            input_checksum="input-checksum",
            items=SYNTHETIC_ITEMS,
            original_command=(
                ".venv/bin/python scripts/04_fetch_author_works.py "
                "--api-key top-secret-value --input data/interim/verified_professors.csv"
            ),
            output_path="data/raw/author_works",
        )

        self.assertNotIn("top-secret-value", progress["original_command"])
        self.assertNotIn("top-secret-value", progress["resume_command"])
        self.assertIn("[REDACTED]", progress["original_command"])

    def test_rate_limit_pause_keeps_exact_profile_and_cursor(self) -> None:
        progress = self._new_progress()
        start_item(progress, 0)
        complete_item(progress)
        start_item(progress, 1)
        complete_item(progress)
        start_item(progress, 2, cursor="cursor-before-page")
        record_page(
            progress,
            record_count=30,
            next_cursor="cursor-after-page",
            request_hash="request-hash-3",
            rate_limit={"credits_remaining": 0, "resets_in_seconds": 18000},
        )
        pause_rate_limit(
            progress,
            {"credits_remaining": 0, "resets_at": "2026-07-15T00:00:00Z"},
        )

        self.assertEqual(progress["status"], "paused_rate_limit")
        self.assertEqual(progress["completed_item_ids"], ["MOCK-01", "MOCK-02"])
        self.assertEqual(progress["current_item"]["item_id"], "MOCK-03")
        self.assertEqual(progress["current_cursor"], "cursor-after-page")
        self.assertEqual(progress["next_item"]["item_id"], "MOCK-04")
        self.assertEqual(progress["records_written"], 30)
        self.assertEqual(progress["pages_written"], 1)
        self.assertIn("--resume", progress["resume_command"])

    def test_openalex_rate_limit_shapes_are_normalized(self) -> None:
        headers = parse_rate_limit_headers(
            {
                "X-RateLimit-Limit": "10000",
                "x-ratelimit-remaining": "0",
                "X-RateLimit-Credits-Used": "1",
                "X-RateLimit-Reset": "18000",
            }
        )
        payload = parse_rate_limit_payload(
            {
                "rate_limit": {
                    "daily_remaining_usd": 0.0,
                    "prepaid_remaining_usd": 2.5,
                    "credits_remaining": 0,
                    "resets_at": "2026-07-15T00:00:00Z",
                    "resets_in_seconds": 18000,
                }
            }
        )

        self.assertEqual(headers["credits_remaining"], 0)
        self.assertEqual(headers["resets_in_seconds"], 18000)
        self.assertEqual(payload["daily_remaining_usd"], 0.0)
        self.assertEqual(payload["prepaid_remaining_usd"], 2.5)

    def test_status_is_human_readable_and_survives_copy(self) -> None:
        progress = self._new_progress()
        start_item(progress, 2, cursor="saved-cursor")
        pause_rate_limit(
            progress,
            {
                "credits_remaining": 0,
                "resets_at": "2026-07-15T00:00:00Z",
                "resets_in_seconds": 18000,
            },
        )
        expected = render_status(progress)

        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first_store = ProgressStore(first_dir)
            second_store = ProgressStore(second_dir)
            first_store.save(progress)
            copied = copy.deepcopy(first_store.load(progress["job_id"]))
            second_store.save(copied)

            actual = render_status(second_store.load(progress["job_id"]))

        self.assertEqual(actual, expected)
        self.assertIn("Current professor: MOCK-03 (A100000003)", actual)
        self.assertIn("Next professor: MOCK-04 (A100000004)", actual)
        self.assertIn("Status: paused_rate_limit", actual)
        self.assertIn("Resume command:", actual)

    def _new_progress(self, filter_value: str = "author.id:A1") -> dict[str, object]:
        setup = {
            "dataset_version": "benchmark-v1",
            "endpoint": "works",
            "filter": filter_value,
            "api_key": "secret-api-key",
        }
        job_id = make_job_id("04_fetch_author_works", setup, "input-checksum")
        return new_progress(
            job_id=job_id,
            stage="04_fetch_author_works",
            setup=setup,
            input_checksum="input-checksum",
            items=SYNTHETIC_ITEMS,
            original_command=(
                ".venv/bin/python scripts/04_fetch_author_works.py "
                "--config config/dataset.yaml --input data/interim/verified_professors.csv "
                "--output data/raw/author_works --state-dir data/raw/progress"
            ),
            output_path="data/raw/author_works",
        )


if __name__ == "__main__":
    unittest.main()
