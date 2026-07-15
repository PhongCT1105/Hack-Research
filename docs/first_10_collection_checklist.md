# First 10-Professor Collection Test

Use this checklist as a go/no-go gate before scaling collection. The first ten are a process test, not a convenience sample for final analysis. Do not generate or send outreach emails as part of this checklist.

## 1. Preflight

- [ ] `config/dataset.yaml` parses and records `benchmark-v1`, seed 42, target 100, and all target margins.
- [ ] All 12 scripts run with `--help`; all network stages run with `--dry-run` without network calls or file mutation.
- [ ] `OPENALEX_API_KEY` is present only in the environment and never appears in logs, manifests, commands, or cached URLs.
- [ ] Raw, interim, final, and private paths are separate; overwrite protection has been demonstrated.
- [ ] Dataset manifest is copied from the template and assigned a candidate-pool version.

## 2. Institution and candidate coverage

- [ ] The institution seed set includes more than one country and region and is not dominated by highly visible US universities.
- [ ] Institution OpenAlex and ROR IDs, types, countries, regions, and homepages are reviewed.
- [ ] Candidate discovery returns more candidates than needed for ten verified records.
- [ ] Minimum works, abstracts, recent activity, affiliation, and topic filters are logged.
- [ ] ORCID absence is not used as an automatic exclusion.

## 3. Faculty and identity verification

- [ ] Exactly 10 test professors have a current role confirmed on an official faculty/university/lab page.
- [ ] Faculty URL, title, retrieval date, and identity notes are recorded.
- [ ] Career stage source distinguishes official-page evidence from publication-year estimation.
- [ ] OpenAlex identity is compared with topic, institution, and sample publication evidence.
- [ ] No candidate has an unresolved merge, split, affiliation conflict, or ambiguous ownership issue.
- [ ] Rejections and deferrals have explicit reason codes.

## 4. Work retrieval and reconciliation

- [ ] Every test professor has at least 8 eligible works and 6 usable abstracts.
- [ ] All raw OpenAlex response pages and redacted request metadata are cached immutably.
- [ ] Abstract reconstruction is deterministic and malformed indexes are logged.
- [ ] DOI records are checked against Crossref where available.
- [ ] Author-paper ownership is checked with a second source for every selected paper.
- [ ] Titles, years, venues, and author conflicts are preserved rather than silently resolved.

## 5. Scores and dimensions

- [ ] Visibility uses field/career-normalized percentiles; extreme top visibility is flagged.
- [ ] Paper popularity and paper complexity are stored separately.
- [ ] Every complexity component, normalization stratum, and missing value is inspectable.
- [ ] Research breadth and topic coherence remain separate fields.
- [ ] Method tags and diversity are plausible across all five broad domain types represented in the candidate pool.
- [ ] Synthesis-difficulty components are stored and final tiers receive human review.
- [ ] Evidence completeness and ambiguity are not folded into a generic difficulty score.

## 6. Paper and passage selection

- [ ] Each packet has exactly 8 selected papers: 3 recent, 2 influential, 2 diversifying, and 1 seeded random slot after deterministic duplicate resolution.
- [ ] Each paper has a primary selection reason and retained score inputs.
- [ ] Exactly 2 focal papers per professor have verified authorship and legal full-text evidence.
- [ ] Each focal paper has 2-4 short passages with section, page when available, source URL, retrieval date, access/license note, and rationale.
- [ ] Passages cover objectives, methods, results, and limitations where the source permits.
- [ ] No copyrighted full PDF is staged for commit.

## 7. Packet, privacy, and provenance

- [ ] All ten packets validate against the JSON Schemas.
- [ ] Professor IDs are unique and anonymous.
- [ ] Every evidence item resolves to a source/provenance record.
- [ ] Real names and direct identity mappings do not appear in public analysis/test outputs.
- [ ] `data/private/professor_identity_map.csv` and `data/private/raw_pdfs/` are ignored by Git.
- [ ] No sensitive demographic trait has been inferred or recorded.
- [ ] Packet limitations make `outside_evidence_scope` usable for unanswerable claims.

## 8. Human process review

- [ ] Two team members independently inspect at least 2 of the 10 packets for authorship, evidence sufficiency, and synthesis risk.
- [ ] Reviewers can identify why each paper and passage was selected.
- [ ] Reviewers agree that the packet can support topic, method, result, and cross-paper claim adjudication without treating abstracts as complete evidence.
- [ ] Any automated/manual disagreement is logged with a disposition.
- [ ] No prompt, runtime output schema, or annotation rubric is changed without respecting the pilot freeze rule.

## 9. Go/no-go decision

- [ ] Validation report has no hard-gate failures.
- [ ] Achieved test coverage exposes at least two career stages, two visibility tiers, and contrasting breadth/synthesis profiles; if not, expand the process test before scaling.
- [ ] API cost, rate limits, cache hit rate, retry behavior, and collector time are recorded.
- [ ] The decision log records `GO`, `REVISE`, or `STOP`, responsible reviewer, date, and required changes.
- [ ] The manifest records checksums and versions for the approved ten-professor test.

Scale only after every hard quality item passes. A `REVISE` decision requires a new process-test version; do not hand-edit the prior raw or final files.
