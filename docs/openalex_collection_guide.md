# OpenAlex Collection Guide

## What this guide produces

Following this guide produces a versioned institution pool, a 500-1,000-author candidate pool, verified professors, reconciled work records, representative paper selections, and evidence packets. OpenAlex is the discovery backbone, not the sole authority for faculty status, identity, authorship, or publication details.

The scripts currently provide executable CLI contracts, dry-run plans, deterministic shared behavior, abstract reconstruction, and repository validation. Network-specific stage bodies should be implemented against these contracts and reviewed before a live collection run.

## Prerequisites

- Python 3.11 or newer
- Project dependencies installed with `pip install -e ".[dev]"`
- A free OpenAlex API key in `OPENALEX_API_KEY`
- Optional provider credentials in environment variables, never command history or committed files
- A copy of `config/dataset.yaml` pinned to the intended dataset version

Create a local `.env` from `.env.example`, then load it once in each new terminal before running
collection commands:

```bash
set -a
source .env
set +a
```

The real `.env` is ignored by Git. Each collector should create their own file; never send the
credential with a checkpoint or partial dataset.

As checked on 2026-07-14, the OpenAlex developer API requires an API key for list endpoints, allows up to 100 results per page, supports cursor pagination beyond 10,000 results, and reports request cost/rate-limit metadata. Recheck the official [authentication documentation](https://developers.openalex.org/api-reference/authentication) before a live run because API limits can change.

Use `https://api.openalex.org` as the base URL. Relevant official references include [API overview](https://developers.openalex.org/api-reference/introduction), [filter syntax](https://developers.openalex.org/guides/filtering), [works listing](https://developers.openalex.org/api-reference/works/list-works), [author fields](https://developers.openalex.org/api-reference/authors), and [topic behavior](https://help.openalex.org/hc/en-us/articles/24736129405719-Topics).

## Common collection rules

1. Send `api_key` from `OPENALEX_API_KEY`; never serialize it into a URL log or raw record.
2. Use `per_page=100` and cursor pagination (`cursor=*`, then `meta.next_cursor`) for deep result sets.
3. Use `select=` only when the omitted fields are not needed for a later reconciliation step.
4. Batch ID filters with `|` when appropriate and within the provider's current limit.
5. Cache each successful response under `data/raw/cache/` using a hash of the provider, endpoint, and redacted canonical query.
6. Store the unmodified response plus a sidecar containing retrieval timestamp, response status, redacted request, query hash, script version, and checksum.
7. Retry 429 and transient 5xx responses with bounded exponential backoff and jitter. Log terminal failures; do not manufacture empty records.
8. Resume from the last cursor and avoid refetching cached pages unless `--force` is explicitly supplied.
9. Write new output to a temporary file, validate it, then rename atomically. Refuse to overwrite an existing raw file.
10. Use a recorded seed for sampling and deterministic sorted IDs for tie-breaking.

## Local progress and exact resume point

Progress is local and specific to a logical command. A stable `job_id` is derived from the
stage, normalized collection setup, input checksum, dataset/candidate-pool versions, and seed.
Changing an endpoint, filter, input file, or seed creates a different job. Machine paths,
timestamps, and API credentials do not affect the ID, so the same job can move between
teammates' machines.

Each live collection stage must write an atomic checkpoint after every successful API page and
after every completed institution or professor. The checkpoint is
`data/raw/progress/<job_id>.json` and records:

- the redacted original and resume commands;
- the current institution or professor, its provider ID, and its input-list index;
- completed item IDs and the next item;
- the current OpenAlex cursor, pages and records written, and last successful request hash;
- the last observed credit balance/reset time and terminal error.

When OpenAlex returns an exhausted-credit response, the stage must save
`status: paused_rate_limit` and exit with code 75. It must not wait overnight or advance the
cursor past the last successfully persisted page. The official API exposes remaining/reset
information in rate-limit headers and through the
[rate-limit status endpoint](https://developers.openalex.org/api-reference/rate-limits/check-rate-limit-status).

Inspect the stopped job without making an API request:

```bash
.venv/bin/python scripts/04_fetch_author_works.py \
  --status \
  --job-id <JOB_ID> \
  --state-dir data/raw/progress
```

The output names the current professor/profile, saved cursor, next professor, record counts,
credit reset information, and exact redacted resume command. Run that printed command after the
quota resets. `--resume` must verify the input checksum and setup fingerprint before continuing;
use `--restart --force` only to create a separate attempt without deleting prior raw data.

For teammate handoff, copy both of these out of band:

1. `data/raw/progress/<job_id>.json`;
2. the partial stage output directory named in that checkpoint.

The teammate puts them at the same repository-relative paths, sets their own
`OPENALEX_API_KEY`, checks `--status`, and runs the saved resume command. Do not send `.env` or an
API key. Progress checkpoints are ignored by Git because they may expose the private identity
collection order; the raw response/output directory remains the source of truth for completed
pages.

The checkpoint engine and `--status` CLI are implemented. The provider-specific network bodies
in stages 1-4 and 6-11 are still guarded scaffolds; when those bodies are enabled, they must call
the checkpoint transitions before being approved for live collection.

## Stage 0: Verify the configuration and CLI contracts

```bash
python scripts/12_validate_dataset.py --config config/dataset.yaml --dry-run
```

Review `dataset_version`, `random_seed`, targets, paths, and provider settings. No live API call should occur in a dry run.

## Stage 1: Build the institution pool

```bash
python scripts/01_fetch_institutions.py \
  --config config/dataset.yaml \
  --output data/raw/institutions.jsonl \
  --dry-run
```

Start from an explicitly reviewed list of OpenAlex institution IDs or reproducible filters. Do not search only for famous institutions. Seek coverage across the United States/Canada, Europe, East/South/Southeast Asia, Latin America, Africa, and Middle East/Oceania, plus varied institution types and visibility.

For every institution, store:

```text
institution_id, display_name, ROR, country_code, region, institution_type,
works_count, cited_by_count, homepage_url
```

The normalized table is `data/interim/institutions.csv` with the column contract in `docs/dataset_policy.md`. Human-review country/region mappings and homepage URLs. Record unavailable regions rather than guessing.

## Stage 2: Discover a large candidate-author pool

```bash
python scripts/02_fetch_author_candidates.py \
  --config config/dataset.yaml \
  --input data/interim/institutions.csv \
  --output data/raw/author_candidates.jsonl \
  --seed 42 \
  --dry-run
```

Retrieve 500-1,000 raw candidates, not exactly 100. OpenAlex author filters can use last-known institution, works count, citations, ORCID presence, and other supported author fields. Candidate eligibility screening should require at least 8 works, several works with abstracts, recent activity, a plausible institutional association, and usable topics. ORCID is optional.

Store the raw API response and normalize the required `author_candidates.csv` fields. Candidate status is one of `discovered`, `screened_in`, `screened_out`, `needs_identity_review`, `verified`, or `rejected`, with a separate reason field in interim review data.

Do not use a name-only match when an OpenAlex ID can be resolved. Similar names and institutional moves are common sources of merge/split errors.

## Stage 3: Verify current faculty status and identity

```bash
python scripts/03_verify_faculty_status.py \
  --config config/dataset.yaml \
  --input data/interim/author_candidates.csv \
  --output data/interim/faculty_verification_queue.csv \
  --dry-run
```

OpenAlex models authors, not current professors. A human must inspect an official faculty, university, or laboratory page and record:

```text
faculty_status_verified, faculty_page_url, faculty_title,
faculty_page_retrieved_at, career_stage, career_stage_source, identity_notes
```

Compare the page's name, institution, topics, and sample publications against the OpenAlex profile. Use ORCID and official publication lists when available. Reject candidates with unconfirmed roles, materially merged/split profiles, clearly wrong affiliations, or highly ambiguous publication ownership.

Faculty pages can change. Save retrieval dates and a permitted snapshot hash or archive locator, not an unauthorized copy of restricted content.

## Stage 4: Retrieve eligible works

```bash
python scripts/04_fetch_author_works.py \
  --config config/dataset.yaml \
  --input data/interim/verified_professors.csv \
  --output data/raw/author_works.jsonl \
  --dry-run
```

Use the author ID filter on `/works`, not author-name search. Collect at least:

```text
OpenAlex work ID, DOI, title, publication year/date, type, venue,
authors and positions, institutions, abstract_inverted_index, topics,
primary topic, field, subfield, domain, cited_by_count, OA status,
best legal OA URL, language, referenced works, related works when useful
```

Retain retraction/type metadata and define eligibility in the normalized layer. Do not silently drop missing values. Preserve the provider's `authorships` array for reconciliation.

## Stage 5: Reconstruct abstracts

```bash
python scripts/05_reconstruct_abstracts.py \
  --config config/dataset.yaml \
  --input data/raw/author_works.jsonl \
  --output data/interim/author_works_with_abstracts.jsonl \
  --dry-run
```

OpenAlex stores many abstracts as an inverted index mapping each token to one or more integer positions. Reconstruct by placing every token at each position, sorting by position, and joining with spaces. Treat a null index as a missing abstract. Detect duplicate positions; log them as malformed instead of arbitrarily choosing a token. Preserve the original inverted index and add reconstructed text plus a reconstruction version.

Abstract text is evidence for portfolio breadth, but not a complete answer key for methods, results, or limitations.

## Stage 6: Reconcile metadata and ownership

```bash
python scripts/06_reconcile_metadata.py \
  --config config/dataset.yaml \
  --input data/interim/author_works_with_abstracts.jsonl \
  --output data/interim/reconciled_candidate_papers.jsonl \
  --dry-run
```

For selected-paper candidates:

1. Match Crossref by DOI when present.
2. Compare normalized title, year, venue, and author list.
3. Compare author-paper ownership with Semantic Scholar.
4. Use ORCID or an official publication list for remaining ambiguity.
5. Record `ownership_verified`, `verification_sources`, `metadata_conflict`, `conflict_notes`, `doi_verified`, `title_similarity`, and `author_match_status`.

Use transparent similarity rules. For example, Unicode-normalize and case-fold titles, remove punctuation for a comparison copy, and retain the original. A high title score does not override a conflicting DOI or author list. No materially uncertain paper enters a final packet.

## Stage 7: Score candidate papers

```bash
python scripts/07_score_paper_complexity.py \
  --config config/dataset.yaml \
  --input data/interim/reconciled_candidate_papers.jsonl \
  --output data/interim/scored_candidate_papers.jsonl \
  --dry-run
```

Create a 20-30-paper eligible pool per professor. Compute recency, field/year citation percentile, topic cluster, method indicators, all paper-complexity components, OA/abstract/full-text availability, representativeness, and diversity contribution. Normalize features only after the comparison pool and version are fixed.

Do not use citation count in the complexity score. Keep raw and normalized popularity alongside, never inside, complexity.

## Stage 8: Score research portfolios

```bash
python scripts/08_score_research_portfolios.py \
  --config config/dataset.yaml \
  --input data/interim/scored_candidate_papers.jsonl \
  --output data/interim/scored_professor_portfolios.jsonl \
  --dry-run
```

Compute research breadth, automated topic coherence aids, method diversity, aggregate paper complexity, and synthesis-difficulty components. Save embeddings/model identifiers and clustering parameters. Human review finalizes obvious topic corrections, topic coherence, and synthesis difficulty.

## Stage 9: Select representative papers and focal papers

```bash
python scripts/09_select_representative_papers.py \
  --config config/dataset.yaml \
  --input data/interim/scored_candidate_papers.jsonl \
  --output data/interim/candidate_papers.csv \
  --seed 42 \
  --dry-run
```

Select 3 recent, 2 influential, 2 diversifying, and 1 seeded-random eligible paper. Resolve duplicate slots deterministically. Mark two focal papers with legal full text, clear method/result evidence, good representation, and verified ownership. Log every inclusion and exclusion rationale.

## Stage 10: Select the final professor sample

```bash
python scripts/10_stratified_sample_professors.py \
  --config config/dataset.yaml \
  --input data/interim/verified_professors.csv \
  --output data/final/verified_professors.csv \
  --seed 42 \
  --dry-run
```

Enforce hard quality gates, then minimize deviation from domain, career, visibility, breadth, paper-complexity, and synthesis targets. Record target/achieved margins, concentration penalties, seed, tie-break order, algorithm version, candidate-pool version, exclusions, and reasons.

## Stage 11: Extract passages and build evidence packets

For each focal paper, locate legal full text using OpenAlex OA locations or Unpaywall. Collect 2-4 short passages across objective/introduction, methods, results, and discussion/limitations as available. Store exact source and access details. Downloaded PDFs, if needed, stay in `data/private/raw_pdfs/` and are never committed.

```bash
python scripts/11_build_evidence_packets.py \
  --config config/dataset.yaml \
  --input data/final/verified_professors.csv \
  --output data/final/evidence_packets \
  --dry-run
```

Each packet must validate against `schemas/evidence_packet.schema.json`. The internal packet may contain provenance URLs needed for adjudication; any public analysis export must remove direct identity mappings and real names.

## Stage 12: Validate before release or generation

```bash
python scripts/12_validate_dataset.py \
  --config config/dataset.yaml \
  --input data/final/evidence_packets \
  --output data/final/validation_report.json \
  --dry-run
```

Validation covers schema parsing, unique IDs, eight papers, exactly two focal papers, 2-4 passages per focal paper, source URLs and dates, verified authorship, source-ID resolution, absence of committed raw PDFs, and public-output identity checks. A machine pass does not replace human review.

## Failure handling and audit trail

- Record failures as structured log events with stage, redacted request hash, entity ID, exception class, retry count, and timestamp.
- Do not put API keys, full response bodies, names from private maps, or PDF contents in logs.
- Continue past entity-local failures only when the output explicitly records the incomplete entity.
- Stop a release when a hard quality gate fails.
- A rerun uses cache by default. `--force` authorizes a new versioned fetch, not silent overwrite.
- Record code and config versions in the dataset manifest.

## First live collection sequence

Run the first ten-professor test before scaling to hundreds of candidates:

1. Validate configuration and dry-run all stage contracts.
2. Build a small but regionally varied institution seed set.
3. Retrieve enough candidates to verify at least ten professors.
4. Complete all stages for those ten.
5. Apply `docs/first_10_collection_checklist.md`.
6. Log failures and approve, revise, or stop before the full pool.
