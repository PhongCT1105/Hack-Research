# Agent & Contributor Guide

This repository is a research codebase for an offline study of factual errors in
AI-generated professor-outreach emails. Read this file before making any change.

## What this project is

A 2×2 factorial experiment (grounding × verification) measuring claim-level factual
accuracy of LLM-written outreach emails against verified publication evidence packets.
Full rationale: `docs/research_proposal.md`. Design: `docs/experimental_design.md`.

## Where to start

1. Find your workstream spec in `tasks/` (01_dataset, 02_pipeline, 03_annotation, 04_paper).
   Each spec lists objective, dependencies, exact file contracts, steps, and completion criteria.
2. Data contracts live in `src/outreach_eval/schemas.py` (Pydantic) and
   `data/evidence/evidence_packet.schema.json`. **Schemas are the source of truth** —
   if code and schema disagree, the schema wins; if a schema must change before the
   freeze, update both and log it in `docs/decision_log.md`.

## Hard rules — never violate these

1. **Freeze rule.** After the 16-email pilot is reviewed and signed off in
   `docs/decision_log.md`, the following are FROZEN: all files in `prompts/`, the
   evidence packet schema, the output record schema, and `docs/annotation_rubric.md`.
   Post-freeze changes are bug fixes only and must be logged.
2. **Never edit generated outputs.** Files in `outputs/` and `logs/` are written
   exclusively by pipeline code. Do not manually alter, "fix", or reformat them.
   If an output is wrong, fix the code and re-run with a logged manifest entry.
3. **Annotator blinding.** Nothing in `annotations/claims_to_label*.csv` may reveal the
   experimental condition, whether text is original or verified, or the professor's real
   name. The blinding map (`annotations/blinding_map.csv`, gitignored) is maintained by
   the pipeline owner only.
4. **Anonymization.** Professors' real names appear ONLY inside `data/evidence/*.json`
   packets and the private roster (`data/professors_private.csv`, gitignored). Everything
   else — outputs, annotations, analysis, paper, commit messages — uses anonymous IDs
   (`CS-01`, `PSY-02`, `BIO-03`, …).
5. **One owner per file.** Check the ownership table in `README.md` before editing an
   artifact owned by another workstream; coordinate via `docs/decision_log.md`.
6. **Versioned prompts.** Prompts are named `<role>_v<N>.md` (e.g. `writer_v1.md`).
   Never modify a prompt version in place after it has been used in a logged run —
   create `_v2` and record the change.
7. **Determinism & provenance.** Every generation run records model ID, provider,
   prompt versions, seed, temperature, and timestamp in `logs/run_manifest.csv`.
   A run that isn't in the manifest doesn't exist.
8. **Emails are never sent.** This is an offline benchmark. No code in this repo may
   contact an email service or any professor.

## Key definitions (use these words precisely)

- **Unsupported** means *not warranted by the agreed evidence packet* — NOT "false in
  the world". Claims the packet cannot fairly answer are **outside evidence scope**.
- **Severe error rate** = (unsupported + contradicted) / all judged factual claims.
- **Supported Personalization Density (SPD)** = supported research-specific claims per
  100 words. The verifier must not "win" by deleting specificity — track deletion and
  rewrite rates alongside factuality.

## Code conventions

- Python ≥ 3.11, package lives in `src/outreach_eval/`, install with `pip install -e ".[dev]"`.
- Pydantic v2 models for all data records; serialize to JSONL via `io_utils.py` helpers.
- The LLM layer is provider-agnostic: code against `outreach_eval.llm.LLMClient`;
  concrete providers (Anthropic, OpenAI) are chosen per-role in `config/config.yaml`.
  Prefer **different model families for writer, verifier, and auto-evaluator** to avoid
  shared blind spots.
- Keep instructions and output-length limits constant across conditions; the ONLY
  difference between conditions is evidence presence (writer) and verification (post).
- No network calls in tests; mock the LLM client.

## Workflow expectations

- Small, single-purpose commits scoped to one workstream.
- Before claiming a pipeline task complete, run `scripts/run_pilot.py --dry-run` (mock
  client) and `scripts/validate_packet.py` on all packets.
- Update `docs/decision_log.md` for any choice that affects another workstream
  (schema tweaks, label definitions, sampling changes, prompt bumps).
