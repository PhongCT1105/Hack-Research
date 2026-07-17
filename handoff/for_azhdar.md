# For Azhdar — Results + everything to fill the empty sections

The full run is done and in the repo (`analysis/results.csv`, `analysis/figures/`). Below is
what you need to finish the paper: the numbers, the figures, ready-to-adapt prose for the
empty sections, and filled Declarations + References. Adapt the wording to your voice.

> Honesty note to weave in: the labels are from an **automatic evaluator** (an LLM judge),
> not humans yet. Kanan is validating a subset (kappa). Frame results as auto-evaluated,
> pending human validation. Do NOT present the exact 0.00s as if human-confirmed.

## The results (from analysis/results.csv — 96 emails, 360 claims, 12 professors)

| Condition | n factual claims | Severe Error Rate (SER) | 95% CI | Supported Personalization Density (SPD) | Email-level ≥1 severe |
|-----------|------------------|-------------------------|--------|------------------------------------------|-----------------------|
| A (closed-book) | 61 | **0.344** | [0.174, 0.545] | 0.65 | 45.5% |
| B (grounded) | 90 | **0.000** | [0.000, 0.000] | 1.71 | 0% |
| C (verify-only) | 50 | **0.020** | [0.000, 0.063] | 1.04 | 4.2% |
| D (grounded+verified) | 87 | **0.000** | [0.000, 0.000] | 1.76 | 0% |

Verifier behaviour: C deletion rate 0.55 / rewrite 0.29; D deletion 0.25 / rewrite 0.25
(D edits less — grounded drafts need less correction).
Machine-label distribution over 360 claims: supported 246, outside-scope 62, unsupported 21,
partially-supported 20, subjective/generic 10, contradicted 1.

**Figures (already rendered, cite these):**
- `analysis/figures/ser_by_condition.png` → **Figure 1** (SER by condition, 95% CI).
- `analysis/figures/frontier.png` → **Figure 2** (Supported-Specificity Frontier; A bottom-right, B/D top-left).

## §4 Results — ready prose (findings only, no interpretation)

> We generated 96 emails (12 professors × 4 conditions × 2 seeds) yielding 360 atomic
> research claims, each labelled by the automatic evaluator against its evidence packet.
> Table 3 reports per-condition metrics. The closed-book baseline (A) had a Severe Error
> Rate of 0.34 (95% CI 0.17–0.55), with at least one severe error in 45.5% of emails.
> Providing evidence to the writer (B) reduced the Severe Error Rate to 0.00 and raised
> Supported Personalization Density from 0.65 to 1.71 claims per 100 words. Verification of
> ungrounded drafts (C) reduced the Severe Error Rate to 0.02 with an SPD of 1.04, while its
> verifier deleted 55% and rewrote 29% of edited claims. The combined condition (D) matched
> B on factuality (SER 0.00) at the highest specificity (SPD 1.76), with a lower verifier
> deletion rate (0.25). Figure 1 shows Severe Error Rate by condition; Figure 2 plots each
> condition on the Supported-Specificity Frontier.

(Add Table 3 = the table above. Keep interpretation OUT of Results.)

## §5 Discussion — beats to expand

- **Main finding:** grounding at write time (B) eliminated severe errors *and* doubled
  supported specificity — factuality and usefulness improved together, not in tension.
- **B vs C (the key comparison):** grounding beat correction-after on both axes (B: SER 0.00,
  SPD 1.71 vs C: SER 0.02, SPD 1.04). Evidence is more valuable during writing than as repair.
- **Trade-off:** C's higher deletion rate (0.55) shows correction-after buys factuality partly
  by removing content; grounding avoids that.
