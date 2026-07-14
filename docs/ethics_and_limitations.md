# Ethics and Limitations

## Ethics Statement (working draft)

- **Offline by design.** All emails are generated for evaluation against publication
  records and are **never sent**. No professor is contacted. No code in this repository
  may integrate with an email service.
- **Public data only.** Evidence packets are built exclusively from public scholarly
  sources: official faculty pages, OpenAlex, Semantic Scholar, Crossref, ORCID, and
  published papers.
- **Anonymization.** Professors are identified by anonymous IDs in all analysis outputs,
  annotations, figures, and the paper. The ID↔name roster is private and excluded from
  any public release. Released examples are paraphrased/redacted so individuals are not
  identifiable.
- **Purpose.** The study measures and mitigates a harm (misrepresentation of real
  scholars' work by AI outreach tools); it does not build or optimize a cold-email tool.
- **Dual-use consideration.** We release evaluation methodology and annotation
  frameworks, not a polished outreach-generation system. Prompts are released for
  reproducibility of the *evaluation*.

## Known Limitations (to state in the paper)

1. **Packet-relative ground truth.** "Unsupported" means unsupported by the agreed
   evidence packet, not false in the world. A claim can be true yet absent from the
   packet; the `outside_evidence_scope` label and passage-escalation policy mitigate but
   do not eliminate this.
2. **Abstract-heavy evidence.** Even with focal-paper passages, abstracts underspecify
   methods/results (SciFact-Open lesson); some false negatives on method/result claims
   are expected.
3. **Model coverage.** One main writer model (plus a second-family robustness check at
   scale); conclusions may be partly model-specific.
4. **Training-data contamination.** Models may already know famous professors; visibility
   stratification and subgroup analysis address this only partially.
5. **Metadata quality.** Scholarly graphs have author-disambiguation errors; we
   cross-check with ≥2 sources but cannot guarantee perfect attribution.
6. **Sample size.** The pilot (12 professors) supports debugging and effect direction,
   not confident interaction estimates; claims about interactions require the 24+
   professor design.
7. **LLM-assisted evaluation.** Automatic claim extraction/labeling has its own error
   modes; all automatic judgments are validated against adjudicated human labels, and
   different model families are used across writer/verifier/evaluator roles.
8. **Field scope.** Three fields; "method," "impact," and "novelty" mean different
   things across disciplines. Field is modeled explicitly, but generalization beyond
   these fields is untested.
