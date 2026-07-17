"""Tests for the auto-evaluator judge (scripts/auto_evaluate.py). No network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from auto_evaluate import judge_email

from outreach_eval.schemas import Condition, EmailRecord, EvidencePacket, ExtractedClaim

ROOT = Path(__file__).resolve().parents[1]
PACKET = EvidencePacket.model_validate_json((ROOT / "data/evidence/MOCK-01.json").read_text())


class StubClient:
    def __init__(self, reply: str):
        self.reply = reply
        self.model = "stub"

    def complete(self, system: str, user: str, *, seed=None) -> str:
        return self.reply


def record_with_claims(*texts):
    return EmailRecord(
        run_id="MOCK-01_A_1", professor_id="MOCK-01", condition=Condition.A, seed=1,
        writer_received_evidence=False, verification_applied=False,
        original_email="body", model="mock",
        extracted_claims=[ExtractedClaim(claim_id=f"MOCK-01_A_1_c{i}", atomic_claim=t)
                          for i, t in enumerate(texts, 1)],
    )


class JudgeTests(unittest.TestCase):
    def test_maps_numbered_labels_to_claim_ids(self) -> None:
        rec = record_with_claims("claim one", "claim two")
        client = StubClient('{"labels":[{"n":1,"label":"Supported"},{"n":2,"label":"unsupported"}]}')
        out = judge_email(rec, PACKET, client)
        self.assertEqual(out["MOCK-01_A_1_c1"], "supported")  # Title-case normalized
        self.assertEqual(out["MOCK-01_A_1_c2"], "unsupported")

    def test_handles_code_fence_and_bad_indices(self) -> None:
        rec = record_with_claims("only claim")
        client = StubClient('```json\n{"labels":[{"n":1,"label":"contradicted"},'
                            '{"n":9,"label":"supported"}]}\n```')
        out = judge_email(rec, PACKET, client)
        self.assertEqual(out, {"MOCK-01_A_1_c1": "contradicted"})  # n=9 out of range dropped

    def test_unknown_label_dropped(self) -> None:
        rec = record_with_claims("claim")
        out = judge_email(rec, PACKET, StubClient('{"labels":[{"n":1,"label":"maybe"}]}'))
        self.assertEqual(out, {})

    def test_no_claims_returns_empty(self) -> None:
        rec = record_with_claims()
        self.assertEqual(judge_email(rec, PACKET, StubClient("{}")), {})


if __name__ == "__main__":
    unittest.main()
