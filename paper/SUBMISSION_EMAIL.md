<!--
Copy-paste email for the resubmission. Reply to the existing thread
("NSRI Editorial Decision | Revision Required | NSRI-J-2026-0178") so the
submission ID and history stay attached. Do not start a new thread.

To:      contact@nsri.world
Subject: (leave as the reply subject, i.e. "Re: NSRI Editorial Decision | Revision Required | NSRI-J-2026-0178")

Attach:
  1. paper/NSRI-J-2026-0178_revision1.docx                  — revised manuscript
  2. paper/NSRI-J-2026-0178_response_to_reviewers.docx      — point-by-point response
-->

# Resubmission email — NSRI-J-2026-0178

**To:** contact@nsri.world
**Subject:** Re: NSRI Editorial Decision | Revision Required | NSRI-J-2026-0178
**Attachments:** `NSRI-J-2026-0178_revision1.docx`, `NSRI-J-2026-0178_response_to_reviewers.docx`

---

Dear NSRI Editorial Team,

Thank you for the editorial review of NSRI-J-2026-0178, "Recipient-Focused Hallucinations in AI-Generated Professor Outreach Emails." Please find attached our revised manuscript and a point-by-point response to each of the four points raised.

All four have been addressed:

1. **Pilot estimates.** The title now reads "A Pilot Factorial Evaluation," and the abstract, Results, and every table and figure caption state that the primary estimates come from an automatic (LLM) evaluator and are not human-verified. We withdrew our earlier claim that human labels confirmed the direction of every result: conditions C and D rest on three human-labelled factual claims each, which cannot support per-condition estimates, and we now say so explicitly.

2. **Evaluator disagreement and uncertainty.** This has moved out of the Discussion into a Results subsection (§4.2), because it bounds every number in the paper. It now reports Cohen's κ with confidence intervals, the full human-versus-machine confusion matrix, per-condition human coverage, and the fact that κ = 0.33 (95% CI 0.16–0.49) falls entirely below the conventional reliability threshold.

3. **Zero observed errors.** Your point identified a genuine numerical error, not only a wording problem. The intervals we had reported as [0.000, 0.000] were an artifact of a percentile bootstrap, which collapses when a condition contains no events. These are replaced with exact (Clopper–Pearson) bounds, and the zeros are now reported as upper bounds rather than measurements.

    Checking this also led to a finding that materially changes the paper. Prompted by your comment, we computed per-condition rates under our second automatic evaluator, which had previously been used only for an aggregate agreement figure. **It does not reproduce the zeros**: it finds 10 severe errors in the grounded condition and 4 in the grounded-plus-verified condition. The zero was therefore a property of one judge rather than of the emails. The manuscript now reports the central result as a large, judge-dependent reduction in severe misrepresentation rather than as elimination. We are grateful the review pushed us to check.

4. **Formatting.** The manuscript is resubmitted as a Word document in Times New Roman 12 pt, double spaced, with continuous line numbering. We also audited all thirteen references against the arXiv record and corrected eight, including one wrong first author, one missing author list, and one cited title that was not the paper's actual title.

Two further matters we should raise directly.

**Our Data Availability Statement was inaccurate and has been corrected.** It previously said the generated emails were available in our public repository. They are not, and should not be: closed-book drafts address real researchers by surname and contain fabricated claims about their work, so releasing them would de-anonymize our sample and propagate the misrepresentation the study exists to measure. The statement now specifies what is released — code, prompts, name-scrubbed claims with all three sets of labels, the claim-to-condition map, figures, and the complete revision statistics — and what is withheld and why. **We will gladly provide the full email corpus to the editors or reviewers for verification on request.** All tables can be reproduced without it.

**The revised manuscript is longer than the original**, at 4,798 words of body text against 3,387, almost entirely because of the added reliability, heterogeneity, and uncertainty reporting. Double spaced it runs to 26 pages. If a word or page limit applies, we can move two Results subsections and their tables to supplementary material without losing any reported statistic; please let us know.

Every statistic in the revision was regenerated from our released data by scripts included in the repository, so each number in the response can be checked independently.

We believe the revised manuscript reports a more limited but considerably better-supported result. The finding that motivated the study — that grounding during drafting outperforms post hoc verification on both factuality and specificity — holds under both automatic evaluators and in all three sampled fields. The claim we can no longer make is that grounding eliminates misrepresentation, and we are glad to have corrected it before publication rather than after.

We would be happy to provide any further material you need.

With thanks,

Abhinav Singh
On behalf of Azhdar Mammadov, Kanan Gasimov, and Phong Cao
Corresponding author, NSRI-J-2026-0178
laterabhi1@gmail.com

---

## Checklist before you hit send

- [ ] Replying to the existing decision thread, not a new email
- [ ] Both `.docx` files attached (manuscript + response)
- [ ] Repository is public and the new commits are pushed (done: `b8e700f`)
- [ ] Author names, affiliations, and all four ORCID iDs correct on page 1
- [ ] Co-authors have seen this version
