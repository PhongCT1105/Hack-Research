# Response to Editorial Decision — NSRI-J-2026-0178

**Manuscript:** Recipient-Focused Hallucinations in AI-Generated Professor Outreach Emails: A Pilot Factorial Evaluation of Grounding and Verification
**Decision:** Revision Required (NSRI Student Research Journal)
**Revision:** 1

We thank the editorial team. The four points identified a single underlying defect: the manuscript presented automatic (LLM-judge) labels as measurements and converted a small-sample zero into an unconditional claim. We have corrected this throughout rather than patching individual sentences.

Every statistic in the revised manuscript was regenerated from the released data by two new scripts, `scripts/compute_revision_stats.py` and `scripts/make_revision_figures.py`. Their output is in `analysis/revision/` (nine CSVs plus `report.md`) and is included as Supplementary File 2, so each number below can be checked independently.

Five further problems surfaced during this work that the review did not name, three of them substantive. We report them in §5 below rather than leaving them for a second round.

---

## 1. "Support the central findings with human-checked results or clearly label them as pilot estimates."

We have taken the labelling route and applied it completely, because expanding human annotation to the point where it could carry the central findings is beyond what we can complete for this revision. We would rather state the limit than imply coverage we do not have.

| Change | Location |
|---|---|
| Title now reads "A **Pilot** Factorial Evaluation" | Title |
| Abstract Methods states the study is a pilot and that **all primary estimates are automatic pilot estimates, not human-verified measurements** | Abstract |
| §4.1 declares the labels as automatic pilot estimates *before* the first number appears | §4.1 opening |
| Table 3 caption marks the contents as automatic pilot labels | Table 3 |
| Figure 1 and 2 captions state the same | Figs 1–2 |
| New §4.2 reports human-labelled coverage per condition (Table 7) with exact intervals | §4.2 |

**We withdrew the claim that human labels validated the results.** The original Abstract said "Human labels confirmed the direction of every result." They cannot: conditions C and D rest on **three** human-labelled factual claims each, and condition D's three claims come from a **single email**. Their exact human intervals run to 0.71. The revision now says the human subset confirms the closed-book baseline is bad and is consistent with grounding being better, and explicitly that it does **not** confirm the per-condition estimates for B, C, or D.

The human numbers are reported in full (Table 7): A 7/11 severe (SER 0.636, 95% CI 0.308–0.891); B 0/10 (0.000–0.308); C 0/3 (0.000–0.708); D 0/3 (0.000–0.708).

**Planned for the full study.** §5.5 now names a concrete stratified expansion — every claim the automatic evaluator flagged severe, plus roughly 30 claims per condition — which would give per-condition human rates with usable intervals at a tractable annotation cost.

---

## 2. "Report evaluator disagreement and uncertainty explicitly."

Disagreement was previously reported only in the Discussion, and each mention was immediately followed by reassurance. It is now a Results subsection (§4.2), placed before the Discussion because it bounds every number in §4.1, and it is reported without softening.

**Added:**

- **Confidence intervals on κ.** Primary evaluator vs human: raw agreement 0.556, κ = 0.33, **95% CI 0.16–0.49**. Primary vs second evaluator: 0.725, κ = 0.50 (0.44–0.57). (Table 4.)
- **The interpretive band, stated plainly.** κ = 0.33 is *fair* agreement, and the **entire interval lies below the conventional κ ≥ 0.6 threshold** for treating a rater as reliable. The manuscript now says the primary labels are not a validated instrument.
- **The full human × machine confusion matrix** (Table 6, 36 claims), so the direction-of-disagreement claim rests on visible cell counts rather than assertion.
- **The disagreement direction, quantified.** Of 16 disagreements the evaluator was too lenient in **14**, too strict in **0**, and orthogonally different in 2. The original text asserted one-directionality without evidence; it holds in this subset, and we now show the counts that establish it.
- **A third comparison the original omitted:** second evaluator vs human, κ = 0.54 (0.35–0.74). **The second evaluator agreed with the human better than the primary evaluator did.** The primary estimates are drawn from the weaker of the two automatic raters. We state this and name re-running the corpus with a stronger judge as a priority.
- **Per-condition rates under both evaluators** (new Table 5). The original used the second evaluator only for a single aggregate agreement percentage, which concealed that the two evaluators disagree about whether the grounded conditions contain any severe errors at all. See item 3.
- **A note that Figure 1's intervals propagate label-sampling error only, not judge error**, so true uncertainty is wider than drawn.

