# Repo Scaffold Design — AI Outreach-Email Factuality Study

**Date:** 2026-07-14 · **Status:** Approved by Phong; implemented same day.

## Goal

Turn the two planning documents (`docs/source/*.docx`) into a working repository:
directory structure, enriched markdown documentation, agent-executable task specs, and
provider-agnostic starter code, so the four workstreams (dataset, pipeline, annotation,
paper) can start in parallel.

## Decisions (from user Q&A)

1. **Scope:** docs + starter code (schemas and LLM layer fully written; pipeline
   modules implemented enough to dry-run end-to-end).
2. **LLM stack:** provider-agnostic (`LLMClient` protocol; anthropic/openai/mock
   adapters; per-role config in `config/config.yaml`).
3. **Doc format:** agent-executable task specs in `tasks/` with objective,
   dependencies, file contracts, steps, and completion criteria.

## Structure (as built)

- Root: `README.md` (overview/repo map), `CLAUDE.md` (hard rules: freeze, blinding,
  anonymization, provenance), `pyproject.toml`, `config/config.yaml`.
- `docs/`: research_proposal, experimental_design, dataset_policy, annotation_rubric,
  analysis_plan, ethics_and_limitations, decision_log; originals in `docs/source/`.
- `tasks/01_dataset.md … 04_paper.md`: one spec per workstream owner.
- `data/`: professors template, `evidence/` schema (Pydantic-exported JSON schema),
  `MOCK-01.json` fixture.
- `prompts/`: writer_v1 / verifier_v1 / claim_extractor_v1 (frozen after pilot).
- `src/outreach_eval/`: schemas, llm, conditions, generate, verify, extract_claims,
  io_utils.
- `scripts/`: run_pilot.py (with --dry-run), validate_packet.py.
- `annotations/`, `analysis/`, `paper/` seeded with templates and the 10-paper
  related-work matrix.

## Verification

`python scripts/run_pilot.py --dry-run` (mock provider, MOCK-01) produces 8
schema-valid records covering all four conditions, with verification + claim
extraction on C/D, plus a run manifest. `validate_packet.py` passes on the fixture.

## Note

A parallel `benchmark-v1` expansion (≈100 professors) later extended
`docs/dataset_policy.md` and `docs/decision_log.md`; this scaffold is the pilot layer
those decisions build on (see decision log D002/D003).
