# Research Proposal

**Title:** Recipient-Focused Hallucinations in AI-Generated Professor Outreach Emails

## 1. Problem Statement

Large language models are increasingly used to draft personalized outreach messages,
including emails to faculty members. Personalization in this setting depends on
describing the *recipient's* research — topics, publications, methods, findings, and
scholarly agenda. This creates a distinctive hallucination risk: the model may combine
unrelated papers, inflate tentative results into broad conclusions, attribute work to
the wrong author, or infer a unified research program the publication record does not
support.

This project runs a controlled, **offline** evaluation of AI-generated
professor-outreach emails using public scholarly data. Emails are generated and
evaluated against publication records but **never sent**.

## 2. Research Questions

**Primary:** How do publication grounding during drafting and evidence-based
post-generation verification affect the factual accuracy of research-related claims in
AI-generated outreach emails to professors?

**Secondary:**
- Do these interventions preserve or reduce supported specificity?
- Which claim types are most failure-prone: topics, methods, results, novelty, impact, or cross-paper synthesis?
- Does verification rescue closed-book generation, or mainly suppress risky content?
- Do field and professor visibility moderate error rates?

## 3. Hypotheses

- **H1:** Grounding during writing reduces severe factual errors relative to closed-book generation.
- **H2:** Post-generation verification further reduces severe factual errors, especially when paired with grounding.
- **H3:** Verification without grounding reduces errors but may reduce supported specificity more than grounding alone.
- **H4:** Novelty, impact, and cross-paper synthesis claims have higher error rates than topic claims.
- **H5:** Famous/highly visible professors show smaller closed-book error reductions (models may already know them).

## 4. Contribution

Framed as (all three, and *not* as a brand-new hallucination-mitigation method):

1. A **new evaluation setting/benchmark** for recipient-focused scientific personalization.
2. A **factorial intervention study** comparing evidence-at-write-time vs. evidence-based post-hoc correction.
3. A **claim-type-sensitive annotation framework** with an explicit factuality ↔ supported-specificity trade-off analysis.

### Novelty claims to keep (validated against literature)

| Gap claim | Status |
|---|---|
| Limited work measures factual errors in AI emails describing a professor's research | Strongly supported |
| Email-personalization research optimizes style/engagement, not claim-level truth | Strongly supported |
| Scientific claim-verification work doesn't evaluate naturally generated outreach | Strongly supported |
| Limited comparison of evidence-during-writing vs. evidence-only-during-correction | Partially supported — narrow to this domain |
| Limited work on whether factuality gains reduce useful personalization | Partially supported — say "limited work in this application" |

### Novelty claims to AVOID

- "First work on hallucinations in personalized text" (see *When Personalization Misleads*, 2026)
- "First work on grounded scientific generation" (see AGREE, ScholarCopilot)
- "First work on post-hoc factual correction" (see RARR, FLEEK, SciFix)
- "First atomic factuality evaluation" (see FActScore)

## 5. Prior Work Landscape (summary)

Five buckets of adjacent work — full matrix in `paper/related_work_matrix.csv`:

1. **Email personalization** — Panza (2024); bulk-email field experiments (CSCW 2022). Sender-style and engagement, not recipient factuality.
2. **Personalized-text evaluation** — AuPEL (2023). Personalization/quality/relevance axes; no third-party factual accuracy.
3. **Scientific claim verification** — SciFact (2020), SciFact-Open (2022). Benchmark claims, not generated outreach. Key warning: *abstract-only evidence can support only a special case of a claim*.
4. **Post-generation correction** — RARR (2023), FLEEK (2023), SciFix (2023). Template for our verifier's minimal-edit philosophy.
5. **Grounded academic generation** — AGREE (NAACL 2024), ScholarCopilot (2025). Motivates the grounding-vs-post-hoc comparison.

Conceptually central: *When Personalization Misleads* (2026) validates the
personalization ↔ factuality tension (PFQABench), but in QA — not publication-grounded
outreach about a real third party.

## 6. Known Design Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Treating abstracts as complete answer key | Critical | Abstract-first, passage-escalation policy; full-text snippets for focal papers |
| "Not in packet" conflated with "false" | Critical | Separate `outside_evidence_scope` label; define unsupported relative to the packet |
| Claim-extraction errors corrupt labels | Critical | Automatic extraction is a draft; humans edit claims on validation sample |
| Claims dependent within email / professor | Critical | Mixed-effects models with nested random effects |
| Verifier "wins" by deleting content | Critical | Supported Personalization Density + deletion/rewrite rates |
| OpenAlex author-disambiguation errors | Major | Cross-check faculty page + ORCID + Semantic Scholar/Crossref |
| Fame contamination (model knows professor) | Moderate | Stratify by visibility band; subgroup analysis |
| Same model family writes/checks/grades | Major | Different model families per role |
| Prompt-length confound between conditions | Moderate | Constant instructions/output limit; optional length-matched placebo context |

## 7. Scope

- **Pilot (this sprint):** 12 professors × 4 conditions × 2 seeds = 96 emails; ≥25% claims double-annotated.
- **Strong study (next):** 24 professors × 4 conditions × 3 seeds = 288 emails (~1,400–2,300 claims).
- **Workshop-quality:** 36–48 professors, 432–576 emails.

Target venues: NLP workshops on factuality, trustworthy NLP, scholarly document
processing, or human-centered AI.

## 8. Companion Documents

- `experimental_design.md` — conditions, controls, freeze rule
- `dataset_policy.md` — sampling, evidence packets, provenance, anonymization
- `annotation_rubric.md` — labels, claim types, decision rules, examples
- `analysis_plan.md` — metrics, models, sample-size rationale
- `ethics_and_limitations.md`
- Source documents: `docs/source/*.docx` (original planning docs with full literature citations)