**We also corrected the mechanism of under-detection**, which we had described inaccurately. The judge does not mainly mislabel severe claims as *supported*; it moves them **out of the denominator**. Seven claims the human called unsupported (6) or contradicted (1) were labelled *outside evidence scope*, a category excluded from the SER denominator. SER is therefore not a simply attenuated version of the true rate — the denominator is biased too. This is now stated in §4.2 and §5.3.

---

## 3. "Do not generalize zero observed errors into a universal guarantee."

This was partly a numerical error, not only wording, and we thank the editors for catching it.

**The reported interval was an artifact.** Conditions B and D were given "95% CI 0.000–0.000". That interval came from a percentile bootstrap over per-email severe-error rates: when no email contains a severe error, every resample returns zero and the interval collapses. Printed as a confidence interval it asserts certainty of zero risk. We have replaced it.

**Table 3 now reports exact (Clopper–Pearson) intervals**, which remain well defined at zero events:

| Condition | Observed | SER | 95% CI (revised) | was |
|---|---|---|---|---|
| A | 21/61 | 0.344 | 0.227–0.477 | 0.17–0.55 |
| B | **0/90** | 0.000 | **0.000–0.040** | 0.00–0.00 |
| C | 1/50 | 0.020 | 0.001–0.106 | 0.00–0.06 |
| D | **0/87** | 0.000 | **0.000–0.042** | 0.00–0.00 |

Because claims cluster within emails, the effective sample size lies between the claim count and the email count, so we also report the email-level bound (0/24 emails → **0.000–0.142**) and state that the true bound lies between the two. §3.6 explains why both are given and why the cluster bootstrap is uninformative here.

**The zeros do not replicate across evaluators, and we now say so.** Prompted by this point, we computed per-condition rates under the second automatic evaluator, which had previously been used only for an aggregate agreement figure. It does **not** reproduce the zeros (new Table 5):

| Evaluator | A | B | C | D |
|---|---|---|---|---|
| Primary (claude-3-haiku) | 21/61 = 0.344 | **0/90 = 0.000** | 1/50 = 0.020 | **0/87 = 0.000** |
| Second (gemini-2.5-flash-lite) | 35/77 = 0.455 | **10/94 = 0.106** | 11/54 = 0.204 | **4/90 = 0.044** |

The second evaluator finds 10 severe errors in condition B and 4 in D. The zero was therefore a property of the primary judge, not of the emails, and we are grateful the review pushed us to check. The manuscript now states this in the Abstract, §4.2, §5.1, §5.3, and §6, and reports the central finding as a **large reduction** in severe misrepresentation — roughly four-fold on the second evaluator's labels — rather than as elimination.

What survives across both evaluators is reported as such: the closed-book baseline is worst under both; both grounded conditions beat both ungrounded conditions under both; and **B < C, the study's key comparison, holds under both** (0.000 vs 0.020 primary; 0.106 vs 0.204 second). The second evaluator in fact separates B from C more clearly than the primary does, so the paper's main claim is better supported after this check than before it. What does not survive is the zero itself and the B-versus-D ordering, both of which are now presented as undetermined.

**Every unconditional sentence has been qualified.** The Abstract and §6 no longer say evidence "removed severe misrepresentation". §5.1 states that a deployment claim of "no misrepresentation" would not be supported by this evidence. §5.4 recasts the practical recommendation as a reason to prefer grounding in system design, not grounds for advertising a factuality guarantee, and adds the evaluation lesson: a single automatic judge would have led us to report elimination of an error mode a second judge still detects.

**Figure 1 was redrawn.** Zero-event conditions previously appeared as bars with zero-height error bars, which reads as a measured zero. They are now hatched, labelled "0/90 claims, upper bound 0.040", and the legend distinguishes observed rates from upper bounds. Figure 2 gained the same treatment.

We also replaced the vague summary "the large majority came from condition A" with the exact counts, which we had: **21 of the 22 severe errors were in condition A and 1 in condition C.**

---

## 4. "Correct NSRI formatting, if needed."

