# For Kanan — Results context + your validation task

## What happened

The full pipeline ran: 96 emails, 12 professors, **360 atomic claims** extracted and labelled
by an **automatic evaluator** (an LLM judge). Preliminary results (auto-labels):

| Condition | Severe Error Rate | Specificity (SPD) |
|-----------|-------------------|-------------------|
| A closed-book | 0.34 | 0.65 |
| B grounded | 0.00 | 1.71 |
| C verify-only | 0.02 | 1.04 |
| D grounded+verified | 0.00 | 1.76 |

Clean story: grounding removes severe errors and doubles specificity. **But these are machine
labels, not human ones.** The judge is generous (68% "supported"), so the exact 0.00s need a
human check. **That check is your job — and it's the piece that makes the results credible.**

## Your task: validate the auto-evaluator with human labels

1. **Open** `annotations/claims_to_label.csv` (in the repo, 360 blinded claims — no condition,
   no real names). You do NOT need to label all 360.
2. **Label a subset** — aim for ~25% (about 90 claims), a spread across the sheet. For each
   claim fill `label_annotator_1`, `label_annotator_2` (a second annotator — Azhdar is the
   backup), and `final_label`, using your rubric (`docs/annotation_rubric.md`). Use exactly the
   7 labels: supported / partially_supported / overstated / unsupported / contradicted /
   outside_evidence_scope / subjective_or_generic (Title Case is fine — the code normalizes it).
3. **Save as** `annotations/human_labels.csv` (same columns). Commit / send it to Abhinav.

That's it. You judge each claim against the professor's evidence packet exactly as your rubric
says — you are NOT told which condition or model produced it (that's the blinding working).

## What your labels produce (Abhinav runs these)

- `scripts/validate_evaluator.py` → **Cohen's κ** (auto-evaluator vs your human labels) +
  per-label precision/recall/F1. This is the number the paper needs to justify trusting the
  auto-labels ("automatic-evaluator agreement against a human-adjudicated subset" in Methods).
- `scripts/compute_results.py --labels annotations/human_labels.csv` → a human-labelled results
  variant + human–human agreement (from your two annotator columns).

## Note for the write-up

If your human labels find MORE errors than the judge did (likely — the judge was lenient), that
is itself a finding: the auto-evaluator gives a *conservative* (lower-bound) error rate, so the
true gap between closed-book and grounded is at least as large as reported. Flag any claims
where you strongly disagree with the machine in `annotations/edge_cases.md`.
