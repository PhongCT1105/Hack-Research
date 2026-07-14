# Workstream 4 — Related Work & Paper

**Owner:** Azhdar (also second blinded annotator for Workstream 3)
**Depends on:** nothing for skeleton/related work; results from Workstream 3 for §8.

## Objective

A complete paper draft with a defensible related-work positioning, correct gap framing,
and integrated results — plus the shared bibliography and related-work matrix.

## Inputs

- `docs/research_proposal.md` (gap claims, contribution framing, prior-work landscape)
- `paper/related_work_matrix.csv` (pre-seeded with the 10 core papers)
- `docs/ethics_and_limitations.md`
- `analysis/results.csv` + `analysis/figures/` (when ready)

## Outputs (file contract)

| File | Content |
|---|---|
| `paper/main.tex` (+ template files) | Full draft |
| `paper/references.bib` | Shared bibliography |
| `paper/related_work_matrix.csv` | Completed matrix (10+ papers) |
| `paper/figures/` | Final figure exports |

## Paper Structure (fixed)

1. Abstract · 2. Introduction · 3. Related Work · 4. Research Questions & Hypotheses ·
5. Dataset · 6. Experimental Design · 7. Annotation & Metrics · 8. Results ·
9. Limitations · 10. Ethics · 11. Conclusion

## Steps

1. **Now:** set up LaTeX template (ACL-style two-column recommended) + `references.bib`
   with the 10 essential papers (list below); create the full section skeleton.
2. **Related-work matrix:** complete columns
   `Paper | Task | Dataset | Method | Metrics | Findings | Overlap with us | Remaining gap`
   for at least the 10 core papers.
3. **Draft early sections** (no dependencies): Introduction, Related Work, Research Gap,
   Ethics, Limitations — sourcing gap claims from `docs/research_proposal.md` §4.
4. **Integrate as delivered:** Dataset (from Workstream 1 policy + manifest),
   Experimental Design (from `docs/experimental_design.md`), Annotation & Metrics (from
   rubric + analysis plan), Results (from Workstream 3).
5. **Final pass:** reproducibility appendix (prompts, config, manifest description),
   anonymization check on every example/figure/table.

## Framing Rules (from the proposal — enforce in every draft)

- Contribution = recipient-focused factuality **evaluation setting** + factorial
  intervention comparison + claim-type annotation framework.
- NEVER claim grounding, verification, post-hoc correction, or atomic factuality
  evaluation is new — cite RARR/FLEEK/SciFix/AGREE/FActScore instead.
- Say "limited work in this application," not "no work."
- Every research-gap sentence must have literature support (matrix row or citation).

## The 10 Essential Papers (seed `references.bib` with these)

1. FActScore (EMNLP 2023) — atomic-claim decomposition, arXiv:2305.14251
2. SciFact: Fact or Fiction (2020) — scientific claim verification, arXiv:2004.14974
3. SciFact-Open (Findings EMNLP 2022) — abstract-only evidence pitfalls, arXiv:2210.13777
4. RARR (ACL 2023) — post-hoc research & minimal revision, arXiv:2210.08726
5. AGREE: LLM Adaptation for Grounding & Citation (NAACL 2024) — arXiv:2311.09533
6. SciFix (2023) — scientific factual error correction, arXiv:2305.14707
7. AuPEL (2023) — automated personalized-text evaluation, arXiv:2310.11593
8. When Personalization Misleads (2026) — PFQABench, arXiv:2601.11000
9. Panza (2024) — local personalized email assistant, arXiv:2407.10994
10. ScholarCopilot (2025) — citation-grounded academic writing, arXiv:2504.00824

Also useful: FLEEK (EMNLP 2023 demo, arXiv:2310.17119); OpenAlex (arXiv:2205.01833);
authorship-disambiguation anomalies (arXiv:2412.18757); bulk-email field experiment
(arXiv:2302.11156).

## Completion Criteria

- [ ] Every research-gap claim supported by literature
- [ ] No "entirely new" claims about grounding/verification
- [ ] Contribution framed as recipient-focused factuality evaluation
- [ ] All examples, figures, tables use anonymous professor IDs
- [ ] Reproducibility appendix complete (prompts, config, run manifest description)
