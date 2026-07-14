# Analysis

Workstream 3 (Kanan). Plan: `docs/analysis_plan.md` · Spec: `tasks/03_annotation.md`.

| Artifact | Content |
|---|---|
| `results.csv` | Per-email and per-condition metrics (SER, SPD, overstatement rate, deletion/rewrite rates, …) |
| `figures/` | Supported Specificity Frontier (headline), condition comparisons, interaction plots, claim-type error profile |
| `notebooks/` | Reproducible notebooks: 01_metrics, 02_mixed_models, 03_figures (create as needed) |

Rules:
- Claims are nested in emails, emails in professors — mixed-effects models only, no flat t-tests.
- `subjective_or_generic` and `outside_evidence_scope` are excluded from the factual
  denominator and reported separately.
- Every notebook must be re-runnable top-to-bottom from committed inputs.
- Anonymous professor IDs only.
