from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "01_fetch_institutions.py",
    "02_fetch_author_candidates.py",
    "03_verify_faculty_status.py",
    "04_fetch_author_works.py",
    "05_reconstruct_abstracts.py",
    "06_reconcile_metadata.py",
    "07_score_paper_complexity.py",
    "08_score_research_portfolios.py",
    "09_select_representative_papers.py",
    "10_stratified_sample_professors.py",
    "11_build_evidence_packets.py",
    "12_validate_dataset.py",
]


class DatasetScaffoldTests(unittest.TestCase):
    def test_every_stage_exposes_help(self) -> None:
        for name in SCRIPTS:
            path = ROOT / "scripts" / name
            self.assertTrue(path.exists(), name)
            completed = subprocess.run(
                [sys.executable, str(path), "--help"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("--config", completed.stdout)
            self.assertIn("--dry-run", completed.stdout)
            self.assertIn("--cache-dir", completed.stdout)
            self.assertIn("--log-file", completed.stdout)
            self.assertIn("--state-dir", completed.stdout)
            self.assertIn("--resume", completed.stdout)
            self.assertIn("--status", completed.stdout)
            self.assertIn("--job-id", completed.stdout)
            self.assertIn("--restart", completed.stdout)
            self.assertIn("--limit", completed.stdout)
            self.assertIn("--full-run", completed.stdout)

    def test_abstract_reconstruction_is_deterministic(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from _dataset_cli import reconstruct_abstract

            inverted = {"evidence": [2], "Verified": [0], "helps": [1, 3]}
            self.assertEqual(reconstruct_abstract(inverted), "Verified helps evidence helps")
            self.assertIsNone(reconstruct_abstract(None))
        finally:
            sys.path.pop(0)

    def test_numbered_script_can_print_local_checkpoint_status(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from _collection_progress import ProgressStore, make_job_id, new_progress, start_item

            with tempfile.TemporaryDirectory() as directory:
                setup = {"endpoint": "institutions", "filter": "country_code:US"}
                job_id = make_job_id("01_fetch_institutions", setup, "no-input")
                progress = new_progress(
                    job_id=job_id,
                    stage="01_fetch_institutions",
                    setup=setup,
                    input_checksum="no-input",
                    items=[
                        {
                            "item_type": "institution",
                            "item_id": "MOCK-INST-01",
                            "provider_id": "I100000001",
                        }
                    ],
                    original_command=(
                        ".venv/bin/python scripts/01_fetch_institutions.py "
                        "--config config/dataset.yaml --output data/raw/institutions"
                    ),
                    output_path="data/raw/institutions",
                )
                start_item(progress, 0, cursor="saved-cursor")
                ProgressStore(directory).save(progress)

                completed = subprocess.run(
                    [
                        sys.executable,
                        str(ROOT / "scripts" / "01_fetch_institutions.py"),
                        "--status",
                        "--job-id",
                        job_id,
                        "--state-dir",
                        directory,
                    ],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Current institution: MOCK-INST-01 (I100000001)", completed.stdout)
            self.assertIn("Resume command:", completed.stdout)
        finally:
            sys.path.pop(0)

    def test_abstract_reconstruction_rejects_duplicate_positions(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from _dataset_cli import reconstruct_abstract

            with self.assertRaisesRegex(ValueError, "duplicate abstract position"):
                reconstruct_abstract({"one": [0], "other": [0]})
        finally:
            sys.path.pop(0)

    def test_atomic_json_write_refuses_silent_overwrite(self) -> None:
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            from _dataset_cli import write_json_atomic

            with tempfile.TemporaryDirectory() as directory:
                destination = Path(directory) / "record.json"
                write_json_atomic(destination, {"version": 1})
                with self.assertRaises(FileExistsError):
                    write_json_atomic(destination, {"version": 2})
                self.assertEqual(json.loads(destination.read_text()), {"version": 1})
                write_json_atomic(destination, {"version": 2}, force=True)
                self.assertEqual(json.loads(destination.read_text()), {"version": 2})
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
