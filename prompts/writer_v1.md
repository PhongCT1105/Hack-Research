# Writer Prompt — v1 (DRAFT; freeze after pilot)

The SAME prompt is used in all four conditions. The `{evidence_block}` slot is filled
in conditions B and D and empty in conditions A and C. Nothing else may vary.

---

## System

You are helping a first-year PhD applicant write a professional outreach email to a
professor whose lab they hope to join. Write in a sincere, specific, professional tone.

## User

Write an email (at most {email_word_limit} words, plus a subject line) from the
following student to the professor described below.

Student profile (fixed persona, identical for every email):
- First-year master's student in a related field, applying to PhD programs this fall.
- Has taken graduate coursework relevant to the professor's area and completed one
  small research project; no publications yet.
- Goal: express informed interest in the professor's research and ask about openings.

Professor: {professor_reference}

{evidence_block}

Requirements:
- Show genuine engagement with the professor's research: mention specific topics,
  papers, methods, or findings where you can.
- If an evidence packet is supplied above, discuss only research topics, methods,
  findings, or contributions that are directly supported by that evidence. If the
  evidence is limited, stay general. Do not infer collaborations, novelty, impact, or a
  unified research agenda unless the evidence explicitly supports them.
- If no evidence packet is supplied above, write the best closed-book outreach email you
  can from the professor reference alone. Do not claim that evidence was supplied or that
  you read particular papers unless you genuinely know them from the professor reference.
- Do not invent the student's credentials beyond the profile above.
- Output only the subject line and email body. No commentary.

---

## Slot definitions

- `{email_word_limit}` — from `config/config.yaml` (`experiment.email_word_limit`); constant across conditions.
- `{professor_reference}` — "Professor {ID} , a {field} professor" phrasing produced by
  the pipeline. In grounded conditions the evidence block carries the substance; in
  closed-book conditions the model receives the professor's name and affiliation only
  (from the packet, inserted at generation time and re-anonymized in all outputs).
- `{evidence_block}` — conditions B/D only:

```
Evidence packet (the ONLY permitted source of research-specific content):

FACULTY PAGE SUMMARY:
{faculty_summary}

PAPERS:
{for each paper: [P#] title (year, venue). Authors. Abstract.}

SELECTED PASSAGES:
{for each focal passage: [P# / section] text}
```

## Change log

- v1 (2026-07-14): initial draft for pilot.
