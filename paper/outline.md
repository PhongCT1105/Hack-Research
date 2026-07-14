# Paper Outline

**Working title:** Recipient-Focused Hallucinations in AI-Generated Professor Outreach Emails
**Owner:** Azhdar · Spec: `tasks/04_paper.md` · Target: NLP workshop (factuality / trustworthy NLP / scholarly document processing / human-centered AI)

## Sections

1. **Abstract** — setting, 2×2 design, SER + SPD headline results, trade-off finding.
2. **Introduction** — recipient-focused personalization risk; why outreach emails are a
   distinctive hallucination setting; contributions (evaluation setting + factorial
   comparison + annotation framework).
3. **Related Work** — five buckets (email personalization; personalized-text evaluation;
   scientific claim verification; post-generation correction; grounded academic
   generation). Source: `related_work_matrix.csv`, `docs/research_proposal.md` §5.
4. **Research Questions and Hypotheses** — RQ + H1–H5 from `docs/research_proposal.md`.
5. **Dataset** — sampling frame, evidence packets, provenance, anonymization
   (`docs/dataset_policy.md`).
6. **Experimental Design** — 2×2 conditions, controls, freeze protocol
   (`docs/experimental_design.md`).
7. **Annotation and Metrics** — rubric, blinding, agreement; SER, SPD, frontier
   (`docs/annotation_rubric.md`, `docs/analysis_plan.md`).
8. **Results** — main effects, interaction, B-vs-C comparison, claim-type error profile,
   frontier plot, visibility/field moderation.
9. **Limitations** — from `docs/ethics_and_limitations.md`.
10. **Ethics** — offline design, public data, anonymization, dual-use.
11. **Conclusion.**

**Appendices:** prompts (all versions), config, run-manifest description, annotation
guide, reproducibility checklist.

## Framing guardrails (enforce every draft — see tasks/04_paper.md)

- Contribution = evaluation setting + factorial comparison + annotation framework.
- Never "first ever" for grounding / verification / correction / atomic factuality.
- "Limited work in this application," not "no work."
- Anonymous IDs in every example, figure, table.
