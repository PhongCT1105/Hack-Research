"""Tests for the auto-evaluator vs human-label agreement (scripts/validate_evaluator.py)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from validate_evaluator import compute_agreement


def m(claim_id, label):
    return {"claim_id": claim_id, "final_label": label}


class AgreementTests(unittest.TestCase):
    def test_only_shared_claims_compared(self) -> None:
        machine = [m("c1", "supported"), m("c2", "unsupported"), m("c3", "supported")]
        human = [m("c1", "supported"), m("c2", "unsupported")]  # c3 not human-labeled
        stats = compute_agreement(machine, human)
        self.assertEqual(stats["n"], 2)
        self.assertEqual(stats["agreement"], 1.0)
        self.assertEqual(stats["kappa"], 1.0)

    def test_per_label_precision_recall(self) -> None:
        # machine calls c2 unsupported but human says supported -> recall/precision drop
        machine = [m("c1", "supported"), m("c2", "unsupported"), m("c3", "supported")]
        human = [m("c1", "supported"), m("c2", "supported"), m("c3", "supported")]
        stats = compute_agreement(machine, human)
        self.assertEqual(stats["n"], 3)
        sup = stats["per_label"]["supported"]
        self.assertEqual(sup["human_count"], 3)
        self.assertAlmostEqual(sup["recall"], 2 / 3)   # 2 of 3 human-supported caught
        self.assertAlmostEqual(sup["precision"], 1.0)  # both machine-supported were right

    def test_empty_overlap(self) -> None:
        stats = compute_agreement([m("c1", "supported")], [m("c9", "supported")])
        self.assertEqual(stats["n"], 0)
        self.assertIsNone(stats["kappa"])

    def test_tolerates_titlecase(self) -> None:
        stats = compute_agreement([m("c1", "Supported")], [m("c1", "supported")])
        self.assertEqual(stats["agreement"], 1.0)


if __name__ == "__main__":
    unittest.main()
