# Resumable OpenAlex Collection Design

**Date:** 2026-07-14
**Status:** Approved direction: local per-command checkpoints

## Goal

Every distinct collection command records exactly where it stopped: script, normalized API setup, current institution or professor, within-profile cursor, completed profiles, rate-limit status, and the exact command needed to continue. The same machine resumes automatically. A teammate can resume after copying the local checkpoint and its partial raw-output directory. No database, shared service, or custom handoff format is required.

## Job identity

Each invocation receives a stable `job_id` derived from SHA-256 over:

- script/stage name;
- dataset and candidate-pool versions;
- API endpoint and normalized filters/options;
- input-file content checksum;
- seed and result limits that affect the records fetched.

The API key, host name, absolute machine paths, timestamps, log path, and presentation-only arguments are excluded. Consequently:

- rerunning the same logical command finds the same checkpoint;
- a different endpoint, filter, input roster, dataset version, or seed creates a separate job;
- moving the repository to a teammate's machine does not change the job ID;
- changing the API key does not invalidate completed work.

## Local state layout

```text
data/raw/
├── progress/
│   └── <job_id>.json
└── <stage-output>/
    ├── <completed-item-id>.jsonl
    └── <partial-item-id>/
```

`data/raw/progress/` is gitignored. State is JSON rather than SQLite so collectors can inspect it directly and a partially copied file cannot corrupt other jobs. Every update uses a temporary file, `fsync`, and atomic rename.

The raw results remain under versioned `data/raw/` stage directories. Completed profiles are stored separately, so resuming never needs to rewrite or refetch them.

## Checkpoint record

Each job JSON contains:

```json
{
  "checkpoint_version": "collection-progress-v1",
  "job_id": "0000000000000000000000000000000000000000000000000000000000000000",
  "stage": "04_fetch_author_works",
  "status": "paused_rate_limit",
  "original_command": ".venv/bin/python scripts/04_fetch_author_works.py --config config/dataset.yaml --input data/interim/verified_professors.csv --output data/raw/author_works --state-dir data/raw/progress",
  "normalized_setup": {
    "endpoint": "works",
    "per_page": 100,
    "dataset_version": "benchmark-v1"
  },
  "input_checksum": "1111111111111111111111111111111111111111111111111111111111111111",
  "current_item_index": 2,
  "total_items": 4,
  "completed_item_ids": ["MOCK-01", "MOCK-02"],
  "current_item": {
    "item_type": "professor",
    "item_id": "MOCK-03",
    "provider_id": "A100000003"
  },
  "current_cursor": "synthetic-openalex-cursor-token",
  "next_item": {
    "item_type": "professor",
    "item_id": "MOCK-04",
    "provider_id": "A100000004"
  },
  "records_written": 230,
  "pages_written": 3,
  "last_success_at": "2026-07-14T12:00:00Z",
  "last_request_hash": "2222222222222222222222222222222222222222222222222222222222222222",
  "rate_limit": {
    "credits_remaining": 0,
    "daily_remaining_usd": 0,
    "resets_at": "2026-07-15T00:00:00Z",
    "resets_in_seconds": 18000
  },
  "resume_command": ".venv/bin/python scripts/04_fetch_author_works.py --config config/dataset.yaml --input data/interim/verified_professors.csv --output data/raw/author_works --state-dir data/raw/progress --resume"
}
```

The example shows field shape only. Implementation tests use synthetic IDs and do not create real professor records.

## Collection transaction

For each institution/professor and each OpenAlex page:

1. Load or create the matching job.
2. Skip IDs listed in `completed_item_ids` whose validated raw output exists.
3. Set `current_item`, `current_item_index`, and the stored cursor.
4. Check cached request hash before making an API request.
5. Make the request with the current cursor.
6. Atomically write the response page or entity result first.
7. Update `records_written`, `pages_written`, `current_cursor`, rate-limit fields, and `last_success_at`.
8. When the provider cursor ends, validate the entity output, add its ID to `completed_item_ids`, clear `current_cursor`, and advance to the next item.
9. Mark `completed` only after all requested items and final output validation pass.

Writing data before the checkpoint makes crash recovery conservative: after a crash, an already-written request hash is reused rather than charged again.

## Rate-limit and failure behavior

OpenAlex reports remaining allowance and reset timing through response headers and `/rate-limit`. The collector records both forms when available.

- `429` with exhausted daily allowance: checkpoint `paused_rate_limit`, save the current item/cursor and reset time, print the resume command, and exit with temporary-failure code 75.
- Short burst throttling or 5xx: bounded exponential backoff, then checkpoint `paused_transient_error` if retries are exhausted.
- Invalid request/authentication: checkpoint `failed_permanent`, retain the current item and error, and exit nonzero without advancing.
- Keyboard interrupt or termination: atomically checkpoint `paused_user` before exit when possible.
- Input/config fingerprint mismatch on resume: refuse and explain which setup changed. A new setup creates a different job instead of corrupting the old one.

The collector never sleeps until the next day's reset. It exits cleanly so another process or teammate can resume later.

## Commands and human-readable status

All OpenAlex collection scripts receive:

```text
--state-dir data/raw/progress
--resume
--status
--job-id <id>
--restart
```

Resume is automatic for a matching incomplete job; `--resume` makes the intent explicit. `--restart` requires `--force` and never deletes prior raw data silently.

`--status` prints the original command, job ID, status, completed/total profiles, current profile or institution, provider ID, cursor presence, record/page counts, credits/reset, next profile, last success, and exact resume command.

## Teammate handoff

After the original collector stops, copy these two things to the same relative paths on the teammate's checkout:

- `data/raw/progress/<job_id>.json`;
- the stage output directory named by the checkpoint.

The teammate sets their own `OPENALEX_API_KEY`, runs the same script with `--status --job-id <job_id>`, and executes the printed resume command. The collector verifies the input/setup fingerprint and existing output checksums before advancing. Collection is sequential: only one person advances a given job at a time. Independent jobs may run concurrently.

## Scope of the first implementation

1. Add the local progress model, stable job fingerprint, atomic checkpoint store, status renderer, and rate-limit state handling.
2. Add common CLI arguments for status/resume/restart.
3. Add a generic per-item cursor collector interface used by OpenAlex stages.
4. Integrate the framework with the first live OpenAlex collection stages as those network bodies are enabled.
5. Test different command setups, same-command resume, mid-profile cursor resume, exhausted credits, crash ordering, status output, and copied-checkpoint handoff without live network calls.

## Non-goals

- Simultaneous writes to one job from multiple machines.
- Storing API keys in checkpoints or bundles.
- Using Git as the progress database.
- Retrying continuously until the next daily reset.
- Treating a checkpoint as evidence that raw output passed final dataset validation.
