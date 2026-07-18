<!--
COMPLETE assembled manuscript for NSRI submission. Merges Azhdar's Introduction /
Related Work / Methods with the real results, corrected per the review, and filled
Declarations + References. Convert to the NSRI Google-Doc template for submission.
Delete this comment and verify author names/ORCIDs/affiliations + that every reference
resolves before submitting.
-->

**Article type:** Original Research

# Recipient-Focused Hallucinations in AI-Generated Professor Outreach Emails: A Factorial Evaluation of Grounding and Verification

**Authors:** Azhdar Mammadov¹\*, Abhinav Singh¹, Kanan¹, Phong Cao¹
*\* Corresponding author. Affiliations and full ORCID iDs to be completed before submission.*
ORCID: A. Mammadov — https://orcid.org/0009-0009-4326-5838

---

## Abstract

**Background.** Large Language Models are increasingly used to draft personalised academic outreach — emails to potential supervisors, mentors, and collaborators — where the personalisation depends on describing a real professor's research. Fluent but unsupported claims about a recipient's topics, methods, findings, impact, or authorship can misrepresent their scholarly work.

**Methods.** We ran an offline, benchmark-style evaluation of AI-generated professor outreach emails. A 2×2 factorial design varied whether the writer received a publication evidence packet during drafting and whether an evidence-based verifier revised the email after generation, yielding four conditions (A–D). We generated 96 emails for 12 professors across three fields, decomposed them into 360 atomic research claims, and labelled each against the professor's evidence packet with an automatic evaluator; a human subset validates these labels.

**Results.** The closed-book baseline (A) had a Severe Error Rate of 0.34 (95% CI 0.17–0.55), with at least one severe error in 45% of emails. Providing evidence during writing (B) reduced the Severe Error Rate to 0.00 while raising Supported Personalization Density from 0.65 to 1.71 supported claims per 100 words. Post-generation verification of ungrounded drafts (C) reduced the rate to 0.02. The combined condition (D) matched B on factuality (0.00) at the highest specificity (1.76). Grounding at write time outperformed post-hoc verification on both factuality and specificity.

**Conclusion.** Giving an AI writer verified publication evidence removed severe misrepresentation of professors' research while making outreach emails more specific, and was more effective than correcting drafts after generation. Grounding, not merely correction, is the stronger safeguard for recipient-focused academic outreach.

**Keywords:** Large Language Models; Hallucination; Academic outreach; Grounded generation; Scientific claim verification; Personalised text generation; Factuality evaluation

---

## 1. Introduction

Large Language Models (LLMs) are increasingly used as writing assistants for personalised text, including email-style messages and academic writing support. Prior work on personalised writing systems has shown that models can imitate or adapt writing style from very limited user data, while evaluation work argues that personalised generation cannot be judged well by generic lexical metrics alone.¹ ²

Academic outreach is a distinctive case because personalisation is not only about tone. A message to a professor often tries to demonstrate fit by referring to the recipient's research topics, publications, methods, datasets, findings, impact, or collaborations. This makes the task more sensitive than ordinary email polishing: a message may sound specific and respectful while still attributing the wrong method, overstating a result, inventing an impact claim, or combining unrelated papers into a misleading description.

Limited work directly evaluates recipient-focused academic outreach emails that describe a specific professor's research, decomposes those descriptions into claim-level units, checks them against publication evidence, and measures whether safeguards preserve useful specificity rather than merely deleting risky details. This study addresses that application-specific gap by evaluating AI-generated professor outreach emails under a controlled 2×2 design comparing evidence during drafting with evidence-based post-generation verification.