Checking the submitted PDF against the NSRI requirements (Word or LaTeX; standard fonts — Times New Roman or Arial; double spacing; continuous line numbering) found four violations. **All four are corrected in the accompanying `NSRI-J-2026-0178_revision1.docx`:**

| Requirement | Originally submitted | Now |
|---|---|---|
| Double spacing | **1.16×** (measured baseline pitch 14.3 pt at 12.4 pt type) | **2.0×** (480 twips) |
| Times New Roman or Arial | **Garamond** body text | **Times New Roman 12 pt** |
| Continuous line numbering | **Absent** | **Enabled**, continuous through the document |
| Word or LaTeX | **PDF** (Google Docs export) | **.docx** |

The .docx is generated from the Markdown source by `scripts/build_submission_docx.py`, so the manuscript and the submission file cannot drift apart: all nine tables are real Word tables with repeating header rows, all three figures are embedded at their callouts, and superscript citations are preserved. Margins are 1 inch throughout.

Double spaced, the manuscript runs to 26 pages.

**A note on length.** The revision initially grew from 3387 to 6393 words because of the reporting the review requires. We have since cut it back to **4798 words** (abstract 398 + body 4400, excluding tables, figure captions, declarations, and references). The cut was entirely to prose: every statistic, all nine tables, all three figures, all thirteen references, and every section of the revised structure are retained — we verified that no numeric value present in the longer draft is absent from the submitted one. If a tighter limit applies, §4.3 (field heterogeneity) and §4.4 (verifier behaviour) could move to supplementary material with two-sentence summaries in the Results, taking the body to roughly 3900 words without losing a reported statistic. Please advise if that is needed.

**References.** An audit of all 13 references against the arXiv API found defects in 8 of them, now corrected:

| Ref | Problem | Correction |
|---|---|---|
| 1 | First author wrong ("Nicolae M-I"); title paraphrased | Nicolicioiu A, et al.; "Panza: design and analysis of a fully-local personalized text writing assistant" |
| 3 | Given/family name reversed; "Multi-Objective" dropped from title | Kong R, et al.; full title restored |
| 4 | Given/family reversed and misspelled ("Zhongxian S") | Sun Z, et al. |
| 8 | Year given as 2023; arXiv v1 is 2022 | 2022 |
| 9 | Family name split ("Bayat FF") | Fatahi Bayat F, et al. |
| 10 | **No authors at all** | Ashok D, Kulkarni A, Pham H, Póczos B |
| 11 | Given/family reversed; **cited title was not the paper's title** | Ye X, et al.; "Effective large language model adaptation for improved grounding and citation generation (AGREE)" |
| 12 | Given/family reversed | Wang Y, et al. |

All 13 arXiv identifiers resolve to real papers, and every author name, title, and year in the revised list was verified against the arXiv record. Author lists are now given in Vancouver form with up to six names before "et al.". Citation numbering was also made consistent (the original mixed `[1][2]`, `[1,3]`, and `[8-10]`).

**Other typographic corrections:** Cohen's kappa is now set as κ throughout (previously Latin "k", including in the Abbreviations list); "2 × 2" uses a multiplication sign; en-dashes are used for numeric ranges; subsection heading capitalisation was made consistent; and "&" in headings was replaced with "and".

---

## 5. Issues we found that the review did not raise

We report these rather than leave them for a second round.

**(a) An undisclosed denominator change.** The design generates 24 emails per condition, and the manuscript reported "at least one severe error in 45.5% of emails". 45.5% is 10/22, not a rate over 24. In condition A, **2 of the 24 emails produced only outside-scope or subjective/generic claims** and were silently dropped from the email-level denominator (conditions B, C, and D retain all 24). The metric code reported `n_emails = 24` while computing the rate over emails carrying at least one factual claim. Table 3 now has separate "Emails generated" and "Emails with ≥1 factual claim" columns, and §4.1 explains the exclusion.

**(b) The verifier and the evaluator are the same model family.** §3.4 claimed the evaluator "does not grade text produced by the same model family". That holds for the writer (OpenAI gpt-4o-mini) but **not for conditions C and D**, where the verifier (claude-haiku-4.5) and the evaluator (claude-3-haiku) are both Anthropic models — the text was edited and graded by the same family. The near-zero rates in C and D may partly reflect that. Condition B, which carries the central grounding claim, involves no verifier and is unaffected, and the second evaluator from a third model family reproduces the same ranking. This is now disclosed in §3.4 and §5.3, with C and D flagged as more fragile than B.

