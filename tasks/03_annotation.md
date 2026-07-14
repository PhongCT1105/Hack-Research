# Workstream 3 — Annotation & Evaluation

**Owner:** Kanan (primary annotator/manager) · **Second annotator:** Azhdar ·
**Adjudicator:** Phong · **Blinding/data prep:** Abhinav
**Depends on:** rubric (ready now) → pilot claims (after pipeline pilot) → full claims (after freeze).

## Objective

Human-validated claim labels, agreement statistics, and the full factuality +
supported-personalization results table and figures.

## Inputs

- `docs/annotation_rubric.md` (labels, claim types, decision rules — DRAFT until freeze)
- `docs/analysis_plan.md` (metrics, models)
- `annotations/claims_to_label.csv` (blinded, produced by Workstream 2)
- `outputs/*.jsonl` (for word counts and verifier edit stats — via scripts, not manual reading of conditions)

## Outputs (file contract)

| File | Content |
|---|---|
| `annotations/rubric_notes.md` | Clarifications/edge cases discovered while annotating (feeds rubric before freeze) |
| `annotations/human_labels.csv` | Sheet fields per `docs/annotation_rubric.md` (both annotators + final adjudicated label) |
| `annotations/edge_cases.md` | Decision log of hard calls |
| `analysis/results.csv` | Per-email and per-condition metrics |
| `analysis/figures/` | Frontier plot, condition comparisons, interaction plots, claim-type error profile |
| `analysis/notebooks/` | Reproducible metric + model notebooks |

## Steps

1. **Now (no dependencies):** finalize the annotation sheet template from the rubric;
   write 10–15 synthetic practice claims with gold labels to calibrate annotators.
2. **Pilot phase:** label the 16-email pilot claims; test that claims are atomic and the
   rubric is applicable; report problems at the checkpoint (this is the last chance to
   change the rubric).
3. **Main annotation:** primary blind annotation (Kanan) + second blind annotation
   (Azhdar) on ≥25% overlap; Phong adjudicates disagreements; document every
   adjudication.
4. **Agreement:** compute Cohen's κ / Krippendorff's α on the overlap set.
5. **Auto-evaluator validation (if used at scale):** compare LLM labels vs adjudicated
   gold — per-label precision/recall/F1 + calibration.
6. **Metrics:** compute per `docs/analysis_plan.md`:
   - Severe Error Rate; % emails with ≥1 severe error; overstatement rate
   - Supported Personalization Density (per 100 words)
   - Verifier deletion + rewrite rates
   - Human usefulness/specificity scores
7. **Models:** fit the mixed-effects models from the analysis plan (nested random
   effects; no flat t-tests). Produce estimated marginal means + interaction plots.
8. **Figures:** the Supported Specificity Frontier is the headline figure.

## Completion Criteria

- [ ] Claims atomic and independently judgeable (verified on pilot)
- [ ] Annotators blinded to condition and original/verified status throughout
- [ ] ≥25% of claims double-annotated; adjudications documented
- [ ] Human–human and AI–human agreement reported
- [ ] Factuality AND supported-personalization metrics both reported
- [ ] Mixed-effects results with CIs and interaction plots delivered to Workstream 4

## Agent Notes

- Never join `human_labels.csv` with the blinding map inside an annotation-facing
  artifact; the join happens only in analysis code after labels are final.
- Exclude `subjective_or_generic` and `outside_evidence_scope` from the factual
  denominator; report their frequencies separately.
- If statsmodels mixed-model fitting is unstable at pilot scale, fall back to
  professor-level aggregation + paired comparisons for the pilot, but keep the full
  model for the main run.