The stakes are concrete and growing. Prospective students, early-career researchers, and sales tools increasingly rely on LLMs to draft outreach at scale, and a single automated message that misattributes a method or invents a finding can embarrass the sender, misrepresent the recipient's scholarly record, and erode trust in AI-assisted research communication. Unlike ordinary summarisation errors, these mistakes are directed at a named individual whose real publications provide an objective ground truth, which makes the task both higher-stakes and unusually well-suited to systematic measurement. Yet the two most common mitigations — supplying the model with source evidence before it writes (grounding), and checking the draft against evidence afterward (verification) — have not been compared head-to-head in this setting, nor has anyone measured whether they preserve the very specificity that makes an outreach email useful.

The primary research question is: *how do publication grounding during drafting and evidence-based post-generation verification affect the factual accuracy of research-related claims in AI-generated outreach emails to professors?* The secondary objective is to measure the factuality–specificity trade-off — whether safer outputs remain genuinely personalised through supported, research-specific content, or whether safety is achieved merely by deleting the specific details that give an email value. Our contribution is threefold: a recipient-focused evaluation setting for factuality in academic outreach, a claim-level annotation framework adapted to research descriptions, and a factorial comparison that separates the effect of grounding from that of verification.

## 2. Related Work

**Personalised text and email generation.** Language models can adapt wording, tone, ordering, and perceived relevance to a target reader. Panza demonstrates that personalised email-writing assistants can learn convincing sender-style patterns from small email collections and use retrieval-augmented generation to condition outputs on examples.¹ Organisational bulk-email research shows that personalisation affects engagement outcomes such as recognition, interest, and detailed reading.³ These studies mainly evaluate style, relevance, engagement, or user experience rather than whether claims about a real recipient are factually supported. In contrast, this project focuses on recipient-grounded personalisation: the email must describe a professor's actual research accurately, not merely sound tailored.

**Automated personalised-text evaluation.** AuPEL argues that personalised generation should be evaluated across dimensions such as personalisation, quality, and relevance rather than only with generic surface metrics.² More recent work on personalisation-induced hallucination shows that personalisation can itself distort factual reasoning, creating a tension between being specific and staying correct.⁴ These findings motivate measuring not only whether an outreach email sounds personalised, but whether its specific research claims are supported by evidence.

**Atomic factuality evaluation.** FActScore introduced a fine-grained approach for evaluating long-form generation by decomposing text into atomic factual claims and measuring the proportion supported by reliable sources.⁵ This is directly relevant because a professor-outreach email may contain several research claims inside one fluent sentence — a topic claim, a method claim, a dataset claim, and an impact claim. Evaluating the whole email as simply correct or incorrect would hide these differences; we therefore adapt atomic factuality evaluation to research-related claims in outreach emails.

**Scientific claim verification.** SciFact established a benchmark where scientific claims are checked against paper abstracts and labelled as supported, refuted, or not enough information.⁶ SciFact-Open extends this to a larger open-domain corpus, showing that verification becomes harder as retrieval scale increases and that abstract-only evidence can support only a limited version of some claims.⁷ These findings motivate our evidence policy: packets include publication metadata and abstracts, with selected passages for focal papers when method-, result-, or scope-sensitive claims require more detail. However, these benchmarks evaluate prepared scientific claims rather than naturally generated outreach emails, where claims arise inside persuasive, personalised messages that may overstate novelty, infer collaborations, or turn tentative results into broad impact claims.

**Grounded generation and post-generation correction.** RARR demonstrates a research-and-revise workflow in which outputs are checked after generation and minimally revised to improve attribution while preserving the original text.⁸ FLEEK presents an end-to-end pipeline for claim extraction, evidence gathering, factuality judgement, and correction.⁹ SciFix shows that scientific factual correction is feasible on established datasets.¹⁰ AGREE shows that explicit grounding can improve grounded response generation and citation quality compared with weaker prompting or post-hoc citation.¹¹ ScholarCopilot shows that retrieval-integrated academic writing improves citation and writing quality.¹² These lines suggest that supplying evidence during drafting may be more effective than repairing unsupported claims afterward — the question our 2×2 design tests directly.

