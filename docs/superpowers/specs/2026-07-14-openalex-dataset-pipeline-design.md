# OpenAlex-Only Dataset Pipeline Design

**Status:** Approved in conversation on 2026-07-14; awaiting written-spec review  
**Dataset:** `benchmark-v1`  
**Scope:** OpenAlex collection and deterministic derivation only; no live run during implementation

## Objective

Implement the repository's 12-stage dataset pipeline so the team can collect a geographically
and scientifically varied OpenAlex candidate pool, retrieve every candidate's complete OpenAlex
work history, derive provisional benchmark features, select representative papers and a
provisional professor sample, and hand structured enrichment tasks to later Tavily/DataBright
agents.

This release does not claim to verify current faculty status, independently reconcile authorship,
or provide full-text evidence passages. Those remain mandatory gates for a final evidence packet.
The existing 12-professor pilot and strict final evidence-packet schema remain unchanged.

## Release boundary

The deliverable is a valid **OpenAlex collection dataset**, not a release-ready evidence benchmark.
It includes:

- an institution pool;
- 500–1,000 deduplicated author candidates for the full run;
- the complete OpenAlex work history for every collected candidate;
- normalized institution, author, work, topic, authorship, citation, and OA metadata;
- deterministic paper and portfolio features;
- eight provisionally selected papers and two provisional focal candidates per eligible author;
- a provisional constrained sample of approximately 100 authors when the pool supports it;
- one anonymous OpenAlex profile bundle and an explicit enrichment-task list per sampled author;
- collection and provisional-bundle validation reports.

The first live run is capped at ten candidates. Exceeding the cap requires `--full-run`. The
implementation and automated tests make no live API requests.

## Architecture

The existing numbered scripts remain the public interface. Shared implementation lives in
focused modules under `scripts/lib/`:

| Module | Responsibility |
|---|---|
| `openalex_client.py` | Authentication, canonical requests, cursor pagination, retries, rate-limit parsing, and cache lookup |
| `progress.py` | Per-command job identity, atomic checkpoints, status rendering, and resume validation |
| `io.py` | Atomic JSON/JSONL/CSV writes, immutable raw-page paths, checksums, and table reads |
| `normalization.py` | OpenAlex institution, author, work, topic, authorship, source, venue, and OA normalization |
| `features.py` | Lexical paper features, percentile normalization, topic/portfolio features, and controlled method indicators |
| `selection.py` | The 3/2/2/1 paper selector, focal-candidate ranking, and constrained professor sampler |
| `bundles.py` | Provisional profile-bundle construction and stable enrichment tasks |
| `validation.py` | Collection, join, privacy, checkpoint, provisional-schema, and final-readiness validation |

The top-level data flow is:

```text
OpenAlex institutions
  -> reviewed/normalized institution pool
  -> OpenAlex author candidates
  -> complete OpenAlex work histories
  -> normalized author/work records
  -> OpenAlex-internal consistency status
  -> paper and portfolio features
  -> representative paper selection
  -> provisional stratified professor sample
  -> provisional OpenAlex profile bundles
  -> validation and enrichment queues
```

## Storage model

### Raw

Successful API pages are immutable and stored under a job-specific hierarchy such as:

```text
data/raw/openalex/<stage>/<job_id>/<item_id>/<page_hash>.json
```

Each raw page stores the unmodified response and a sidecar or envelope with retrieval time,
redacted canonical request, HTTP status, request hash, response checksum, cursor-in,
cursor-out, client version, and job ID. A cached request hash prevents duplicate paid requests.

Local checkpoints live under `data/raw/progress/<job_id>.json` and remain Git-ignored. Derived
normalized records live under `data/interim/`; selected provisional artifacts live under
`data/final/`. Real identity mappings and downloaded PDFs remain under `data/private/`.

### Provisional bundle schema

Add `schemas/openalex_profile_bundle.schema.json`. It must require:

- schema, dataset, candidate-pool, and bundle versions;
- anonymous `professor_id` and canonical OpenAlex author ID;
- normalized OpenAlex profile and institution metadata;
- OpenAlex-derived visibility and career-estimate inputs;
- separately stored breadth, coherence aids, method diversity, paper complexity, and synthesis
  difficulty aids;
- exactly eight provisionally selected papers when the candidate qualifies;
- exactly two provisional focal-paper IDs;
- provenance and raw-source references;
- OpenAlex-internal consistency status;
- `final_evidence_packet_ready: false`;
- stable `enrichment_tasks` describing every unmet final-quality gate.

The strict `schemas/evidence_packet.schema.json` is not weakened. A provisional bundle must fail
final-evidence readiness until independent verification and focal passages are added.

## Stage behavior

### Stage 1: institutions

Query OpenAlex institution list endpoints using configured region/country and institution-type
filters. Capture all pages, deduplicate by canonical institution ID, and normalize the required
institution table. Regional targets guide candidate-pool diversity but are not claimed as exact
quotas. Unmapped countries or types are retained and flagged instead of guessed.

