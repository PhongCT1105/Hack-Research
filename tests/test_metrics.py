"""Tests for the analysis metrics + the results join (Workstream 3).

Stdlib + synthetic data only — no network, no optional analysis extras.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from outreach_eval.metrics import (
    ClaimLabel,
    bootstrap_ci,
    cohen_kappa,
    condition_metrics,
    normalize_label,
    severe_error_rate,
    supported_personalization_density,
)
from outreach_eval.schemas import Condition, EmailRecord, EditAction, VerifierEdit

from compute_results import compute

S = ClaimLabel.SUPPORTED
U = ClaimLabel.UNSUPPORTED
C = ClaimLabel.CONTRADICTED
OV = ClaimLabel.OVERSTATED
SUBJ = ClaimLabel.SUBJECTIVE_OR_GENERIC
OUT = ClaimLabel.OUTSIDE_EVIDENCE_SCOPE


class LabelNormalizationTests(unittest.TestCase):
    def test_accepts_titlecase_and_spaces(self) -> None:
        self.assertEqual(normalize_label("Supported"), S)
        self.assertEqual(normalize_label("supported"), S)
        self.assertEqual(normalize_label("Outside evidence scope"), OUT)
        self.assertEqual(normalize_label("subjective_or_generic"), SUBJ)

    def test_rejects_unknown_and_empty(self) -> None:
        self.assertIsNone(normalize_label("research_topic"))  # a claim type, not a label
        self.assertIsNone(normalize_label(""))
        self.assertIsNone(normalize_label(None))


class MetricTests(unittest.TestCase):
    def test_severe_error_rate_excludes_non_factual(self) -> None:
        self.assertEqual(severe_error_rate([S, U, C, OV]), 0.5)  # 2 severe / 4 factual
        self.assertEqual(severe_error_rate([S, SUBJ, OUT, C]), 0.5)  # 1 severe / 2 factual
        self.assertIsNone(severe_error_rate([SUBJ, OUT]))  # no factual claims

    def test_spd(self) -> None:
        self.assertEqual(supported_personalization_density(3, 150), 2.0)
        self.assertIsNone(supported_personalization_density(3, 0))

    def test_cohen_kappa(self) -> None:
        self.assertIsNone(cohen_kappa([]))
        self.assertEqual(cohen_kappa([(S, S), (U, U)]), 1.0)  # perfect
        self.assertEqual(cohen_kappa([(S, S), (S, U), (U, U), (U, S)]), 0.0)  # chance-level

    def test_bootstrap_ci_deterministic_and_bracketing(self) -> None:
        vals = [0.0, 0.5, 1.0, 0.25, 0.75]
        a = bootstrap_ci(vals, seed=7)
        b = bootstrap_ci(vals, seed=7)
        self.assertEqual(a, b)
        self.assertIsNotNone(a)
        self.assertLessEqual(a[0], sum(vals) / len(vals))
        self.assertGreaterEqual(a[1], sum(vals) / len(vals))
        self.assertIsNone(bootstrap_ci([]))

    def test_condition_metrics(self) -> None:
        m = condition_metrics(
            "D",
            claims_by_email={"r1": [S, U], "r2": [S, S, OV]},
            words_by_email={"r1": 100, "r2": 100},
            verifier_edits_by_email={"r1": ["delete", "keep"]},
        )
        self.assertEqual(m.n_emails, 2)
        self.assertEqual(m.n_factual_claims, 5)
        self.assertAlmostEqual(m.severe_error_rate, 0.2)  # 1 severe / 5
        self.assertAlmostEqual(m.supported_personalization_density, 1.5)  # 3 supported / 200 * 100
        self.assertAlmostEqual(m.email_level_severe_rate, 0.5)  # r1 has severe, r2 doesn't
        self.assertAlmostEqual(m.verifier_deletion_rate, 0.5)


class ComputeJoinTests(unittest.TestCase):
    def _record(self, run_id, condition, verified=False):
        cond = Condition(condition)
        return EmailRecord(
            run_id=run_id, professor_id="CS-01", condition=cond, seed=1,
            writer_received_evidence=cond.writer_receives_evidence,
            verification_applied=cond.verification_applied,
            original_email="one two three four five",
            verified_email="one two three" if verified else "",
            verifier_edits=[VerifierEdit(claim_id="c1", action=EditAction.DELETE,
                                         original_span="x", reason="unsupported")] if verified else [],
            model="mock",
        )

    def test_end_to_end_join(self) -> None:
        records = [self._record("CS-01_A_1", "A"), self._record("CS-01_C_1", "C", verified=True)]
        map_rows = [
            {"claim_id": "E-1_c01", "run_id": "CS-01_A_1", "condition": "A", "professor_id": "CS-01"},
            {"claim_id": "E-2_c01", "run_id": "CS-01_C_1", "condition": "C", "professor_id": "CS-01"},
        ]
        label_rows = [
            {"claim_id": "E-1_c01", "final_label": "unsupported",
             "label_annotator_1": "unsupported", "label_annotator_2": "unsupported"},
            {"claim_id": "E-2_c01", "final_label": "Supported",
             "label_annotator_1": "supported", "label_annotator_2": "overstated"},
        ]
        results, kappa = compute(records, label_rows, map_rows)
        by_cond = {m.condition: m for m in results}
        self.assertEqual(by_cond["A"].severe_error_rate, 1.0)
        self.assertEqual(by_cond["C"].severe_error_rate, 0.0)
        self.assertAlmostEqual(kappa, 1 / 3, places=3)  # (U,U),(S,O)

    def test_unmapped_claims_are_ignored(self) -> None:
        records = [self._record("CS-01_A_1", "A")]
        map_rows = [{"claim_id": "E-1_c01", "run_id": "CS-01_A_1", "condition": "A",
                     "professor_id": "CS-01"}]
        label_rows = [{"claim_id": "ORPHAN", "final_label": "supported"}]
        results, kappa = compute(records, label_rows, map_rows)
        self.assertEqual(results, [])
        self.assertIsNone(kappa)


if __name__ == "__main__":
    unittest.main()