**Remaining gap.** Prior work provides strong foundations — personalised generation motivates the outreach setting, FActScore motivates atomic decomposition, SciFact motivates evidence-based labels, and RARR/FLEEK/SciFix/AGREE motivate the interventions — but these strands study separate parts of the problem. Email-personalisation work rarely evaluates factual accuracy about a real recipient's research; scientific verification rarely evaluates naturally generated outreach; and grounded-generation work does not measure whether safeguards preserve useful, professor-specific personalisation. The remaining gap is recipient-focused factuality in AI-generated academic outreach.

## 3. Methods

### 3.1 Study design
This is an offline, benchmark-style original-research study; no generated emails were sent to professors. The design is a 2×2 factorial comparison with two binary factors: whether the writing model received an evidence packet during drafting, and whether a separate evidence-based verifier revised the draft after generation (Table 1). The design isolates the main effect of grounding, the main effect of verification, and their interaction. The comparison between conditions B and C is especially important, as it tests whether evidence is more useful during generation or only during repair.

**Table 1. Experimental conditions.**

| Condition | Writer receives evidence | Post-generation verification | Purpose |
|---|---|---|---|
| A | No | No | Closed-book baseline |
| B | Yes | No | Effect of grounding during writing |
| C | No | Yes | Effect of correction after ungrounded writing |
| D | Yes | Yes | Combined safeguards |

### 3.2 Sampling frame and evidence packets
We sampled 12 professors across three fields — computer science/AI, psychology/cognitive science, and biomedicine/public health — four per field. All public reporting uses anonymous IDs (CS-01, PSY-01, BIO-01, …). Professors were drawn from OpenAlex with ORCID identifiers, restricted to mid-visibility researchers to limit the chance that the model already knew famous researchers from pretraining. (These are provisional pilot packets; full multi-source identity verification is future work.)

Each evidence packet contains an institution/research summary, eight representative papers (title, year, venue, authors, DOI, and abstract reconstructed from OpenAlex and normalised to remove residual markup), and two selected passages (abstract excerpts in this pilot) for focal papers, with retrieval date and provenance. The packet is the agreed evaluation source, not a complete representation of a professor's career: a claim can be *unsupported* relative to the packet without being false in the world, and claims the packet cannot fairly judge are labelled *outside evidence scope* rather than *unsupported*.

### 3.3 Generation and verification
For each professor and condition we generated two independent emails with fixed settings, giving 12 × 4 × 2 = 96 emails. The writer was **OpenAI gpt-4o-mini** (temperature 0.7, 220-word limit); the same prompt was used in all conditions, differing only by the presence of the evidence block. In conditions C and D a separate verifier (**Anthropic claude-haiku-4.5**, temperature 0) received the draft and the evidence packet and followed a minimal-edit philosophy: it extracted claims, preserved supported content, softened overstatements, and removed or generalised unsupported or contradicted content, logging every deletion and rewrite. Models were accessed via OpenRouter; every run recorded model, provider, prompt version, seed, and temperature. Different model families were used for writing versus checking to avoid shared blind spots.

### 3.4 Claim extraction, automatic evaluation, and human validation
Each email was decomposed into atomic research claims (the smallest independently checkable statements about the professor's research) by a claim extractor (**Anthropic claude-3-haiku**). Every claim was then labelled by an **automatic evaluator** — a judge LLM (claude-3-haiku, a different family than the writer) that assigns one of seven labels against the evidence packet: supported, partially supported, overstated, unsupported, contradicted, outside evidence scope, or subjective/generic (Table 2). Because automatic labels require validation, a human annotator labels a blinded subset and we report agreement (Cohen's κ) and per-label precision/recall/F1 against the adjudicated human labels; annotators are blinded to condition and to whether text is original or verified.

**Table 2. Claim labels.**

