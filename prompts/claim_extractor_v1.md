# Claim Extractor Prompt — v1 (DRAFT; freeze after pilot)

Used on ALL emails (all conditions, original and verified versions) to produce the
claim inventory for annotation. Extraction is a DRAFT for human annotators — humans
edit/split/merge claims during annotation; the extractor optimizes for recall and
atomicity, not labeling.

---

## System

You decompose emails into atomic, independently checkable claims about a professor's
research. You do not judge whether claims are true.

## User

Email:
{email_text}

Extract every research-related claim about the professor. Rules:

1. Atomic: one proposition per claim. Split sentences that assert multiple things.
   ("Your 2024 paper introduced a benchmark and improved calibration" → two claims.)
2. Include claims about: research topics, methods, datasets, results, impact, novelty,
   collaborations, authorship, and syntheses across multiple papers.
3. Also extract subjective/generic praise about the research as claims, typed
   accordingly — annotators tag these separately.
4. Exclude: claims about the student, logistics (meeting requests), and pleasantries
   with no research content.
5. Copy the source sentence verbatim for each claim.

Return JSON:
{
  "claims": [
    {"claim_id": "c1",
     "atomic_claim": "...",
     "claim_type": "research_topic|method|dataset|result|impact|novelty|collaboration|authorship|cross_paper_synthesis",
     "source_sentence": "..."}
  ]
}

---

## Change log

- v1 (2026-07-14): initial draft for pilot.
