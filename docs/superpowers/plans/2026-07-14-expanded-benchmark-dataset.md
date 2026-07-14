# Expanded Benchmark Dataset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an implementation-ready, privacy-aware collection layer for an approximately 100-professor benchmark while preserving the existing 12-professor pilot.

**Architecture:** Keep the pilot experiment and its pre-freeze runtime contracts intact. Add a versioned collection layer under `docs/`, `schemas/`, `config/dataset.yaml`, and `data/{raw,interim,final,private}`. Collection scripts share deterministic CLI, cache, logging, dry-run, and no-overwrite conventions; the packet builder emits anonymous, provenance-rich records validated before use by the email experiment.

**Tech Stack:** Python 3.11 standard library, PyYAML, JSON Schema draft 2020-12, OpenAlex REST API, CSV/JSON/JSONL/YAML.

## Global Constraints

- The 12-professor, 3-domain, 96-email design remains the pilot.
- The 2-professor, 16-email run remains the pilot's pre-freeze checkpoint.
- No real professor records, real identity map, raw PDFs, API keys, or generated emails are added.
- Expanded benchmark schemas are versioned collection contracts and do not silently replace frozen pilot runtime schemas.
- Public analysis uses anonymous professor IDs; identity-bearing mappings remain private.
- Raw source records are immutable; transformations write to new versioned paths and never overwrite silently.

---

### Task 1: Document the collection and benchmark design

**Files:**
- Create: `docs/benchmark_design.md`
- Create: `docs/openalex_collection_guide.md`
- Create: `docs/first_10_collection_checklist.md`
- Create or modify: `docs/dataset_policy.md`, `docs/decision_log.md`
- Modify: `README.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: existing pilot scope, factorial design, evidence policy, privacy rules, and freeze rule.
- Produces: definitions, target margins, staged workflow, table contracts, quality gates, and a collector-facing first command.

- [ ] Write the benchmark reference and rationale, keeping all seven difficulty-related dimensions separate.
- [ ] Write the task-oriented OpenAlex collection guide with API, cache, reconciliation, and provenance rules.
- [ ] Write the dataset policy and privacy/licensing boundaries.
- [ ] Record every expanded-benchmark decision and how it relates to the pilot.
- [ ] Add a first-10-professor gate and link all documents from the repository entry points.

### Task 2: Define machine-readable collection contracts

**Files:**
- Create: `schemas/professor.schema.json`
- Create: `schemas/paper.schema.json`
- Create: `schemas/evidence_packet.schema.json`
- Create: `config/dataset.yaml`
- Create: `data/dataset_manifest.template.yaml`

**Interfaces:**
- Consumes: documented field definitions and target distributions.
- Produces: draft 2020-12 JSON Schemas and a YAML configuration consumed by collection scripts.

- [ ] Define professor metadata, dimension scores, source methods, review states, and secondary metadata.
- [ ] Define paper popularity, complexity components, reconciliation, selection, and focal status.
- [ ] Define eight-paper/two-focal-paper evidence packets, passages, provenance, and quality-control assertions.
- [ ] Encode reproducibility seeds, target margins, selection counts, and path conventions.
- [ ] Add a manifest template for source snapshots, sampling versions, achieved margins, exclusions, and checksums.

### Task 3: Protect the data layout

**Files:**
- Create: `data/raw/.gitkeep`, `data/interim/.gitkeep`, `data/final/.gitkeep`, `data/private/.gitkeep`, `data/private/raw_pdfs/.gitkeep`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: privacy and licensing rules.
- Produces: tracked empty stage directories while ignoring identity maps, PDFs, credentials, and caches.

- [ ] Create stage directories with immutable-raw and private-data conventions.
- [ ] Ignore all private identity-map variants and downloaded PDFs while retaining directory placeholders.
- [ ] Ignore common API credential files, HTTP caches, and temporary collection artifacts.

### Task 4: Add tested collection scaffolds

**Files:**
- Create: `tests/test_dataset_scaffolds.py`
- Create: `scripts/_dataset_cli.py`
- Create: `scripts/01_fetch_institutions.py` through `scripts/12_validate_dataset.py`

**Interfaces:**
- Consumes: `config/dataset.yaml`, staged CSV/JSONL inputs, environment-provided API credentials.
- Produces: deterministic stage plans, safe output handling, failure logs, abstract reconstruction, and dataset validation entry points.

- [ ] Write a failing standard-library test that requires all 12 CLIs, `--help`, deterministic abstract reconstruction, and no-overwrite behavior.
- [ ] Run `python -m unittest tests/test_dataset_scaffolds.py -v` and confirm failure because the shared implementation is absent.
- [ ] Implement the shared parser, config loader, seed control, cache/log conventions, atomic no-overwrite writes, and stage-plan output.
- [ ] Add all 12 stage entry points; keep unimplemented network mutations explicit while making dry-run planning executable.
- [ ] Implement OpenAlex inverted-index abstract reconstruction and repository-level validation.
- [ ] Re-run the unit test and confirm all checks pass.

### Task 5: Verify the complete handoff

**Files:**
- Verify all files created or modified above.

**Interfaces:**
- Consumes: complete documentation, configuration, schemas, scripts, and ignore rules.
- Produces: evidence that the repository is ready for a first controlled collection test.

- [ ] Parse every JSON Schema with `python -m json.tool`.
- [ ] Parse `config/dataset.yaml` and the manifest template with `yaml.safe_load`.
- [ ] Run every script with `--help`.
- [ ] Run unit tests and `git diff --check`.
- [ ] Confirm private identity maps, PDFs, `.env` variants, and caches are ignored.
- [ ] Search tracked work for real professor records, fabricated records, and pilot-scope regressions.
- [ ] Report files, decisions, assumptions, limitations, and the exact first collection command.