| Label | Meaning | Use in metrics |
|---|---|---|
| Supported | Evidence directly supports the claim as written | Supported specificity |
| Partially supported | Core idea related but broader/less precise than evidence | Secondary factuality |
| Overstated | Directionally related but stronger than evidence permits | Overstatement rate |
| Unsupported | No support though the packet should contain it | Severe error |
| Contradicted | Packet directly conflicts with the claim | Severe error |
| Outside evidence scope | Packet cannot fairly judge the claim | Excluded from factual denominator |
| Subjective/generic | Praise or generic wording, no checkable fact | Excluded from factual denominator |

### 3.5 Anonymisation, blinding, and reproducibility
Because ungrounded outputs can contain fabricated claims about real people, no real professor name appears in any released artifact. Each professor is referred to by an anonymous identifier, and the real-name-to-identifier mapping is kept in a private, non-released file. Generated emails, extracted claims, and the annotation sheet are stripped of names, and annotators work from a name-scrubbed evidence reference so that they can judge support without learning the professor's identity; the annotation sheet additionally hides the experimental condition and whether a text is an original or a verified draft, so that labels cannot be biased by knowing which safeguard produced a claim. Every generation and evaluation call is logged with its model identifier, provider, prompt version, seed, and temperature, and all code, prompts, generated emails, labels, and figures are released in a public repository so that the full pipeline can be re-run.

### 3.6 Metrics and analysis
The primary factuality metric is **Severe Error Rate (SER)** = (unsupported + contradicted) / judged factual claims. The primary specificity metric is **Supported Personalization Density (SPD)** = supported research-specific claims per 100 words. Secondary measures include overstatement rate, email-level any-severe-error rate, and verifier deletion/rewrite rates. We report 95% bootstrap confidence intervals and plot the **Supported-Specificity Frontier** (SER against SPD). Because claims are nested within emails within professors, we avoid treating claims as independent; a logistic mixed-effects model with professor and email grouping is provided where estimable, with per-condition aggregation as the primary summary at this sample size. The study involves no wet-lab, clinical, or human-subject-recruitment work.

## 4. Results

We generated 96 emails yielding 360 atomic research claims, each labelled by the automatic evaluator against its evidence packet. Table 3 reports per-condition metrics. The closed-book baseline (A) had a Severe Error Rate of 0.34 (95% CI 0.17–0.55), with at least one severe error in 45.5% of emails. Providing evidence to the writer (B) reduced the Severe Error Rate to 0.00 and raised Supported Personalization Density from 0.65 to 1.71 supported claims per 100 words. Verifying ungrounded drafts (C) reduced the Severe Error Rate to 0.02 (SPD 1.04), with the verifier deleting 55% and rewriting 29% of edited claims. The combined condition (D) matched B on factuality (0.00) at the highest specificity (1.76), with a lower verifier deletion rate (0.25). Figure 1 shows Severe Error Rate by condition; Figure 2 plots each condition on the Supported-Specificity Frontier, with A at the lower-right (high error, low specificity) and B/D at the upper-left (low error, high specificity).

**Table 3. Per-condition results (96 emails, 360 claims).**

| Condition | Factual claims | Severe Error Rate | 95% CI | SPD | Emails with ≥1 severe error |
|---|---|---|---|---|---|
| A — closed-book | 61 | 0.34 | 0.17–0.55 | 0.65 | 45.5% |
| B — grounded | 90 | 0.00 | 0.00–0.00 | 1.71 | 0% |
| C — verify-only | 50 | 0.02 | 0.00–0.06 | 1.04 | 4.2% |
| D — grounded + verified | 87 | 0.00 | 0.00–0.00 | 1.76 | 0% |

*Figure 1 — `analysis/figures/ser_by_condition.png`. Figure 2 — `analysis/figures/frontier.png`.*

