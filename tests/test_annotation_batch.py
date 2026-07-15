"""Tests for the blinded annotation-batch builder (scripts/build_annotation_batch.py).

Verifies the blinding guarantees Workstream 3 depends on: no condition/seed/version
leakage, real names scrubbed, deterministic shuffle, and a complete join map.
"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_annotation_batch import (
    MAP_FIELDS,
    SHEET_FIELDS,
    _write_csv,
    build_batch,
    name_variants,
    scrub_names,
)
from outreach_eval.schemas import Condition, EmailRecord, ExtractedClaim


def make_record(condition: Condition, seed: int, claims: list[str]) -> EmailRecord:
    cond = Condition(condition)
    return EmailRecord(
        run_id=f"CS-01_{cond.value}_{seed}",
        professor_id="CS-01",
        condition=cond,
        seed=seed,
        writer_received_evidence=cond.writer_receives_evidence,
        verification_applied=cond.verification_applied,
        original_email="body",
        verified_email="verified body" if cond.verification_applied else "",
        extracted_claims=[
            ExtractedClaim(claim_id=f"c{i}", atomic_claim=text)
            for i, text in enumerate(claims, start=1)
        ],
        model="mock-x",
    )


class NameScrubTests(unittest.TestCase):
    def test_variants_include_full_name_and_surname_not_honorific(self) -> None:
        variants = name_variants("Jane Q. Smith")
        self.assertIn("Jane Q. Smith", variants)
        self.assertIn("Smith", variants)
        # "Professor" must never be picked as a standalone token to blank out.
        self.assertNotIn("Professor", name_variants("Professor Ada Lovelace"))

    def test_short_surname_is_scrubbed(self) -> None:
        # Regression: a 2-char surname (common in Chinese/Korean names) must be caught,
        # since emails address the professor by surname ("Dear Prof. Du").
        variants = name_variants("Zhaoping Du")
        self.assertIn("Du", variants)
        self.assertIn("Zhaoping", variants)
        out = scrub_names("Prof. Du's work; DU studies control.", variants)
        self.assertNotIn("Du", out)
        self.assertNotIn("DU", out)

    def test_common_word_surname_not_over_scrubbed(self) -> None:
        # Ambiguous 2-letter English words are left alone to avoid mangling text.
        self.assertNotIn("He", name_variants("Ada He"))

    def test_scrub_replaces_name_case_insensitive_and_possessive(self) -> None:
        text = "Smith studies calibration; SMITH's 2024 paper is on triage."
        out = scrub_names(text, name_variants("Jane Smith"))
        self.assertNotIn("Smith", out)
        self.assertNotIn("SMITH", out)
        self.assertIn("the professor", out)

    def test_empty_name_yields_no_variants(self) -> None:
        self.assertEqual(name_variants(""), [])
        self.assertEqual(name_variants("(fictional)"), [])


class BuildBatchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.records = [
            make_record(Condition.A, 1, ["Jane Smith studies calibration.", "Uses fMRI."]),
            make_record(Condition.D, 2, ["Jane Smith pioneered triage models."]),
        ]
        self.name_map = {"CS-01": name_variants("Jane Smith")}

    def test_sheet_has_no_condition_or_version_leakage(self) -> None:
        sheet, _ = build_batch(self.records, self.name_map, seed=42, batch_tag="pilot-01")
        self.assertEqual(list(sheet[0].keys()), SHEET_FIELDS)
        blob = " ".join(str(v) for row in sheet for v in row.values())
        # No run ids, condition letters as run keys, or verified flags reach annotators.
        self.assertNotIn("CS-01_A_1", blob)
        self.assertNotIn("CS-01_D_2", blob)
        self.assertNotIn("verified", blob.lower())
        # Real name scrubbed everywhere in the sheet.
        self.assertNotIn("Smith", blob)

    def test_label_columns_are_empty(self) -> None:
        sheet, _ = build_batch(self.records, self.name_map, seed=42, batch_tag="pilot-01")
        for row in sheet:
            self.assertEqual(row["label_annotator_1"], "")
            self.assertEqual(row["label_annotator_2"], "")
            self.assertEqual(row["final_label"], "")

    def test_map_covers_every_claim_and_recovers_truth(self) -> None:
        sheet, mapping = build_batch(self.records, self.name_map, seed=42, batch_tag="pilot-01")
        self.assertEqual(len(sheet), len(mapping))
        self.assertEqual(len(mapping), 3)  # 2 + 1 claims
        self.assertEqual(list(mapping[0].keys()), MAP_FIELDS)
        by_claim = {m["claim_id"]: m for m in mapping}
        for row in sheet:
            self.assertIn(row["claim_id"], by_claim)
        conditions = {m["condition"] for m in mapping}
        self.assertEqual(conditions, {"A", "D"})

    def test_shuffle_is_deterministic(self) -> None:
        a, _ = build_batch(self.records, self.name_map, seed=42, batch_tag="pilot-01")
        b, _ = build_batch(self.records, self.name_map, seed=42, batch_tag="pilot-01")
        self.assertEqual([r["claim_id"] for r in a], [r["claim_id"] for r in b])

    def test_csv_write_round_trip(self) -> None:
        sheet, mapping = build_batch(self.records, self.name_map, seed=42, batch_tag="pilot-01")
        with tempfile.TemporaryDirectory() as d:
            sheet_path = Path(d) / "sheet.csv"
            map_path = Path(d) / "map.csv"
            _write_csv(sheet_path, SHEET_FIELDS, sheet)
            _write_csv(map_path, MAP_FIELDS, mapping)
            with sheet_path.open() as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 3)
        self.assertEqual(list(rows[0].keys()), SHEET_FIELDS)


if __name__ == "__main__":
    unittest.main()