### Stage 2: candidate authors

For every selected institution, query associated OpenAlex authors and deduplicate by canonical
author ID. Record every institution through which an author was discovered. Apply only observable
screening rules: at least eight works, recent activity, usable topic metadata, plausible OpenAlex
institutional association, and abstract-availability statistics. ORCID is optional.

Set `faculty_status_verified` to false and `quality_status` to `needs_enrichment`. OpenAlex author
records are not described as verified professors.

### Stage 3: enrichment queue

Transform candidates into an identity/faculty review queue. Generate stable anonymous candidate
IDs and enrichment tasks without scraping pages or changing eligibility to verified. Preserve the
canonical author ID, profile URL, last-known institutions, topic summary, work/citation statistics,
ORCID if present, first/last publication years, and suspected merge/split indicators.

### Stage 4: complete work histories

For each collected author, cursor through all works associated with the canonical author ID. Do
not stop at the eventual 20–30-paper selection pool. Store the complete response fields needed by
the OpenAlex guide: IDs, DOI, title, dates, type, venue/source, authorships and positions,
institutions, inverted abstract, topics and hierarchy, citation counts, OA locations and status,
language, referenced works, and related works.

Referenced-work IDs are retained, but their full records are not recursively fetched unless they
are already in a candidate's work history. This bounds collection while preserving future links.

### Stage 5: abstracts

Reconstruct abstract text from the inverted index by sorting tokens by position. Null remains
missing; duplicate positions are an explicit malformed-record error. Preserve both the original
index and a reconstruction-version field.

### Stage 6: OpenAlex consistency

Perform within-provider checks only: canonical author ownership, duplicate work IDs, conflicting
DOI/title pairs, inconsistent authorship entries, implausible profile/topic mixtures, and overlap
with other collected author profiles. Assign `openalex_consistent`, `needs_identity_review`, or
`needs_metadata_enrichment`. Do not set externally verified ownership fields.

### Stage 7: paper features

Use title and reconstructed abstract text to compute raw lexical features, then normalized
components and the documented 25/20/15/15/15/10 paper-complexity score. Store raw counts,
normalization strata, unavailable components, and score version. Controlled indicators cover
method families, datasets/populations, experiments/results, research objectives, technical
vocabulary, readability, interdisciplinary topic breadth, and qualification/hedging. These are
operational heuristics, not claims of scientific merit.

Popularity remains separate and includes raw citations plus field/year percentile ranks.

### Stage 8: portfolio features

Aggregate complete histories and candidate-paper pools into topic entropy, unique topic/field/
subfield counts, topic clusters, coherence aids, method count/entropy, collaboration measures,
temporal publication span and evolution, OA rate, paper-complexity distribution, and synthesis-
difficulty components. Automated coherence and synthesis outputs are aids labelled for later
human review, not final labels.

### Stage 9: papers and focal candidates

Derive a 20–30-paper eligible pool from each complete history, then deterministically allocate
eight unique papers: three recent, two influential by normalized popularity, two maximizing
marginal topic/method coverage, and one seeded random remaining paper. Resolve slot collisions by
advancing within the relevant ranked list. Rank two provisional focal candidates using OA/full-
text location metadata, abstract availability, topic representation, and OpenAlex consistency.
Do not create passage text.

### Stage 10: provisional professor sample

Filter on OpenAlex-available collection gates and select up to the configured target using a seeded
optimizer that minimizes normalized absolute target-margin deviation plus institution/region
concentration penalties. Domain targets are hard only when the eligible pool supports them.
Unavailable human-reviewed dimensions are recorded as provisional aids or excluded from the
objective. Persist target and achieved distributions, exclusions, reasons, seed, candidate-pool
version, and algorithm version.

### Stage 11: bundles

Build anonymous OpenAlex profile bundles, not strict evidence packets. Include profile metadata,
selected papers, focal candidates, score components, provenance, consistency findings, and the
following stable enrichment-task types as applicable:

```text
verify_faculty_status
resolve_author_identity
reconcile_crossref_metadata
reconcile_semantic_scholar_ownership
retrieve_legal_full_text
extract_focal_passages
review_topic_coherence
review_synthesis_difficulty
```

Future agents append versioned enrichment results; they never edit immutable OpenAlex raw pages.

### Stage 12: validation

Validate configuration, JSON Schemas, file existence/checksums, unique IDs, input/output joins,
complete checkpoint state, work-history completeness markers, deterministic selection counts,
anonymity, secret absence, prohibited PDF commits, bundle schema, and enrichment-task coverage.
Report these separately:

- `openalex_collection_valid`;
- `provisional_bundle_valid`;
- `final_evidence_packet_ready` (false until all strict gates pass).

## CLI contract and safety gate

All numbered scripts share:

```text
--config --input --output --cache-dir --state-dir --limit --seed --dry-run
--resume --status --job-id --restart --force --full-run
```