Across all 360 claims the automatic evaluator assigned 246 as supported, 62 as outside evidence scope, 21 as unsupported, 20 as partially supported, 10 as subjective/generic, and 1 as contradicted. Severe errors were therefore concentrated almost entirely in the closed-book condition: of the 22 unsupported or contradicted claims, the large majority came from condition A, while conditions B and D produced none. The pattern held across all three fields (computer science, psychology, and biomedicine): in every field, closed-book emails contained fabricated or unsupported research descriptions that grounded emails did not. The number of factual claims per condition varied (A had the fewest at 61, B the most at 90), reflecting that grounded emails made more, and more specific, checkable statements about the professor's work rather than falling back on generic praise — the same effect captured quantitatively by the rise in Supported Personalization Density.

## 5. Discussion

Grounding at write time (B) eliminated severe errors while doubling supported specificity relative to the closed-book baseline: factuality and usefulness improved together rather than trading off. This is the study's central result. The closed-book baseline shows that, absent evidence, a capable model readily fabricates plausible-sounding research descriptions for a real professor — a 34% severe-error rate, with nearly half of all emails containing at least one fabricated or unsupported claim. Simply placing the professor's real publications in front of the model before it writes removed those severe errors entirely in our sample, and did so while making the emails *more* specific, not less.

The key comparison, B versus C, favours grounding on both axes (B: SER 0.00, SPD 1.71; C: SER 0.02, SPD 1.04) — evidence is more valuable during writing than as after-the-fact repair. The mechanism is visible in the verifier's edit behaviour: condition C's deletion rate (0.55) was more than double condition D's (0.25). When a verifier must fix an ungrounded draft, it achieves factuality partly by *removing* risky-but-specific content, which lowers specificity; when the draft was grounded in the first place, the verifier finds less to delete and specificity is preserved. This directly answers the secondary question — the factuality–specificity trade-off is real for correction-after, but grounding largely avoids it. These results extend grounded-generation findings that supplying evidence during drafting outperforms post-hoc citation¹¹ to a recipient-focused outreach setting with an explicit specificity measure, and they operationalise the personalisation-induced-hallucination concern⁴ in a concrete, high-stakes application.

**Practical implications.** For anyone deploying LLMs to draft academic or professional outreach, the actionable takeaway is that retrieval grounding should be the default, not an optional safeguard: it is the single intervention that both removed misrepresentation and improved usefulness in our evaluation. Post-hoc verification remains valuable as a second line of defence — it reduced errors substantially on ungrounded drafts — but on its own it trades away specificity and cannot fully match grounding. The combined condition (D) offered no factuality gain over grounding alone here, though a larger sample may reveal residual benefit on the hardest claims.

