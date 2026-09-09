# Revision statistics — NSRI-J-2026-0178

All figures regenerated from `annotations/` and `outputs/full.jsonl`.
Exact intervals are Clopper-Pearson; the cluster bootstrap resamples
whole emails. Zero-event conditions have no informative bootstrap
interval, which is why exact bounds are the primary report.

## Table 3 — per-condition (automatic pilot labels)

| Cond | emails | emails w/ >=1 factual claim | factual claims | severe | SER | 95% CI (exact) | SPD | emails w/ >=1 severe | 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| A | 24 | 22 | 61 | 21 | 0.344 | 0.227–0.477 | 0.65 | 10/22 (0.455) | 0.244–0.678 |
| B | 24 | 24 | 90 | 0 | 0.000 | 0.000–0.040 | 1.71 | 0/24 (0.000) | 0.000–0.142 |
| C | 24 | 24 | 50 | 1 | 0.020 | 0.001–0.106 | 1.04 | 1/24 (0.042) | 0.001–0.211 |
| D | 24 | 24 | 87 | 0 | 0.000 | 0.000–0.042 | 1.76 | 0/24 (0.000) | 0.000–0.142 |

## Per-condition SER under each automatic evaluator

| Evaluator | Cond | factual claims | severe | SER | 95% CI |
|---|---|---|---|---|---|
| primary_claude-3-haiku | A | 61 | 21 | 0.344 | 0.227–0.477 |
| primary_claude-3-haiku | B | 90 | 0 | 0.000 | 0.000–0.040 |
| primary_claude-3-haiku | C | 50 | 1 | 0.020 | 0.001–0.106 |
| primary_claude-3-haiku | D | 87 | 0 | 0.000 | 0.000–0.042 |
| second_gemini-2.5-flash-lite | A | 77 | 35 | 0.455 | 0.341–0.572 |
| second_gemini-2.5-flash-lite | B | 94 | 10 | 0.106 | 0.052–0.187 |
| second_gemini-2.5-flash-lite | C | 54 | 11 | 0.204 | 0.106–0.335 |
| second_gemini-2.5-flash-lite | D | 90 | 4 | 0.044 | 0.012–0.110 |

- worst condition under both evaluators: A / A
- B < C (the study's key comparison) under primary: True; under second: True
- second evaluator also finds zero in B and D: False

## Reliability

| Comparison | n | raw agreement | kappa | 95% CI | Landis-Koch |
|---|---|---|---|---|---|
| primary (claude-3-haiku) vs human | 36 | 0.556 | 0.326 | 0.156–0.495 | fair |
| primary vs second evaluator (gemini-2.5-flash-lite) | 360 | 0.725 | 0.504 | 0.439–0.570 | moderate |
| second evaluator vs human | 36 | 0.694 | 0.542 | 0.348–0.735 | moderate |

## Direction of human/machine disagreement

- claims compared: 36
- agree: 20
- machine too lenient: 14
- machine too strict: 0
- orthogonal (both non-severe, different label): 2
- severe claims the judge moved into 'outside evidence scope' (i.e. out of the SER denominator): 7
- human 'subjective/generic' claims the judge called 'supported' (inflates SPD): 6
- precision of machine 'supported' against human: 0.667 (95% CI 0.468–0.828)
- 'overstated' ever emitted by primary evaluator: False
- 'overstated' ever emitted by second evaluator: False
- 'overstated' used by human annotator: 1 claims

## Human-subset coverage per condition

| Cond | human claims | factual | severe | emails | human SER | 95% CI |
|---|---|---|---|---|---|---|
| A | 16 | 11 | 7 | 6 | 0.636 | 0.308–0.891 |
| B | 10 | 10 | 0 | 4 | 0.000 | 0.000–0.308 |
| C | 7 | 3 | 0 | 3 | 0.000 | 0.000–0.708 |
| D | 3 | 3 | 0 | 1 | 0.000 | 0.000–0.708 |

## Field heterogeneity

| Field | A | B | C | D |
|---|---|---|---|---|
| biomedicine | 1/19 = 0.05 | 0/27 = 0.00 | 0/15 = 0.00 | 0/30 = 0.00 |
| computer science | 3/23 = 0.13 | 0/33 = 0.00 | 1/20 = 0.05 | 0/26 = 0.00 |
| psychology | 17/19 = 0.89 | 0/30 = 0.00 | 0/15 = 0.00 | 0/31 = 0.00 |

Leave-one-field-out for condition A:
- [A excluding psychology]: 4/42 = 0.095 (95% CI 0.027–0.226)
- [A excluding computer science]: 18/38 = 0.474 (95% CI 0.310–0.642)
- [A excluding biomedicine]: 20/42 = 0.476 (95% CI 0.320–0.636)

## Verifier edit behaviour

| Cond | decisions | delete | soften/rewrite | keep | deletion rate | 95% CI |
|---|---|---|---|---|---|---|
| C | 49 | 27 | 14 | 8 | 0.551 | 0.402–0.693 |
| D | 56 | 14 | 14 | 28 | 0.250 | 0.144–0.384 |

Fisher exact test, C vs D deletion rate: p = 0.0025
