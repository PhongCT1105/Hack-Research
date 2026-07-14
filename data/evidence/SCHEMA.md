# Evidence Packet Schema

One JSON file per professor: `data/evidence/<PROFESSOR_ID>.json` (e.g. `CS-01.json`).

- **Authoritative contract:** `src/outreach_eval/schemas.py` → `EvidencePacket`.
- **Machine-readable copy:** `evidence_packet.schema.json`, regenerate with
  `python -m outreach_eval.schemas > data/evidence/evidence_packet.schema.json`.
- **Validate a packet:** `python scripts/validate_packet.py data/evidence/CS-01.json`
- **Worked example:** `MOCK-01.json` (fictional professor; used by pipeline dry runs).

## Required contents (per `docs/dataset_policy.md`)

| Field | Requirement |
|---|---|
| `professor_id` | `CS-NN`, `PSY-NN`, `BIO-NN` (or `MOCK-NN` for fixtures) |
| `field`, `career_stage`, `visibility_band` | Stratification metadata |
| `faculty_summary` (+ provenance) | Short research-theme summary from the official page |
| `papers` | 6 for pilot (8 at scale): title, year, venue, full authors, DOI, abstract, provenance |
| `focal_passages` | 2–4 short verbatim passages for 1–2 focal papers (methods/results detail) |
| `real_name_do_not_export` | Stays inside this file; never copied downstream |

Every item carries `provenance` (source URL + retrieval date + access method).

**Freeze notice:** this schema is frozen after the 16-email pilot sign-off.