**(c) The headline baseline is concentrated in one field.** The manuscript said "the pattern held across all three fields". Literally true — every field had at least one closed-book severe error — but it implied homogeneity that does not exist:

| Field | Condition A SER |
|---|---|
| Psychology | **17/19 = 0.89** |
| Computer science | 3/23 = 0.13 |
| Biomedicine | 1/19 = 0.05 |

**The four psychology professors account for 17 of the 21 closed-book severe errors (81%).** Two professors alone account for 11 of 21, and **5 of the 12 professors produced no severe errors even closed-book**. Excluding psychology, the closed-book SER falls from 0.344 to **0.095** (4/42, 95% CI 0.027–0.226). The revision adds §4.3, Table 8, and a new Figure 3, and states that the *direction* of the grounding effect is consistent across fields while its *magnitude* is dominated by one field of four professors and is not a general closed-book hallucination rate.

**A pre-specified metric was unmeasurable.** Neither automatic evaluator ever emitted the *overstated* label on any of the 360 claims, so the overstatement rate was 0.000 in all conditions **by construction rather than by finding**. The human annotator did use the label. We have withdrawn the metric and disclosed why (§3.6, §4.2) rather than report a structurally empty result.

**The Data Availability Statement overclaimed.** Preparing this revision we checked what the public repository actually contains. The original statement said generated emails were available; they are not, and must not be. Closed-book drafts address real researchers by surname and carry fabricated claims about their work, so publishing them would de-anonymize the sample and propagate exactly the misrepresentation the study measures. The statement now says plainly what is released (code, prompts, name-scrubbed claims with all three label sets, the claim-to-condition map, figures, and the full revision statistics) and what is withheld and why, and offers the email corpus to the editors on request. To keep the analysis reproducible without it, `scripts/compute_revision_stats.py` now also exports `analysis/revision/run_metadata.csv` — de-identified per-run word counts and verifier actions, the only things the tables need from the withheld file. We confirmed by scan that no released artifact contains a real professor name.

**Supported Personalization Density is also inflated.** Of the 24 claims the primary evaluator called *supported*, only 16 were human-supported — precision 0.67 (95% CI 0.47–0.83) — with six human *subjective/generic* claims counted as supported. The SPD numerator is inflated by roughly one third. §4.2 reports approximate human-adjusted densities (A 0.43, B 1.14, C 0.69, D 1.17); the ordering across conditions is preserved, the absolute values are not.

---

## Summary of changes

**New:** §4.2 (evaluator reliability, moved from Discussion and expanded), §4.3 (field heterogeneity), §4.4 (verifier edit behaviour); Tables 4–9 (Table 4 agreement with κ intervals, Table 5 per-condition rates under both evaluators, Table 6 confusion matrix, Table 7 human coverage, Table 8 field heterogeneity, Table 9 verifier edits); Figure 3; `scripts/compute_revision_stats.py`; `scripts/make_revision_figures.py`; `analysis/revision/` (Supplementary File 2).

**Revised:** title; Abstract (rewritten, with an explicit "Interpretation and limits" paragraph); §3.4 (model-family confound); §3.5 (reliability method); §3.6 (interval methodology and the withdrawn metric); §4.1 (pilot framing, exact intervals, corrected denominators, exact severe counts); §5 (restructured into principal findings, grounding vs correction, threats to validity, practical implications, limitations); §6; Figures 1–2; all 13 references.

**Withdrawn:** the claim that human labels confirmed the direction of every result; the [0.000, 0.000] intervals; the overstatement-rate metric; unconditional statements that grounding removed or eliminated misrepresentation; the implication that the closed-book rate is homogeneous across fields; and the B-versus-D ordering, now reported as undetermined.

We believe the revised manuscript reports a more limited but considerably better-supported result. The central finding — that grounding at write time outperformed post hoc verification on both factuality and specificity — survives every check we added, including replication under a second independent evaluator, and now carries its uncertainty explicitly rather than by implication. The claim we can no longer make is that grounding eliminates misrepresentation; we thank the editors for requiring that correction, since a single-judge pipeline would have let it stand.
