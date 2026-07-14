# Analysis Plan

## Metrics

| Role | Metric | Definition / purpose |
|---|---|---|
| **Primary factuality** | Severe Error Rate (SER) | (unsupported + contradicted) / all judged factual claims — misrepresentation risk |
| **Primary personalization** | Supported Personalization Density (SPD) | supported research-specific claims per 100 words — separates factual-and-specific from factual-but-generic |
| Secondary factuality | Supported-claim precision; overstatement rate; email-level any-severe-error rate | Softer and harsher failure modes |
| Content preservation | Verifier deletion rate; rewrite rate; edit distance from original | Prevents the verifier from "winning" by erasing content |
| Usefulness (human) | Usefulness, relevance-to-professor, naturalness/professionalism scores | Keeps the task anchored in outreach quality |
| Evaluator validity | Human–human κ/α; auto-evaluator vs adjudicated gold (P/R/F1, calibration) | Required for any automatic grading |

**Denominator rule:** `subjective_or_generic` and `outside_evidence_scope` claims are
excluded from the factual denominator (reported separately).

### The Supported Specificity Frontier

Key figure: each condition plotted at
**x = severe errors per 100 words, y = supported research-specific claims per 100 words.**
Best systems sit upper-left. If verification reduces x but collapses y, that is the
factuality–personalization trade-off this paper exists to expose. The four separable
outcomes:

| | Low SER | High SER |
|---|---|---|
| **High SPD** | factual and highly personalized ✅ | detailed but inaccurate ⚠️ |
| **Low SPD** | factual but generic 😐 | inaccurate and generic ❌ |

## Statistical Models

Claims are nested within emails, emails within professors — **never analyze claims as
independent observations; no flat t-tests.**

**Claim-level severe errors** (logistic mixed model):

```
error ~ grounding * verification + field + visibility
        + (1 | professor) + (1 | professor:email)
```

**Counts per email** (unsupported claims, etc.): negative binomial mixed model with a
word-count offset.

**Likert ratings** (usefulness/relevance): cumulative link mixed model (or linear mixed
model for implementation simplicity).

**Report:** estimated marginal means, confidence intervals, and interaction plots for
grounding × verification. Include field as fixed effect + field-specific error analysis.

**Implementation:** Python `statsmodels` (or R `lme4`/`ordinal` if preferred; keep the
model formulas above). Notebooks in `analysis/notebooks/`.

## Sample-Size Rationale

| Study level | Size | Yield |
|---|---|---|
| Minimum viable pilot (this sprint) | 12 professors × 4 × 2 seeds = 96 emails | Debug prompts, packets, rubric |
| Strong student project | 24 × 4 × 3 = 288 emails | ~1,400–2,300 claims at 5–8 claims/email |
| Workshop-quality | 36–48 × 4 × 3 = 432–576 emails | Stable mixed-effects estimates, field comparisons |

The bottleneck is the number of *professors* (higher-level units) and annotation
quality, not raw claim count. 15 professors is enough for a pilot but NOT for a strong
main study with interaction estimates.

## Agreement & Evaluator Validation

- Cohen's κ or Krippendorff's α on the double-annotated subset (target: report, and
  discuss anything below 0.6).
- Auto-evaluator (LLM-assisted claim labeling) compared to adjudicated human gold:
  per-label precision/recall/F1 + calibration. Auto labels are usable at scale only if
  validated here.
- Stratify results by visibility band (H5) and field.

## Deliverables

- `analysis/results.csv` — per-email and per-condition metric table
- `analysis/figures/` — frontier plot, condition comparisons, interaction plots, claim-type error profile
- `analysis/notebooks/` — reproducible analysis notebooks (seeded, re-runnable)