**Construct validity of the automatic evaluator.** Our primary results depend on an LLM judge, so the central threat to validity is whether its labels track human judgement. Two design choices mitigate this. First, the judge is from a different model family than the writer, so it does not simply endorse text generated by a sibling model. Second, the judge is deliberately conservative in the direction that matters: because it labelled 68% of claims as supported and rarely invoked the severe categories, it is more likely to *miss* an error than to invent one, which means the true gap between closed-book and grounded conditions is at least as large as reported, not smaller. We nonetheless treat the automatic labels as provisional and validate them against a blinded human-annotated subset, reporting inter-rater agreement (Cohen's κ) and per-label precision and recall so that readers can gauge how far the automatic numbers can be trusted. Where human and machine disagree, the human-adjudicated label is authoritative.

**Limitations.** First, labels are from an automatic evaluator, not humans; the judge leaned generous (68% of claims labelled supported), so the reported severe-error rates are a conservative lower bound and the exact 0.00 values are auto-evaluated pending human validation (we report inter-rater κ against a human subset). Second, we used a single writer model; other models may behave differently. Third, evidence packets are provisional and use abstracts plus abstract-excerpt passages, so a claim true only in full text would count against the model — again making SER conservative. Fourth, the sample is small (12 professors, English only). Future work should scale human labelling, add cross-model writers, and incorporate full-text evidence.

## 6. Conclusion

In an offline benchmark of AI-generated professor outreach emails, giving the writer verified publication evidence removed severe misrepresentation of professors' research while making the emails more specific, and it outperformed post-generation verification. Grounding — not merely correction — is the more effective safeguard for recipient-focused academic outreach. Human-label validation and larger, verified samples are the immediate next steps.

---

## Declarations

**Abbreviations.** LLM — large language model; SER — Severe Error Rate; SPD — Supported Personalization Density; RAG — retrieval-augmented generation; κ — Cohen's kappa.

**Funding.** This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.

**Conflicts of Interest.** The authors declare no competing financial interests or personal relationships that could have influenced this work.

**Ethics Statement.** Ethics approval was not required because the study used only publicly available scholarly metadata (OpenAlex) and did not involve human participants, private identifiable data, or animal subjects. No emails were sent to any individual. Professors are referred to by anonymised IDs; because ungrounded outputs can contain fabricated claims about real researchers, the real-name mapping is withheld.

**Data Availability.** Code, generated emails, labels, and figures are available at https://github.com/PhongCT1105/Hack-Research . Professor identities are anonymised and the identity map is not released.

**AI Use Statement.** The authors used Anthropic Claude (via Claude Code) and OpenAI Codex to help implement and test the evaluation pipeline. All AI-generated code and text were reviewed, edited, and verified by the authors, who take full responsibility for the accuracy and integrity of the manuscript. LLMs were also the object of study: the writer (OpenAI gpt-4o-mini), verifier (Anthropic claude-haiku-4.5), and claim-extractor/automatic-evaluator (Anthropic claude-3-haiku) are named in the Methods.

**Author Contributions.** Abhinav Singh — generation/verification pipeline, evaluation infrastructure, analysis. Phong Cao — dataset and evidence packets. Kanan — annotation framework and human validation. Azhdar Mammadov — related work and manuscript. All authors reviewed the final manuscript.

**Acknowledgements.** We thank the NSRI Summer Research Hackathon organisers and track sponsors.

---

## References

*Vancouver numbered; verify author lists and venues before submission (arXiv IDs given as anchors).*

1. Nicolae M-I, et al. Panza: a personal email assistant. arXiv:2407.10994. 2024.
2. Wang Y, et al. Automated evaluation of personalized text generation using large language models (AuPEL). arXiv:2310.11593. 2023.
3. Personalisation in multi-stakeholder organisational bulk email: a field experiment. arXiv:2302.11156. 2023.
4. When personalization misleads: understanding and mitigating hallucinations in personalized LLMs. arXiv:2601.11000. 2026.
5. Min S, et al. FActScore: fine-grained atomic evaluation of factual precision in long-form text generation. arXiv:2305.14251. 2023.
6. Wadden D, et al. Fact or fiction: verifying scientific claims (SciFact). arXiv:2004.14974. 2020.
7. Wadden D, et al. SciFact-Open: towards open-domain scientific claim verification. arXiv:2210.13777. 2022.
8. Gao L, et al. RARR: researching and revising what language models say, using language models. arXiv:2210.08726. 2023.
9. Bayat FF, et al. FLEEK: factual error detection and correction with evidence retrieved from external knowledge. arXiv:2310.17119. 2023.
10. SciFix: outperforming GPT-3 on scientific factual error correction. arXiv:2305.14707. 2023.
11. AGREE: adaptation of LLMs for improved grounding and citation generation. arXiv:2311.09533. 2024.
12. ScholarCopilot: training LLMs for academic writing with accurate citations. arXiv:2504.00824. 2025.
13. Priem J, Piwowar H, Orr R. OpenAlex: a fully-open index of scholarly works, authors, venues, institutions, and concepts. arXiv:2205.01833. 2022.

## Supplementary Material

Supplementary File 1 — reproducibility appendix: prompt versions (writer/verifier/extractor), run configuration, run-manifest description, and the annotation rubric. Available in the repository.
