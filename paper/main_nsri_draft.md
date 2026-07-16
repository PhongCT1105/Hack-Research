<!--
NSRI-format paper skeleton — STARTER for Azhdar (Workstream 4).
Mapped to NSRI_Research_paper_Format.pdf: 5 main sections + Declarations.
Pre-filled where the content is already known (Methods, Declarations, References);
[FILL] marks what needs the pilot results or your prose. Delete all gray/HTML comments
and every [FILL]/[DRAFT] marker before submission.

RULES (enforce everywhere):
- Anonymous IDs only (CS-01, PSY-01) in every example/table/figure — never a real name.
- Never claim grounding / verification / atomic factuality is "new" — cite prior work.
- Say "limited work in this application," not "no work."
- Results section states findings only; meaning goes in Discussion.
- Target 3,000–5,000 words (excludes abstract, refs, tables, figures). Aim ~4,200.
-->

**Article type:** Original Research

# Recipient-Focused Hallucinations in AI-Generated Professor Outreach Emails: A Factorial Study of Grounding and Verification

**Authors:** Abhinav Singh¹*, [Azhdar Mammadov]¹, [Kanan …]¹, [Phong Cao]¹†
_(first + senior author fixed; middle authors alphabetical by last name — confirm order)_

**ORCID iDs:** [each author: register free at orcid.org and paste here]

**Affiliations:** ¹ [Division, Organization, City, Country]
\* Equal contribution. † Corresponding author: [name, email — optional]

---

## Abstract
_(Structured, ≤250 words. No citations/figures.)_

**Background.** AI writing tools increasingly draft personalized academic outreach that *describes a recipient's research*. Misdescribing a real scholar's work — inventing findings, overstating impact, or misattributing methods — is a distinctive and under-measured harm. [1–2 sentences on why this matters and the gap.]

**Methods.** We ran an offline benchmark (no email is ever sent). For each professor we built a verified evidence packet from OpenAlex. Emails were generated under a 2×2 factorial design crossing *grounding* (evidence given to the writer) with *verification* (an evidence-based correction pass after writing), yielding four conditions (A–D). Every email was decomposed into atomic claims about the professor's research and labeled against the packet; a subset was human-validated.

**Results.** [FILL after pilot — SER by condition; the B-vs-C comparison; the factuality–specificity trade-off; agreement statistics.]

**Conclusion.** [FILL — one sentence: what grounding vs. verification each buys, and the trade-off caveat.]

**Keywords:** large language models; hallucination; factuality evaluation; retrieval grounding; scientific claim verification; personalized text generation; research integrity

---

# 02 / Main Manuscript

