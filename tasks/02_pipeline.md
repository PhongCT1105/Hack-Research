# Workstream 2 — Generation & Verification Pipeline

**Owner:** Abhinav · **Depends on:** MOCK packet only (do NOT wait for real data)
**Blocks:** annotation (needs outputs), analysis.

## Objective

A reproducible four-condition generation pipeline with an evidence-based verifier and
claim extractor, fully logged (model, seed, prompt version, edits) — built and tested
against mock data, then run on real packets.

## Inputs

- `docs/experimental_design.md` (conditions, controls, verification protocol)
- `src/outreach_eval/` (schemas, LLM adapters, stubs to complete)
- `prompts/*_v1.md` (draft prompts — refine during pilot, freeze after)
- `data/evidence/MOCK-01.json`, then `CS-01.json` / `PSY-01.json` when delivered
- `config/config.yaml`

## Outputs (file contract)

| File | Content |
|---|---|
| `prompts/writer_v1.md`, `verifier_v1.md`, `claim_extractor_v1.md` | Final pilot prompt versions |
| `outputs/pilot.jsonl` | 16 pilot records (2 profs × 4 cond × 2 seeds), one `EmailRecord` per line |
| `outputs/full_generation.jsonl` | 96 records after freeze |
| `logs/run_manifest.csv` | One row per generation: run_id, professor_id, condition, seed, provider, model, prompt versions, temperature, timestamp |
| `annotations/claims_to_label.csv` + `annotations/blinding_map.csv` (gitignored) | Blinded claim sheet for Workstream 3 |

The output record schema is `outreach_eval.schemas.EmailRecord`:

```json
{
  "professor_id": "CS-01", "condition": "D", "seed": 1,
  "writer_received_evidence": true, "verification_applied": true,
  "original_email": "...", "verified_email": "...",
  "extracted_claims": [], "verifier_edits": [],
  "model": "...", "prompt_version": "v1"
}
```

## Steps

1. **Complete the stubs** in `src/outreach_eval/` (`generate.py`, `verify.py`,
   `extract_claims.py`) against the `LLMClient` interface. Use the `mock` provider for
   tests — no network in tests.
2. **One fixed writing prompt** (`writer_v1.md`): identical across conditions except the
   evidence block; constant persona, tone rules, and word limit.
3. **Implement conditions A–D** via `conditions.py`: the ONLY differences are evidence
   presence (writer) and verification (post). Model, temperature, max_tokens, and
   instruction text stay constant.
4. **Verifier** (RARR/FLEEK-style minimal edit): extract atomic claims → check against
   packet → preserve supported specificity → soften overstatements → remove/generalize
   unsupported or contradicted content. Store original and verified emails separately;
   log every edit as a `VerifierEdit`.
5. **Dry run**: `python scripts/run_pilot.py --dry-run` (mock provider) produces valid
   records end-to-end.
6. **Pilot**: run on CS-01 + PSY-01 → `outputs/pilot.jsonl` (16 emails). Bring to the
   team checkpoint.
7. **After freeze**: run all 12 professors → `outputs/full_generation.jsonl` (96 emails).
8. **Prepare annotation batch**: extract claims from all emails, shuffle, strip
   condition/version info into `annotations/claims_to_label.csv`; keep the mapping in
   the gitignored `annotations/blinding_map.csv`.

## Completion Criteria

- [ ] All four conditions run successfully on mock + real packets
- [ ] Every run has seed, model version, and prompt version in `logs/run_manifest.csv`
- [ ] Verifier deletions/rewrites fully logged per email
- [ ] Prompts frozen after pilot (any change = new `_v2` file + decision-log entry)
- [ ] Outputs use anonymous professor IDs only
- [ ] Tests pass with the mock provider (`pytest`)

## Agent Notes

- Retry transient API errors with `tenacity`; a failed generation is re-run, never
  hand-patched.
- Seeds: pass through to providers where supported; regardless, record the seed and
  treat (professor, condition, seed) as the unique run key — `run_id = f"{professor_id}_{condition}_{seed}"`.
- Do not implement any email-sending capability. Offline benchmark only.