Stages that collect or process author profiles default to at most ten candidates. A request to
collect or process more than ten authors requires `--full-run`. Stage 1 instead uses an explicit
institution limit because a geographically useful seed pool may need more than ten institutions.
Dry runs print the normalized execution plan and consume no API credits.

Every logical command receives a stable job ID derived from stage, normalized non-secret setup,
input checksum, dataset/candidate-pool versions, limit, and seed. Changing those values creates a
different job. API keys, absolute machine paths, timestamps, and presentation-only arguments do
not affect job identity.

## Checkpoint and recovery semantics

After every successful page:

1. validate the response shape;
2. atomically persist the immutable raw page;
3. atomically update the checkpoint with item, cursor-out, page/record counts, response checksum,
   request hash, and last-success time;
4. only then request the next page.

The checkpoint also stores completed item IDs, the next item, the redacted original/resume command,
and observed rate-limit/reset metadata. A resumed command verifies its setup fingerprint, input
checksum, and existing output/raw-page checksums.

On exhausted credits, save `paused_rate_limit` and exit 75 without advancing beyond the last
persisted page. Bounded exponential backoff handles transient transport and 5xx failures.
Authentication/authorization failures, malformed JSON, incompatible response shapes, and permanent
4xx failures stop the job with a diagnostic; none are converted into empty results.

For teammate handoff, copy the job checkpoint and its job-specific raw/output directory. The
teammate supplies a separate key and runs status before the saved resume command. Only one machine
advances a given job at a time.

## OpenAlex client behavior

The client uses `OPENALEX_API_KEY`, the configured base URL, `per_page=100`, and cursor pagination.
Requests use a canonical redacted hash for cache identity. API keys never appear in logs, raw
envelopes, commands, checkpoints, or dataset manifests. Retry limits, timeout, user-agent/contact
metadata, and client version are configurable and recorded without secrets.

No automated test connects to OpenAlex. Tests inject a local fake transport with representative
success, pagination, duplicate, malformed, transient-error, authentication-error, and exhausted-
credit responses.

## Testing strategy

Implementation follows test-first development. Synthetic OpenAlex fixtures use unmistakably fake
IDs and people. Coverage includes:

- canonical requests, secret redaction, cache hits, cursor pagination, and retry classification;
- page-before-checkpoint atomicity and exact item/cursor resumption;
- cross-directory checkpoint copying and setup/input mismatch rejection;
- ten-candidate gate and `--full-run` override;
- institution, author, work, topic, authorship, source, and OA normalization;
- complete work-history iteration without recursive referenced-work fetching;
- deterministic abstract reconstruction and malformed-index handling;
- paper feature formulas, missing-feature behavior, and percentile normalization;
- portfolio aggregation, entropy, clustering, and score-component separation;
- unique 3/2/2/1 selection, focal ranking, and seeded reproducibility;
- constrained sample reproducibility and achieved-margin reporting;
- provisional schema validation and strict final-readiness rejection;
- absence of credentials, raw PDFs, and real identity mappings from public artifacts;
- every numbered script's help, dry run, failure handling, and no-overwrite behavior.

## Operator workflow

The documented operator path is:

1. load the local environment and validate `credential_present` in a dry run;
2. run repository/config validation;
3. run Stage 1 with a bounded institution target;
4. inspect and accept the normalized institution pool;
5. run Stages 2–12 with the default ten-candidate safety gate;
6. inspect checkpoints, completeness, score distributions, selections, bundles, and validation;
7. record the first-ten GO/REVISE/STOP decision;
8. rerun network stages with `--full-run` only after GO;
9. hand enrichment tasks to later Tavily/DataBright agents;
10. build strict final evidence packets only after all mandatory enrichment gates pass.

## Constraints and non-goals

- Do not send generated outreach emails.
- Do not infer sensitive demographic traits.
- Do not scrape faculty pages or call Crossref, Semantic Scholar, Unpaywall, Tavily, or DataBright
  in this release.
- Do not download or commit full PDFs.
- Do not call an OpenAlex author a verified professor.
- Do not describe OpenAlex-internal consistency as independent authorship verification.
- Do not fabricate missing abstracts, full-text evidence, passages, review outcomes, or final labels.
- Do not weaken the existing final evidence-packet quality gates.
- Do not make live API calls during implementation or automated verification.

## Acceptance criteria

The implementation is accepted when:

1. all 12 scripts have functional OpenAlex-only or deterministic local behavior appropriate to
   their stage;
2. network stages use cache, checkpoints, exact resume, credit-exhaustion exit 75, and the ten-item
   safety gate;
3. complete candidate work histories are retained and can be reprocessed without API calls;
4. all derived scores store components and remain separated by construct;
5. paper selection and provisional sampling are deterministic for a supplied seed;
6. provisional bundles validate against their own schema and explicitly fail final readiness;
7. later enrichment agents receive stable, complete task records;
8. tests use only synthetic fixtures and make no network calls;
9. lint, tests, schema/config parsing, help checks, secret scans, and dry runs pass;
10. operator documentation gives exact ten-candidate, status, resume, and full-run commands.