## 1. Introduction
_(~700 words. Arc: broad problem → what's known → the gap → objective + RQ/hypotheses.)_

[DRAFT — Azhdar to write prose. Hit these beats:]
- **Broad problem:** LLM outreach/synthesis tools now generate factual statements about real scientists' work at scale (name the deployed setting — cold outreach, lab-research summaries).
- **What's known:** five prior-work buckets — email personalization [Panza], personalized-text evaluation [AuPEL], scientific claim verification [SciFact, SciFact-Open], post-hoc correction [RARR, FLEEK, SciFix], grounded academic generation [AGREE, ScholarCopilot]. Personalization can itself distort facts [PFQABench].
- **The gap:** *limited work in this application* — recipient-focused, claim-level factuality of publication-grounded outreach, with a factorial grounding-vs-verification comparison and a factuality-vs-specificity analysis. (Do NOT say "first to study grounding/verification.")
- **Objective + contributions:** a recipient-focused evaluation setting + factorial intervention comparison + claim-type annotation framework.
- **End the section** with the research question and hypotheses H1–H5 (source: `docs/research_proposal.md`). One tight paragraph — NSRI has no separate hypotheses section.

## 2. Methods
_(~1,300 words — the heavy section. Merges our old Dataset + Design + Annotation sections. Use bold inline sub-headers, not numbered subsections. Sources cited inline below.)_

**Study design.** Offline, benchmark-style; generated emails are never sent. One independent manipulation with two factors — evidence to the writer (grounding) and a post-generation evidence-based verification pass — giving four conditions:

| Condition | Writer gets evidence | Verification after | Purpose |
|-----------|----------------------|--------------------|---------|
| A | No | No | Closed-book baseline (audit target) |
| B | Yes | No | Effect of grounding at writing time |
| C | No | Yes | Effect of correction after ungrounded writing |
| D | Yes | Yes | Combined safeguards |

_(This is Table 1. The single most informative comparison is B vs C.)_ Source: `docs/experimental_design.md`.

**Data and evidence packets.** Professors sampled across three fields (CS/AI, Psychology/CogSci, Biomedicine/Public Health), mid-visibility only (superstars excluded to avoid the model already "knowing" famous researchers from pretraining — state this as a deliberate control). Each professor's evidence packet = an official research summary + representative papers (title, year, venue, authors, DOI, abstract) + selected passages, all from OpenAlex with provenance. Abstracts are reconstructed from OpenAlex's inverted index and markup-normalized. Only public scholarly metadata is used. Source: `docs/dataset_policy.md`.

**Generation pipeline.** One fixed writer prompt is used in all conditions; the *only* difference is whether the evidence block is present. Model, temperature, output-length limit, and instructions are held constant across conditions. The verifier (conditions C/D) follows a minimal-edit philosophy (in the spirit of RARR/FLEEK): it extracts atomic claims, checks each against the packet, keeps supported content, softens overstatements, and removes/generalizes unsupported or contradicted content. Different model families are used for writing vs. verification/judging to avoid shared blind spots. Every run is logged (model, provider, prompt version, seed, temperature). Source: `docs/experimental_design.md`.

**Annotation and metrics.** Each email is decomposed into atomic research claims and each claim gets one label: *supported, partially supported, overstated, unsupported, contradicted, outside evidence scope,* or *subjective/generic.* Annotators are blinded to condition and to whether text is original or verified. Primary metrics: **Severe Error Rate (SER)** = (unsupported + contradicted) / judged factual claims; and **Supported Personalization Density (SPD)** = supported research-specific claims per 100 words (guards against the verifier "winning" by deleting specificity). We also plot the **Supported-Specificity Frontier** (SER vs. SPD). Auto-labels are validated against a human-adjudicated subset. Source: `docs/annotation_rubric.md`, `docs/analysis_plan.md`.

**Statistical analysis.** Claims are nested within emails within professors, so we use mixed-effects models (logistic for claim-level severe error, with grounding × verification interaction, field and visibility as fixed effects, and professor/email random effects) rather than flat tests. We report estimated marginal means, confidence intervals, and interaction plots. Source: `docs/analysis_plan.md`.

_(NSRI note: this study involves no wet-lab, clinical, or human-subject-recruitment work — it fits NSRI's scope. State this once.)_

## 3. Results
_(~850 words. Findings only — no interpretation. Every table/figure numbered in cite order and mentioned in text.)_

[FILL after pilot:]
- Headline: SER by condition with 95% CIs (**Figure 1**).
- The B-vs-C comparison (grounding-at-write vs. correction-after).
- Claim-type error profile — which claim types fail most (novelty, impact, synthesis?).
- **Figure 2:** Supported-Specificity Frontier.
- **Table 2:** agreement — human–human and auto-vs-human κ.
- Moderation by professor visibility (H5) and field.

## 4. Discussion
_(~1,000 words. Interpretation. Limitations live HERE, not as a separate section.)_

[DRAFT — after results. Structure:]
- Lead with the single most important finding (likely: what grounding vs. verification each buys, and whether verification only reduces errors by stripping specificity — the trade-off).
- Connect to prior work (does the applied setting confirm/extend RARR/AGREE?).
- **Strengths:** pre-registered hypotheses, human-validated auto-labels, factorial isolation.
- **Limitations (one paragraph):** abstracts ⊂ full papers → SER is a conservative upper bound; single-generator/model caveat; LLM-judge fallibility (mitigated by the human κ subset); small N; English-only; three fields.
- **Future work:** cross-model, larger N, full-text evidence.

## 5. Conclusion
_(~200 words. Central takeaway, why it matters for research integrity in AI-assisted academia, the most important next step. No new information.)_

[FILL]

---

# 03 / Declarations

**Abbreviations.** LLM — large language model; SER — Severe Error Rate; SPD — Supported Personalization Density; RAG — retrieval-augmented generation; κ — Cohen's kappa.

**Funding.** This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.

**Conflicts of Interest.** The authors declare no competing financial interests or personal relationships that could have influenced the work reported in this paper.

**Ethics Statement.** Ethics approval was not required because the study used only publicly available scholarly metadata and did not involve human participants, private identifiable data, or animal subjects. No emails were sent to any individual. Because ungrounded model outputs can contain fabricated claims about real researchers, all professors are referred to by anonymized IDs (e.g., CS-01) throughout; the identity map is withheld to protect individuals.

**Data Availability.** All code, generated emails, annotation labels, and figures are available at [GitHub repository URL]. Professor identities are anonymized and the identity map is not released.

**AI Use Statement.** [CONFIRM EXACT TOOL LIST WITH THE TEAM BEFORE SUBMISSION.] The authors used Anthropic Claude (via Claude Code) and OpenAI Codex to assist with implementing and testing the evaluation pipeline [and, if applicable, drafting/editing the manuscript]. All AI-generated code and text were reviewed, edited, and verified by the authors, who take full responsibility for the accuracy and integrity of the manuscript. Note that large language models were also the *object of study*: the specific models used as experimental subjects (writer, verifier, and automatic evaluator) are named in the Methods.

**Author Contributions.** [Adjust to reality.] Abhinav Singh — generation/verification pipeline, evaluation infrastructure, testing. [Phong Cao] — dataset construction and evidence packets. [Kanan] — annotation framework and analysis. [Azhdar Mammadov] — related work and manuscript. All authors reviewed the final manuscript.

**Acknowledgements.** [Optional — mentors/advisors; delete if none.]

---

# 04 / References
_(Vancouver numbered, in order of first appearance. Superscript numbers in text after punctuation. VERIFY final venue/year/authors before submission — arXiv IDs given as anchors.)_

1. Min S, Krishna K, Lyu X, et al. FActScore: Fine-grained atomic evaluation of factual precision in long-form text generation. arXiv preprint arXiv:2305.14251. 2023.
2. Wadden D, Lin S, Lo K, et al. Fact or fiction: Verifying scientific claims. arXiv preprint arXiv:2004.14974. 2020.
3. Wadden D, Lo K, Kuehl B, et al. SciFact-Open: Towards open-domain scientific claim verification. arXiv preprint arXiv:2210.13777. 2022.
4. Gao L, Dai Z, Pasupat P, et al. RARR: Researching and revising what language models say, using language models. arXiv preprint arXiv:2210.08726. 2023.
5. [AGREE] Effective large language model adaptation for improved grounding and citation generation. arXiv preprint arXiv:2311.09533. 2024.
6. [SciFix] Outperforming GPT-3 on scientific factual error correction. arXiv preprint arXiv:2305.14707. 2023.
7. [AuPEL] Automated evaluation of personalized text generation using large language models. arXiv preprint arXiv:2310.11593. 2023.
8. [PFQABench] When personalization misleads: Understanding and mitigating hallucinations in personalized LLMs. arXiv preprint arXiv:2601.11000. 2026.
9. [Panza] Design and analysis of a fully-local personalized text writing assistant. arXiv preprint arXiv:2407.10994. 2024.
10. [ScholarCopilot] Training large language models for academic writing with accurate citations. arXiv preprint arXiv:2504.00824. 2025.
11. Priem J, Piwowar H, Orr R. OpenAlex: A fully-open index of scholarly works, authors, venues, institutions, and concepts. arXiv preprint arXiv:2205.01833. 2022.

---

# 05 / Supplementary Material

Reproducibility appendix (upload separately, cite as Supplementary File 1): prompt versions (writer/verifier/extractor), run configuration, run-manifest description, annotation guide. Label items Table S1, Figure S1, etc.

<!-- FINAL SUBMISSION CHECK
[ ] Article type selected; instructional/gray text + [FILL]/[DRAFT] markers removed
[ ] Author names, affiliations, ORCID iDs, corresponding author verified
[ ] Ethics, funding, conflicts, data-availability, AI-use statements complete
[ ] Every table and figure cited in the text
[ ] References in Vancouver numbered style; venues verified
[ ] Only anonymous IDs in every example/table/figure
[ ] Word count 3,000–5,000 (excl. abstract/refs/tables/figures)
[ ] Supplementary files labeled + uploaded separately
-->