- **Limitations (be explicit):** (1) labels are from an LLM auto-evaluator, not human — the
  judge leaned generous (68% supported); exact 0.00s are auto-evaluated and validated on a
  human subset (report Kanan's kappa here). (2) Single writer model (gpt-4o-mini). (3) Small
  provisional sample; evidence packets use abstracts + abstract-excerpt passages, so SER is a
  conservative upper bound. (4) One judge family. Future work: human labels at scale,
  cross-model writers, full-text evidence.

## §6 Conclusion — one tight paragraph
> In this offline benchmark, giving an AI writer verified publication evidence removed severe
> misrepresentation of professors' research while making outreach emails more specific, and it
> outperformed post-hoc verification. Grounding, not just correction, is the more effective
> safeguard for recipient-focused academic outreach. Human-label validation and larger,
> verified samples are the next step.

## Abstract — fill the two gaps
- **Results:** "Across 96 emails and 360 claims, the closed-book baseline had a 0.34 severe
  error rate (≥1 severe error in 45% of emails); providing evidence during writing reduced it
  to 0.00 while doubling supported specificity, and outperformed post-generation verification."
- **Conclusion (rewrite the future-tense one):** "Grounding during drafting reduced research
  misrepresentation without sacrificing useful personalisation, and was more effective than
  correction after generation."

## Declarations — fill these
- **Funding:** This research did not receive any specific grant from funding agencies in the
  public, commercial, or not-for-profit sectors.
- **Conflicts of Interest:** The authors declare no competing financial interests or personal
  relationships that could have influenced this work.
- **Ethics Statement:** Ethics approval was not required because the study used only publicly
  available scholarly metadata (OpenAlex) and did not involve human participants, private
  identifiable data, or animal subjects. No emails were sent to any individual. Professors are
  referred to by anonymised IDs (e.g., CS-01).
- **Data Availability:** Code, generated emails, labels, and figures are at
  https://github.com/PhongCT1105/Hack-Research . Professor identities are anonymised; the
  identity map is withheld.
- **AI Use Statement:** The authors used Anthropic Claude (via Claude Code) and OpenAI Codex
  to help implement and test the evaluation pipeline. All AI-generated code was reviewed and
  verified by the authors, who take full responsibility. Note that LLMs were also the object
  of study: the writer (OpenAI gpt-4o-mini), verifier (Anthropic claude-haiku-4.5), and
  automatic evaluator/claim extractor (Anthropic claude-3-haiku) are named in the Methods.
- **Author Contributions:** Abhinav Singh — pipeline, evaluation infrastructure, analysis;
  Phong Cao — dataset and evidence packets; Kanan — annotation framework and human validation;
  Azhdar Mammadov — related work and manuscript. All authors reviewed the final manuscript.

## References — Vancouver (verify author lists/venues before submit; arXiv IDs are anchors)
1. Nicolae et al. Panza: A personal email assistant. arXiv:2407.10994. 2024.
2. Wang et al. Automated evaluation of personalized text generation using large language models (AuPEL). arXiv:2310.11593. 2023.
3. Organisational bulk-email personalisation field experiment. arXiv:2302.11156. 2023.
4. When personalization misleads: hallucinations in personalized LLMs (PFQABench). arXiv:2601.11000. 2026.
5. Min S, et al. FActScore: fine-grained atomic evaluation of factual precision. arXiv:2305.14251. 2023.
6. Wadden D, et al. Fact or fiction: verifying scientific claims (SciFact). arXiv:2004.14974. 2020.
7. Wadden D, et al. SciFact-Open. arXiv:2210.13777. 2022.
8. Gao L, et al. RARR: researching and revising what language models say. arXiv:2210.08726. 2023.
9. Bayat et al. FLEEK: factual error detection and correction. arXiv:2310.17119. 2023.
10. SciFix: scientific factual error correction. arXiv:2305.14707. 2023.
11. AGREE: adaptation for grounding and citation generation. arXiv:2311.09533. 2024.
12. ScholarCopilot: academic writing with accurate citations. arXiv:2504.00824. 2025.

Add OpenAlex if you cite the data source: Priem J, Piwowar H, Orr R. OpenAlex. arXiv:2205.01833. 2022.
