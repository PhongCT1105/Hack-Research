# Resumable OpenAlex Progress Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist one human-readable local checkpoint per logical API command so collection resumes at the exact institution/professor and cursor after credit exhaustion or interruption.

**Architecture:** A focused `_collection_progress.py` module owns stable job fingerprints, atomic JSON state, status rendering, item/page transitions, and rate-limit parsing. The shared dataset CLI exposes state/resume/status controls. Live OpenAlex collectors call the transition functions only after raw data is durably written.

**Tech Stack:** Python 3.11+ standard library, JSON, SHA-256, argparse, unittest/pytest, Ruff.

## Global Constraints

- Never store API keys in checkpoints, commands, hashes, logs, or raw request metadata.
- Different endpoints, filters, inputs, seeds, and dataset versions create different jobs.
- Completed item IDs and within-item cursors survive process and machine restarts.
- Every checkpoint write is atomic.
- Rate-limit exhaustion exits instead of sleeping until the next daily reset.
- `.collection_state` databases and shared services are out of scope; state lives in ignored `data/raw/progress/` JSON files.
- No real professor records are added by tests.

---

### Task 1: Stable jobs and atomic checkpoints

**Files:**
- Create: `scripts/_collection_progress.py`
- Create: `tests/test_collection_progress.py`

**Interfaces:**
- Produces: `make_job_id(stage, setup, input_checksum) -> str`, `ProgressStore`, `new_progress(...)`, `file_sha256(path) -> str`.

- [ ] Write failing tests asserting API-key changes do not change a job ID, filter changes do, and two setups save to distinct JSON files.
- [ ] Run `.venv/bin/pytest tests/test_collection_progress.py -v` and verify import failure for `_collection_progress`.
- [ ] Implement recursive secret stripping, canonical JSON hashing, SHA-256 input fingerprints, and atomic `ProgressStore.save/load/list_jobs`.
- [ ] Re-run the focused tests and require all job/checkpoint tests to pass.

### Task 2: Per-profile transitions and rate-limit pause

**Files:**
- Modify: `scripts/_collection_progress.py`
- Modify: `tests/test_collection_progress.py`

**Interfaces:**
- Produces: `start_item`, `record_page`, `complete_item`, `pause_rate_limit`, `parse_rate_limit_headers`, `parse_rate_limit_payload`, and `render_status`.

- [ ] Write failing tests for a synthetic four-profile job stopped on profile three with a stored cursor, completed IDs, next profile, zero credits, reset time, and resume command.
- [ ] Run the focused tests and verify failures name the missing transition functions.
- [ ] Implement transitions that mutate only the supplied progress mapping; save remains the caller's explicit durability boundary.
- [ ] Implement case-insensitive OpenAlex header parsing and `/rate-limit` payload parsing.
- [ ] Implement status text containing original command, current/next item, cursor presence, completion count, credits/reset, and resume command.
- [ ] Re-run the focused tests and require all transition/status tests to pass.

### Task 3: Shared CLI controls

**Files:**
- Modify: `scripts/_dataset_cli.py`
- Modify: `tests/test_dataset_scaffolds.py`

**Interfaces:**
- Adds: `--state-dir`, `--resume`, `--status`, `--job-id`, and `--restart` to every stage parser.
- `--status --job-id ID` loads `data/raw/progress/ID.json`, prints `render_status`, and exits without API/config mutation.

- [ ] Extend the CLI test to require all five progress arguments in every numbered script's help output.
- [ ] Add a subprocess test that writes a synthetic checkpoint, invokes a numbered script with `--status`, and verifies the current profile and resume command are printed.
- [ ] Run the two focused test files and verify the new CLI assertions fail.
- [ ] Add parser arguments and status handling before live-stage dispatch; include state directory and resume intent in dry-run plans.
- [ ] Re-run both focused test files and require all tests to pass.

### Task 4: Documentation, ignore policy, and decision log

**Files:**
- Modify: `.gitignore`
- Modify: `config/dataset.yaml`
- Modify: `docs/openalex_collection_guide.md`
- Modify: `docs/decision_log.md`

**Interfaces:**
- Documents the local progress path, state fields, status/resume commands, teammate copy procedure, temporary-failure exit 75, and the OpenAlex reset fields used.

- [ ] Ignore `data/raw/progress/` while leaving immutable source responses outside that ignore rule.
- [ ] Add `paths.progress: data/raw/progress` and checkpoint version to dataset configuration.
- [ ] Add exact status/resume and teammate-copy commands to the collection guide.
- [ ] Record the per-command local checkpoint decision and its limits.

### Task 5: Final verification

**Files:**
- Verify all files above.

**Interfaces:**
- Proves behavior without live API calls or real professor data.

- [ ] Run `.venv/bin/pytest -q` and require zero failures.
- [ ] Run `.venv/bin/ruff check scripts tests` and require zero findings.
- [ ] Run all 12 numbered scripts with `--help` and confirm the progress flags appear.
- [ ] Simulate a rate-limited synthetic job, copy its checkpoint to a second temporary state directory, and confirm status/resume information is identical.
- [ ] Confirm `data/raw/progress/example.json` is ignored and no API-key-shaped value appears in test checkpoints.
- [ ] Run `git diff --check` and report the exact commands for status, resume, and teammate handoff.
