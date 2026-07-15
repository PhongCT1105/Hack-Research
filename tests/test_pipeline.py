"""Unit tests for the generation + verification pipeline (Workstream 2).

Uses the offline MockClient only — no network (CLAUDE.md: no network in tests).
Covers the invariants the pilot freeze depends on: condition logic, evidence-block
inclusion, verify-only-on-C/D, claim extraction on the final email, run-id keying,
and JSONL / manifest I/O round-trips.
"""

from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outreach_eval.conditions import (
    build_evidence_block,
    professor_reference,
    writer_evidence_block,
)
from outreach_eval.extract_claims import extract_claims
from outreach_eval.generate import PROMPT_VERSION, generate_email, load_prompt_sections
from outreach_eval.io_utils import (
    MANIFEST_FIELDS,
    append_jsonl,
    append_manifest_row,
    read_jsonl,
)
from outreach_eval.llm import MockClient, RoleConfig, get_client
from outreach_eval.schemas import Condition, EvidencePacket
from outreach_eval.verify import deletion_rate, verify_email

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / "data" / "evidence"
PROMPTS = ROOT / "prompts"
MOCK_CFG = RoleConfig(provider="mock", model="test-model", temperature=0.0, max_tokens=256)


def mock_client() -> MockClient:
    return get_client(MOCK_CFG)


def load_mock_packet() -> EvidencePacket:
    return EvidencePacket.model_validate_json((EVIDENCE_DIR / "MOCK-01.json").read_text())


class ConditionLogicTests(unittest.TestCase):
    def test_factorial_flags(self) -> None:
        expected = {
            Condition.A: (False, False),
            Condition.B: (True, False),
            Condition.C: (False, True),
            Condition.D: (True, True),
        }
        for cond, (evidence, verify) in expected.items():
            self.assertEqual(cond.writer_receives_evidence, evidence, cond)
            self.assertEqual(cond.verification_applied, verify, cond)

    def test_writer_evidence_block_only_for_b_and_d(self) -> None:
        packet = load_mock_packet()
        self.assertEqual(writer_evidence_block(packet, Condition.A), "")
        self.assertEqual(writer_evidence_block(packet, Condition.C), "")
        self.assertNotEqual(writer_evidence_block(packet, Condition.B), "")
        self.assertEqual(
            writer_evidence_block(packet, Condition.B),
            writer_evidence_block(packet, Condition.D),
        )

    def test_evidence_block_contains_all_packet_parts(self) -> None:
        packet = load_mock_packet()
        block = build_evidence_block(packet)
        self.assertIn(packet.faculty_summary, block)
        for paper in packet.papers:
            self.assertIn(paper.title, block)
        for passage in packet.focal_passages:
            self.assertIn(passage.text, block)

    def test_professor_reference_uses_field(self) -> None:
        packet = load_mock_packet()
        ref = professor_reference(packet)
        self.assertIn(packet.field, ref)


class WriterStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = load_mock_packet()
        self.client = mock_client()
        self.prompt = PROMPTS / "writer_v1.md"

    def test_record_shape_and_run_id(self) -> None:
        record = generate_email(self.packet, Condition.B, 1, self.client, self.prompt, 220)
        self.assertEqual(record.run_id, "MOCK-01_B_1")
        self.assertEqual(record.professor_id, "MOCK-01")
        self.assertTrue(record.writer_received_evidence)
        self.assertFalse(record.verification_applied)
        self.assertTrue(record.original_email)
        self.assertEqual(record.verified_email, "")
        self.assertEqual(record.model, self.client.model)
        self.assertEqual(record.prompt_version, PROMPT_VERSION)
        self.assertTrue(record.timestamp)

    def test_flags_match_condition(self) -> None:
        for cond in Condition:
            record = generate_email(self.packet, cond, 2, self.client, self.prompt, 220)
            self.assertEqual(record.writer_received_evidence, cond.writer_receives_evidence)
            self.assertEqual(record.verification_applied, cond.verification_applied)
            self.assertTrue(record.run_id.endswith(f"_{cond.value}_2"))

    def test_load_prompt_sections_splits_system_and_user(self) -> None:
        system, user = load_prompt_sections(PROMPTS / "writer_v1.md")
        self.assertIn("outreach email", system.lower())
        self.assertIn("{evidence_block}", user)
        # Documentation sections must not leak into the prompt body.
        self.assertNotIn("Slot definitions", user)
        self.assertNotIn("Change log", user)

    def test_missing_section_raises(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "bad.md"
            bad.write_text("## System\nonly system, no user section\n")
            with self.assertRaises(ValueError):
                load_prompt_sections(bad)


class VerifierStageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = load_mock_packet()
        self.client = mock_client()
        self.writer_prompt = PROMPTS / "writer_v1.md"
        self.verifier_prompt = PROMPTS / "verifier_v1.md"

    def test_verify_refuses_non_verified_conditions(self) -> None:
        record = generate_email(self.packet, Condition.A, 1, self.client, self.writer_prompt, 220)
        with self.assertRaises(ValueError):
            verify_email(record, self.packet, self.client, self.verifier_prompt)

    def test_verify_populates_and_does_not_mutate_original(self) -> None:
        record = generate_email(self.packet, Condition.D, 1, self.client, self.writer_prompt, 220)
        verified = verify_email(record, self.packet, self.client, self.verifier_prompt)
        # Original record is untouched (outputs are append-only).
        self.assertEqual(record.verified_email, "")
        self.assertEqual(record.extracted_claims, [])
        # Verified copy is populated.
        self.assertTrue(verified.verified_email)
        self.assertTrue(verified.extracted_claims)
        self.assertTrue(verified.verifier_edits)
        self.assertEqual(verified.run_id, record.run_id)

    def test_deletion_rate(self) -> None:
        record = generate_email(self.packet, Condition.C, 1, self.client, self.writer_prompt, 220)
        verified = verify_email(record, self.packet, self.client, self.verifier_prompt)
        rate = deletion_rate(verified)
        self.assertGreaterEqual(rate, 0.0)
        self.assertLessEqual(rate, 1.0)
        # Empty-edit record is defined as zero deletions, not a divide-by-zero.
        self.assertEqual(deletion_rate(record), 0.0)


class ClaimExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.packet = load_mock_packet()
        self.client = mock_client()

    def test_claim_ids_are_namespaced_by_run(self) -> None:
        record = generate_email(
            self.packet, Condition.A, 1, self.client, PROMPTS / "writer_v1.md", 220
        )
        claims = extract_claims(record, self.client, PROMPTS / "claim_extractor_v1.md")
        self.assertTrue(claims)
        for claim in claims:
            self.assertTrue(claim.claim_id.startswith(record.run_id))
            self.assertIsNone(claim.machine_label)  # extractor never labels

    def test_final_email_is_source_of_extraction(self) -> None:
        # A/B: final == original; C/D: final == verified.
        a = generate_email(self.packet, Condition.A, 1, self.client, PROMPTS / "writer_v1.md", 220)
        self.assertEqual(a.final_email, a.original_email)
        d = generate_email(self.packet, Condition.D, 1, self.client, PROMPTS / "writer_v1.md", 220)
        d = verify_email(d, self.packet, self.client, PROMPTS / "verifier_v1.md")
        self.assertEqual(d.final_email, d.verified_email)


class IoRoundTripTests(unittest.TestCase):
    def test_jsonl_round_trip(self) -> None:
        packet = load_mock_packet()
        client = mock_client()
        record = verify_email(
            generate_email(packet, Condition.D, 1, client, ROOT / "prompts/writer_v1.md", 220),
            packet,
            client,
            ROOT / "prompts/verifier_v1.md",
        )
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "out.jsonl"
            append_jsonl(path, record)
            append_jsonl(path, record)
            loaded = read_jsonl(path)
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].run_id, record.run_id)
        self.assertEqual(loaded[0].verified_email, record.verified_email)
        self.assertEqual(loaded[0].condition, Condition.D)

    def test_manifest_header_written_once(self) -> None:
        row = {field: "x" for field in MANIFEST_FIELDS}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "manifest.csv"
            append_manifest_row(path, row)
            append_manifest_row(path, row)
            rows = list(csv.reader(path.open()))
        self.assertEqual(rows[0], MANIFEST_FIELDS)
        self.assertEqual(len(rows), 3)  # 1 header + 2 data rows


if __name__ == "__main__":
    unittest.main()
