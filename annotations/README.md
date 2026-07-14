# Annotations

Workstream 3 (Kanan). Rubric: `docs/annotation_rubric.md` · Spec: `tasks/03_annotation.md`.

| File | Written by | Notes |
|---|---|---|
| `claims_to_label.csv` | Pipeline (Abhinav) | Blinded — no condition, no original/verified flag, no real names |
| `blinding_map.csv` | Pipeline (Abhinav) | **Gitignored.** claim_id → (run_id, condition, version). Pipeline owner only |
| `human_labels.csv` | Annotators | Template: `claims_to_label.template.csv` columns + label columns |
| `edge_cases.md` | Annotators | Decision log of hard calls; feeds rubric before freeze |
| `rubric_notes.md` | Kanan | Clarifications discovered during pilot annotation |

**Blinding rule:** never join `human_labels.csv` with `blinding_map.csv` in any
annotation-facing artifact. The join happens only in analysis code after labels are final.
