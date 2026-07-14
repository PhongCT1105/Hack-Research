# Workstream 1 — Dataset & Evidence Packets

**Owner:** Phong · **Depends on:** nothing (starts immediately)
**Blocks:** pipeline pilot run (needs first 2 packets), all downstream analysis.

## Objective

Deliver 12 verified, anonymized, schema-valid professor evidence packets plus the
sampling manifest, so that generation, annotation, and analysis rest on trustworthy
evidence.

## Inputs

- `docs/dataset_policy.md` (sampling rules, packet spec, anonymization)
- `data/evidence/evidence_packet.schema.json` + `src/outreach_eval/schemas.py` (contract)
- `data/evidence/MOCK-01.json` (worked example of a complete packet)

## Outputs (file contract)

| File | Content |
|---|---|
| `data/professors.csv` | Public manifest: `professor_id, field, career_stage, visibility_band, n_papers_in_packet, packet_complete` |
| `data/professors_private.csv` | **Gitignored.** `professor_id, real_name, faculty_url, orcid, notes` |
| `data/evidence/CS-01.json` … `BIO-04.json` | 12 packets matching the schema |
| `docs/dataset_policy.md` | Updated with any policy decisions made during collection |

## Steps

1. **Select professors** — 4 CS/AI, 4 Psych/CogSci, 4 Biomed/Public-Health, stratified by
   career stage and visibility band within field (see `docs/dataset_policy.md`). Do not
   pick by fame.
2. **Assign IDs** (`CS-01`…`BIO-04`) in `data/professors_private.csv` first; only then
   create any other artifact.
3. **Verify identity** — cross-check each professor's publication ownership with ≥2 of:
   faculty page, ORCID, OpenAlex, Semantic Scholar, Crossref. Reject/replace professors
   with ambiguous authorship.
4. **Build each packet** per the schema: faculty-summary, 6 papers (title/year/venue/
   authors/DOI/abstract/source link), 1–2 focal papers with 2–4 full-text passages,
   provenance (retrieval date + URL) on every item.
5. **Validate**: `python scripts/validate_packet.py data/evidence/<ID>.json` must pass
   for every packet.
6. **Priority handoff:** finish `CS-01.json` and `PSY-01.json` FIRST and announce —
   the pipeline pilot starts on those two.

## Completion Criteria

- [ ] First 2 packets (CS-01, PSY-01) delivered early for the pilot
- [ ] All 12 packets pass `scripts/validate_packet.py`
- [ ] No misattributed papers (≥2-source identity check logged per professor)
- [ ] Sample balanced across fields; stratification recorded in `professors.csv`
- [ ] Real names appear nowhere outside packets + private roster
- [ ] Every evidence item has retrieval date and source URL

## Agent Notes

- When fetching abstracts programmatically, prefer OpenAlex/Semantic Scholar APIs and
  reconcile DOIs via Crossref; keep raw API responses out of the repo (scratch only).
- If a professor lacks 6 recent papers or a usable faculty page, replace them and note
  the swap in `docs/decision_log.md`.
- Focal passages should target methods/results details that the abstracts omit —
  that is exactly where annotation needs evidence.
