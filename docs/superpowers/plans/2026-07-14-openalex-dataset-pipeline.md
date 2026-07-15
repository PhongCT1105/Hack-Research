# OpenAlex-Only Dataset Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all 12 dataset stages as a resumable OpenAlex-only pipeline that collects complete candidate work histories, produces deterministic provisional benchmark bundles, and never claims missing external verification.

**Architecture:** Keep the numbered scripts as stable entry points and move reusable behavior into focused `scripts/lib/` modules. Network stages use an injected transport, immutable raw-page cache, and page-level checkpoints; local stages transform JSONL/CSV deterministically and write atomically. Strict final evidence schemas remain unchanged while a new provisional OpenAlex bundle schema supports later Tavily/DataBright enrichment.

**Tech Stack:** Python 3.11+, standard-library `urllib`, PyYAML, Pydantic, `jsonschema`, pytest, Ruff, JSON/JSONL/CSV, OpenAlex REST API.

## Global Constraints

- Preserve the 12-professor pilot and its frozen runtime contracts.
- This implementation uses OpenAlex only and makes no Tavily, DataBright, Crossref, Semantic Scholar, Unpaywall, or scraping requests.
- Automated tests and implementation verification must make zero live network calls.
- Complete OpenAlex work histories are retained for each collected author; referenced-work records are not recursively fetched.
- Author-processing stages default to ten candidates and require `--full-run` to exceed ten.
- Raw pages are immutable, checkpoints are atomic, and exhausted credits save state before exit code 75.
- API keys never enter logs, commands, checkpoints, manifests, cache identities, or output records.
- Provisional bundles set `final_evidence_packet_ready` to false and do not fabricate faculty verification, external authorship verification, passages, or human labels.
- Use only synthetic names and unmistakably fake OpenAlex IDs in tests and fixtures.

---

## File map

New shared modules:

- `scripts/lib/config.py`: typed access to dataset and OpenAlex settings.
- `scripts/lib/io.py`: atomic JSON/JSONL/CSV operations and immutable raw envelopes.
- `scripts/lib/openalex_client.py`: transport, request canonicalization, pagination, cache, retries, and API error classes.
- `scripts/lib/progress.py`: compatibility exports plus resume/setup validation.
- `scripts/lib/runner.py`: durable item/page collection loop.
- `scripts/lib/normalization.py`: institution, author, and work normalization.
- `scripts/lib/features.py`: paper and portfolio features.
- `scripts/lib/selection.py`: representative papers, focal candidates, and constrained sample.
- `scripts/lib/bundles.py`: anonymous provisional bundles and enrichment tasks.
- `scripts/lib/validation.py`: collection, provisional-schema, privacy, and readiness checks.

Compatibility files `scripts/_dataset_cli.py` and `scripts/_collection_progress.py` remain importable while delegating to the shared modules. Each numbered script owns only argument-to-stage orchestration.

Synthetic fixtures live under `tests/fixtures/openalex/`. Tests are split by module and stage so every task has an isolated red-green cycle.

---

### Task 1: Shared CLI, configuration, and safety gate

**Files:**
- Create: `scripts/lib/__init__.py`
- Create: `scripts/lib/config.py`
- Create: `scripts/lib/io.py`
- Modify: `scripts/_dataset_cli.py`
- Modify: `config/dataset.yaml`
- Test: `tests/test_cli_and_config.py`

**Interfaces:**
- Produces: `DatasetConfig.load(path)`, `OpenAlexSettings`, `atomic_write_json`, `atomic_write_jsonl`, `atomic_write_csv`, `read_jsonl`, `read_csv`, `input_checksum`, `enforce_author_limit(limit, full_run)`.
- Consumes: existing YAML keys and existing atomic-write behavior.

- [ ] **Step 1: Write failing CLI/config tests**

```python
def test_author_limit_requires_full_run():
    with pytest.raises(ValueError, match="--full-run"):
        enforce_author_limit(11, full_run=False)
    assert enforce_author_limit(11, full_run=True) == 11

def test_dry_run_exposes_new_operational_flags(tmp_path):
    result = run_script("02_fetch_author_candidates.py", "--dry-run", "--limit", "10")
    assert result.returncode == 0
    plan = json.loads(result.stdout)
    assert plan["limit"] == 10
    assert plan["full_run"] is False
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `.venv/bin/pytest tests/test_cli_and_config.py -v`
Expected: failures because the modules and `--limit`/`--full-run` flags do not exist.

- [ ] **Step 3: Implement typed config, atomic I/O, and flags**

Add `--limit` as a positive integer and `--full-run` as a boolean flag. Implement:

```python
def enforce_author_limit(limit: int | None, full_run: bool, safe_limit: int = 10) -> int:
    resolved = safe_limit if limit is None else limit
    if resolved < 1:
        raise ValueError("--limit must be at least 1")
    if resolved > safe_limit and not full_run:
        raise ValueError(f"author limit above {safe_limit} requires --full-run")
    return resolved
```

Extend configuration with explicit institution seed countries/types, recent-activity year,
OpenAlex mailto/user-agent, raw envelope version, safe author limit, and bundle version. Keep secrets
as environment-variable names only.

- [ ] **Step 4: Run focused and existing scaffold tests**

Run: `.venv/bin/pytest tests/test_cli_and_config.py tests/test_dataset_scaffolds.py -v`
Expected: all tests pass and all 12 help screens include `--limit` and `--full-run`.

- [ ] **Step 5: Commit the independently testable CLI foundation**

```bash
git add scripts/lib scripts/_dataset_cli.py config/dataset.yaml tests/test_cli_and_config.py tests/test_dataset_scaffolds.py
git commit -m "feat: add dataset pipeline CLI safety controls"
```

---

### Task 2: OpenAlex client, cache, and error classification

**Files:**
- Create: `scripts/lib/openalex_client.py`
- Create: `tests/fixtures/openalex/institutions_page_1.json`
- Create: `tests/fixtures/openalex/institutions_page_2.json`
- Create: `tests/test_openalex_client.py`

**Interfaces:**
- Produces: `HttpResponse`, `Transport` protocol, `UrllibTransport`, `OpenAlexClient`, `OpenAlexError`, `AuthenticationError`, `PermanentRequestError`, `MalformedResponseError`, `RateLimitExhausted`, `TransientOpenAlexError`.
- `OpenAlexClient.iter_pages(endpoint, params, start_cursor="*") -> Iterator[Page]` returns validated results, meta, cursor-in/out, request hash, rate-limit metadata, and cache status.

- [ ] **Step 1: Write failing transport/client tests**

```python
def test_cursor_pagination_uses_next_cursor_and_redacts_key(fake_transport, tmp_path):
    client = OpenAlexClient(settings(), fake_transport, tmp_path)
    pages = list(client.iter_pages("institutions", {"filter": "country_code:CA"}))
    assert [page.cursor_in for page in pages] == ["*", "cursor-2"]
    assert [len(page.results) for page in pages] == [2, 1]
    assert "secret" not in json.dumps([page.request for page in pages])

def test_429_raises_rate_limit_with_reset(fake_transport_429, tmp_path):
    with pytest.raises(RateLimitExhausted) as caught:
        next(OpenAlexClient(settings(), fake_transport_429, tmp_path).iter_pages("authors", {}))
    assert caught.value.rate_limit["credits_remaining"] == 0
```

- [ ] **Step 2: Run client tests and confirm RED**

Run: `.venv/bin/pytest tests/test_openalex_client.py -v`
Expected: import failure for `scripts.lib.openalex_client`.

- [ ] **Step 3: Implement the injected client**

Use `urllib.request` only inside `UrllibTransport`. Canonicalize sorted non-secret parameters,
append the real key only at transport time, validate `results` and `meta`, parse rate-limit headers,
and classify 401/403, 429, retryable 5xx/transport failures, permanent 4xx, and malformed JSON.
Cache successful parsed responses by redacted request hash and never retry a cache hit.

- [ ] **Step 4: Verify pagination, cache reuse, retry bounds, and secret scan**

Run: `.venv/bin/pytest tests/test_openalex_client.py -v`
Expected: tests pass; the fake transport call count does not increase on a cache hit.

- [ ] **Step 5: Commit the client**

```bash
git add scripts/lib/openalex_client.py tests/fixtures/openalex tests/test_openalex_client.py
git commit -m "feat: add cached OpenAlex cursor client"
```

---

### Task 3: Durable page runner and exact resume validation

**Files:**
- Create: `scripts/lib/progress.py`
- Create: `scripts/lib/runner.py`
- Modify: `scripts/_collection_progress.py`
- Test: `tests/test_collection_runner.py`
- Modify: `tests/test_collection_progress.py`

**Interfaces:**
- Produces: `CollectionJob.create_or_resume(...)`, `CollectionJob.collect_items(...)`, `ResumeMismatchError`, `RawPageStore.persist(page, item_id)`.
- Preserves all existing `_collection_progress` imports through compatibility re-exports.

- [ ] **Step 1: Write failing durability and mismatch tests**

```python
def test_raw_page_is_persisted_before_cursor_advances(tmp_path, two_page_client):
    job = synthetic_job(tmp_path, two_page_client)
    job.collect_items([mock_author("A100000001")], endpoint_for_author)
    checkpoint = load_checkpoint(tmp_path)
    assert len(list((tmp_path / "raw").rglob("*.json"))) == 2
    assert checkpoint["current_cursor"] is None
    assert checkpoint["completed_item_ids"] == ["MOCK-01"]

def test_resume_rejects_changed_input_checksum(tmp_path):
    create_paused_job(tmp_path, input_checksum="first")
    with pytest.raises(ResumeMismatchError, match="input checksum"):
        resume_job(tmp_path, input_checksum="second")
```

- [ ] **Step 2: Run runner tests and confirm RED**

Run: `.venv/bin/pytest tests/test_collection_runner.py -v`
Expected: missing runner/job interfaces.

- [ ] **Step 3: Implement page-before-checkpoint ordering**

The runner must persist and checksum a raw envelope before calling `record_page`. On
`RateLimitExhausted`, merge rate metadata, save `paused_rate_limit`, and raise a process-level
exception carrying exit code 75. Resume validates checkpoint version, normalized setup, input
checksum, and every referenced raw-page checksum.

- [ ] **Step 4: Run progress and runner suites**

Run: `.venv/bin/pytest tests/test_collection_progress.py tests/test_collection_runner.py -v`
Expected: all old compatibility behavior and new exact-resume behavior pass.

- [ ] **Step 5: Commit durable collection orchestration**

```bash
git add scripts/lib/progress.py scripts/lib/runner.py scripts/_collection_progress.py tests/test_collection_progress.py tests/test_collection_runner.py
git commit -m "feat: add durable resumable collection runner"
```

---

### Task 4: OpenAlex normalization contracts

**Files:**
- Create: `scripts/lib/normalization.py`
- Create: `tests/fixtures/openalex/authors_page.json`
- Create: `tests/fixtures/openalex/works_page.json`
- Create: `tests/test_openalex_normalization.py`

**Interfaces:**
- Produces: `canonical_openalex_id`, `normalize_institution`, `normalize_author`, `normalize_work`, `author_candidate_status`, and stable CSV column constants.
- Consumes raw OpenAlex dictionaries without mutating them.

- [ ] **Step 1: Write failing normalization tests**

```python
def test_work_normalization_preserves_complete_evidence_fields(work_fixture):
    work = normalize_work(work_fixture, professor_id="MOCK-01")
    assert work["openalex_work_id"] == "W100000001"
    assert work["abstract_inverted_index"] == {"Synthetic": [0], "abstract": [1]}
    assert work["topics"][0]["field"] == "Computer Science"
    assert work["authorships"][0]["author_position"] == "first"
    assert work["referenced_works"] == ["W100000099"]
```

- [ ] **Step 2: Run normalization tests and confirm RED**

Run: `.venv/bin/pytest tests/test_openalex_normalization.py -v`
Expected: missing normalization module.

- [ ] **Step 3: Implement loss-aware normalizers**

Normalize IDs to short canonical forms while preserving provider URLs separately. Retain missing
values as null/empty collections, preserve all authorships/topic hierarchy/OA locations, and
derive first/last publication years only from supplied OpenAlex summary fields.

- [ ] **Step 4: Run fixture normalization tests**

Run: `.venv/bin/pytest tests/test_openalex_normalization.py -v`
Expected: deterministic normalized dictionaries match the field contracts.

- [ ] **Step 5: Commit normalization**

```bash
git add scripts/lib/normalization.py tests/fixtures/openalex tests/test_openalex_normalization.py
git commit -m "feat: normalize OpenAlex collection records"
```

---

### Task 5: Functional Stage 1 institution collection

**Files:**
- Modify: `scripts/01_fetch_institutions.py`
- Create: `tests/test_stage_01_institutions.py`
- Modify: `config/dataset.yaml`

**Interfaces:**
- Produces raw job pages, `data/interim/institutions.csv`, and an institution collection summary.
- Uses `OpenAlexClient`, `CollectionJob`, and `normalize_institution`.

- [ ] **Step 1: Write a failing fixture-driven Stage 1 test**

```python
def test_stage_1_deduplicates_and_writes_normalized_pool(tmp_path, fake_client):
    result = collect_institutions(config(), fake_client, tmp_path, limit=3)
    assert [row["openalex_id"] for row in result.rows] == ["I100000001", "I100000002"]
    assert result.summary["regions represented"] >= 2
    assert result.job_id
```

- [ ] **Step 2: Run Stage 1 test and confirm RED**

Run: `.venv/bin/pytest tests/test_stage_01_institutions.py -v`
Expected: `collect_institutions` is absent.

- [ ] **Step 3: Implement Stage 1 orchestration**

Build configured OpenAlex filters per country/type, paginate through results, deduplicate canonical
IDs, retain discovery filters, sort deterministically, and atomically write normalized CSV plus a
JSON summary. `--dry-run` prints filters and estimated jobs without constructing a client.

- [ ] **Step 4: Verify Stage 1 without network**

Run: `.venv/bin/pytest tests/test_stage_01_institutions.py tests/test_openalex_client.py -v`
Expected: Stage 1 passes using only the fake client.

- [ ] **Step 5: Commit Stage 1**

```bash
git add scripts/01_fetch_institutions.py config/dataset.yaml tests/test_stage_01_institutions.py
git commit -m "feat: implement OpenAlex institution collection"
```

---

### Task 6: Functional Stages 2 and 3 candidate discovery and enrichment queue

**Files:**
- Modify: `scripts/02_fetch_author_candidates.py`
- Modify: `scripts/03_verify_faculty_status.py`
- Create: `tests/test_stage_02_03_candidates.py`

**Interfaces:**
- Stage 2 produces raw author pages and `data/interim/author_candidates.csv`.
- Stage 3 produces `data/interim/faculty_identity_enrichment_queue.csv` with stable anonymous IDs and `needs_enrichment` status.

- [ ] **Step 1: Write failing deduplication, gate, and queue tests**

```python
def test_author_found_at_two_institutions_is_one_candidate(fake_client, tmp_path):
    result = collect_candidates(two_institutions(), fake_client, tmp_path, limit=10)
    assert len(result.rows) == 1
    assert result.rows[0]["discovery_institution_ids"] == "I100000001|I100000002"
    assert result.rows[0]["faculty_status_verified"] == "false"

def test_queue_uses_stable_anonymous_id(candidate_rows):
    first = build_enrichment_queue(candidate_rows, "candidate-pool-v1")
    second = build_enrichment_queue(candidate_rows, "candidate-pool-v1")
    assert first[0]["professor_id"] == second[0]["professor_id"]
    assert first[0]["quality_status"] == "needs_enrichment"
```

- [ ] **Step 2: Run Stages 2/3 tests and confirm RED**

Run: `.venv/bin/pytest tests/test_stage_02_03_candidates.py -v`
Expected: collection and queue functions are absent.

- [ ] **Step 3: Implement author discovery and deterministic queue**

Query authors by institution ID, preserve every discovery institution, stop after the deduplicated
candidate limit, and apply only OpenAlex-observable eligibility. Generate anonymous IDs from domain
prefix plus a candidate-pool-versioned deterministic rank; put the real mapping only in the ignored
private identity map while public/provisional outputs use the anonymous ID.

- [ ] **Step 4: Verify safety gate and no-name public queue**

Run: `.venv/bin/pytest tests/test_stage_02_03_candidates.py tests/test_cli_and_config.py -v`
Expected: >10 candidates fails without `--full-run`; public queue fixtures contain no display name.

- [ ] **Step 5: Commit Stages 2/3**

```bash
git add scripts/02_fetch_author_candidates.py scripts/03_verify_faculty_status.py tests/test_stage_02_03_candidates.py
git commit -m "feat: collect OpenAlex author candidates"
```

---

### Task 7: Functional Stages 4 and 5 complete work histories

**Files:**
- Modify: `scripts/04_fetch_author_works.py`
- Modify: `scripts/05_reconstruct_abstracts.py`
- Create: `tests/test_stage_04_05_works.py`

**Interfaces:**
- Stage 4 produces job-specific raw pages, normalized `author_works.jsonl`, and per-author completeness markers.
- Stage 5 produces `author_works_with_abstracts.jsonl` while retaining original inverted indexes.

- [ ] **Step 1: Write failing complete-history and resume tests**

```python
def test_stage_4_fetches_every_page_but_not_referenced_work_records(fake_works_client, tmp_path):
    result = collect_author_works([mock_candidate()], fake_works_client, tmp_path, limit=10)
    assert result.completeness["MOCK-01"]["page_count"] == 2
    assert result.completeness["MOCK-01"]["work_count"] == 3
    assert "W100000099" in result.works[0]["referenced_works"]
    assert all(call.endpoint == "works" for call in fake_works_client.calls)
```

- [ ] **Step 2: Run work-stage tests and confirm RED**

Run: `.venv/bin/pytest tests/test_stage_04_05_works.py -v`
Expected: Stage 4 collector is absent.

- [ ] **Step 3: Implement all-page author work collection**

Use `filter=author.id:<canonical_id>`, cursor until `next_cursor` is null, normalize every work, and
write a completeness record containing first/last cursor, pages, works, raw hashes, and
`collection_complete: true`. Resume a partially collected author from the saved cursor and merge
normalized pages by work ID without re-requesting persisted pages.

- [ ] **Step 4: Verify stages and abstract regression suite**

Run: `.venv/bin/pytest tests/test_stage_04_05_works.py tests/test_dataset_scaffolds.py -v`
Expected: complete histories and existing abstract behaviors pass.

- [ ] **Step 5: Commit Stages 4/5**

```bash
git add scripts/04_fetch_author_works.py scripts/05_reconstruct_abstracts.py tests/test_stage_04_05_works.py
git commit -m "feat: collect complete OpenAlex work histories"
```

---

### Task 8: Functional Stage 6 OpenAlex consistency assessment

**Files:**
- Modify: `scripts/06_reconcile_metadata.py`
- Create: `tests/test_stage_06_consistency.py`

**Interfaces:**
- Produces `consistency_status`, machine-readable issue codes, and non-final reconciliation fields for every candidate work/profile.

- [ ] **Step 1: Write failing consistency tests**

```python
def test_conflicting_doi_titles_need_metadata_enrichment():
    rows = [work("W1", doi="10.1/mock", title="First"), work("W2", doi="10.1/mock", title="Other")]
    result = assess_openalex_consistency(rows, expected_author_id="A100000001")
    assert result.status == "needs_metadata_enrichment"
    assert "conflicting_doi_titles" in result.issue_codes
    assert result.externally_verified is False
```

- [ ] **Step 2: Run Stage 6 tests and confirm RED**

Run: `.venv/bin/pytest tests/test_stage_06_consistency.py -v`
Expected: consistency assessor is absent.

- [ ] **Step 3: Implement within-provider checks**

Check expected author presence, duplicate IDs, DOI/title conflicts, inconsistent author entries,
topic-mixture warnings, and cross-profile work overlap. Never write `ownership_verified: true` or
external source claims.

- [ ] **Step 4: Run Stage 6 tests**

Run: `.venv/bin/pytest tests/test_stage_06_consistency.py -v`
Expected: consistent, identity-review, and metadata-enrichment cases pass.

- [ ] **Step 5: Commit Stage 6**

```bash
git add scripts/06_reconcile_metadata.py tests/test_stage_06_consistency.py
git commit -m "feat: assess OpenAlex metadata consistency"
```

---

### Task 9: Functional Stage 7 paper features and complexity

**Files:**
- Create: `scripts/lib/features.py`
- Modify: `scripts/07_score_paper_complexity.py`
- Create: `tests/test_paper_features.py`

**Interfaces:**
- Produces: `extract_paper_features(text, topics)`, `percentile_rank`, `score_paper_complexity`, and controlled keyword dictionaries versioned as `paper-features-v1`.

- [ ] **Step 1: Write failing formula and missing-text tests**

```python
def test_complexity_uses_documented_weights():
    components = ComplexityComponents(100, 50, 40, 20, 80, 60, 2, 0.1)
    assert score_paper_complexity(components) == pytest.approx(62.0)

def test_missing_abstract_is_explicit_not_zero():
    result = extract_paper_features(None, topics=[])
    assert result.available is False
    assert result.technical_vocabulary_density is None
```

- [ ] **Step 2: Run paper-feature tests and confirm RED**

Run: `.venv/bin/pytest tests/test_paper_features.py -v`
Expected: feature interfaces are absent.

- [ ] **Step 3: Implement deterministic lexical features and normalization**

Tokenize with standard-library Unicode-aware expressions. Store raw counts and densities, apply
controlled method/dataset/result/objective/hedging indicators, compute readability from sentence/
word/syllable approximations, normalize within field/year strata with documented fallback, and
keep popularity percentiles outside the complexity score.

- [ ] **Step 4: Verify formulas and deterministic output**

Run: `.venv/bin/pytest tests/test_paper_features.py -v`
Expected: exact formula, missingness, percentile ties, and repeatability tests pass.

- [ ] **Step 5: Commit Stage 7**

```bash
git add scripts/lib/features.py scripts/07_score_paper_complexity.py tests/test_paper_features.py
git commit -m "feat: score OpenAlex paper complexity features"
```

---

### Task 10: Functional Stage 8 portfolio features

**Files:**
- Modify: `scripts/08_score_research_portfolios.py`
- Create: `tests/test_portfolio_features.py`

**Interfaces:**
- Produces: `topic_entropy`, `method_entropy`, `build_topic_clusters`, `score_portfolio`, and separately named breadth/coherence-aid/method/complexity/synthesis component dictionaries.

- [ ] **Step 1: Write failing separation and entropy tests**

```python
def test_broad_portfolio_can_still_have_high_coherence_aid():
    result = score_portfolio(related_multi_field_papers())
    assert result["research_breadth"]["score"] > 0.5
    assert result["topic_coherence_aid"]["score"] > 0.5
    assert "synthesis_difficulty" in result
    assert result["topic_coherence_aid"]["human_reviewed"] is False
```

- [ ] **Step 2: Run portfolio tests and confirm RED**

Run: `.venv/bin/pytest tests/test_portfolio_features.py -v`
Expected: portfolio scorer is absent.

- [ ] **Step 3: Implement topic-based deterministic portfolio aggregation**

Use OpenAlex topic IDs/hierarchy for entropy and cluster grouping; no embedding dependency is added
in this release. Compute temporal, collaboration, OA, method, dataset/population, and complexity
distributions. Apply the documented synthesis weights only to available normalized components and
record the denominator/missing components.

- [ ] **Step 4: Verify construct separation**

Run: `.venv/bin/pytest tests/test_portfolio_features.py -v`
Expected: breadth, coherence aid, method diversity, paper complexity, synthesis aid, visibility,
and evidence completeness remain distinct outputs.

- [ ] **Step 5: Commit Stage 8**

```bash
git add scripts/08_score_research_portfolios.py tests/test_portfolio_features.py
git commit -m "feat: score OpenAlex research portfolios"
```

---

### Task 11: Functional Stage 9 representative and focal selection

**Files:**
- Create: `scripts/lib/selection.py`
- Modify: `scripts/09_select_representative_papers.py`
- Create: `tests/test_paper_selection.py`

**Interfaces:**
- Produces: `select_candidate_pool`, `select_representative_papers(papers, seed)`, and `select_focal_candidates(selected)`.

- [ ] **Step 1: Write failing slot and reproducibility tests**

```python
def test_selector_returns_unique_three_two_two_one_allocation():
    selected = select_representative_papers(thirty_papers(), seed=42)
    assert len(selected) == 8
    assert len({paper["paper_id"] for paper in selected}) == 8
    assert Counter(paper["selection_reason"] for paper in selected) == {
        "recent": 3, "influential": 2, "diversifying": 2, "random": 1
    }
    assert [p["paper_id"] for p in selected] == [p["paper_id"] for p in select_representative_papers(thirty_papers(), seed=42)]
```

- [ ] **Step 2: Run selection tests and confirm RED**

Run: `.venv/bin/pytest tests/test_paper_selection.py -v`
Expected: selection module is absent.

- [ ] **Step 3: Implement deterministic collision resolution and focal ranking**

Rank recency and influence independently, greedily maximize new topic/method coverage for
diversifying slots, and draw the random slot from a sorted remaining list with `random.Random(seed)`.
Focal rank combines OA location, abstract availability, consistency, and coverage; it never claims
that full text was inspected.

- [ ] **Step 4: Run selection tests**

Run: `.venv/bin/pytest tests/test_paper_selection.py -v`
Expected: slot counts, uniqueness, collision fallbacks, insufficient-paper errors, and seeded output pass.

- [ ] **Step 5: Commit Stage 9**

```bash
git add scripts/lib/selection.py scripts/09_select_representative_papers.py tests/test_paper_selection.py
git commit -m "feat: select representative OpenAlex papers"
```

---

### Task 12: Functional Stage 10 provisional constrained sampling

**Files:**
- Modify: `scripts/10_stratified_sample_professors.py`
- Create: `tests/test_professor_sampling.py`

**Interfaces:**
- Produces: `sample_professors(candidates, targets, seed, limit) -> SamplingResult` with selected IDs, objective, target/achieved distributions, exclusions, and reason counts.

- [ ] **Step 1: Write failing reproducibility and margin tests**

```python
def test_sampler_is_reproducible_and_reports_unmet_targets():
    first = sample_professors(synthetic_candidates(), targets(), seed=42, limit=10)
    second = sample_professors(synthetic_candidates(), targets(), seed=42, limit=10)
    assert first.selected_ids == second.selected_ids
    assert first.achieved_distribution == second.achieved_distribution
    assert first.unmet_targets
    assert all(reason for reason in first.exclusion_reasons.values())
```

- [ ] **Step 2: Run sampling tests and confirm RED**

Run: `.venv/bin/pytest tests/test_professor_sampling.py -v`
Expected: provisional sampler is absent.

- [ ] **Step 3: Implement seeded greedy constrained sampling**

Filter candidates with eight selected papers, complete work marker, and no blocking OpenAlex
consistency issue. At each step choose the candidate with the largest decrease in normalized margin
deviation minus institution/region concentration penalties; break ties by seeded rank then
professor ID. Mark human-review-dependent targets as provisional in the report.

- [ ] **Step 4: Verify sampling reports**

Run: `.venv/bin/pytest tests/test_professor_sampling.py -v`
Expected: deterministic selection, concentration penalties, exclusions, and undersupplied-domain reporting pass.

- [ ] **Step 5: Commit Stage 10**

```bash
git add scripts/10_stratified_sample_professors.py tests/test_professor_sampling.py
git commit -m "feat: sample provisional professor benchmark"
```

---

### Task 13: Provisional bundle schema and functional Stage 11

**Files:**
- Create: `schemas/openalex_profile_bundle.schema.json`
- Create: `scripts/lib/bundles.py`
- Modify: `scripts/11_build_evidence_packets.py`
- Modify: `pyproject.toml`
- Create: `tests/test_openalex_bundles.py`

**Interfaces:**
- Produces: `build_openalex_bundle(profile, selected_papers, focal_ids, provenance)` and `build_enrichment_tasks(bundle)`.
- Keeps `schemas/evidence_packet.schema.json` unchanged.

- [ ] **Step 1: Write failing schema/readiness tests**

```python
def test_provisional_bundle_validates_but_is_not_final_ready(bundle_inputs, bundle_schema):
    bundle = build_openalex_bundle(**bundle_inputs)
    validate(bundle, bundle_schema)
    assert bundle["final_evidence_packet_ready"] is False
    assert {task["task_type"] for task in bundle["enrichment_tasks"]} >= {
        "verify_faculty_status", "resolve_author_identity", "extract_focal_passages"
    }
    assert "passages" not in bundle
```

- [ ] **Step 2: Run bundle tests and confirm RED**

Run: `.venv/bin/pytest tests/test_openalex_bundles.py -v`
Expected: schema and bundle builder are absent.

- [ ] **Step 3: Implement versioned anonymous bundles and stable tasks**

Generate task IDs as a hash of bundle version, professor ID, task type, and optional paper ID.
Include raw-source hashes and OpenAlex URLs, selected paper metadata, all component scores, explicit
missing gates, and no real display name in public/provisional bundle files. Rename the Stage 11
description/output contract to profile bundles while retaining the numbered filename for compatibility.
Add `jsonschema>=4.23` as an explicit runtime dependency and use Draft 2020-12 validation with
format checking for the provisional schema.

- [ ] **Step 4: Validate synthetic bundles and strict non-readiness**

Run: `.venv/bin/pytest tests/test_openalex_bundles.py -v`
Expected: provisional schema passes, exact task coverage passes, and final readiness remains false.

- [ ] **Step 5: Commit Stage 11 and schema**

```bash
git add schemas/openalex_profile_bundle.schema.json scripts/lib/bundles.py scripts/11_build_evidence_packets.py pyproject.toml tests/test_openalex_bundles.py
git commit -m "feat: build provisional OpenAlex profile bundles"
```

---

### Task 14: Functional Stage 12 validation and manifest

**Files:**
- Create: `scripts/lib/validation.py`
- Modify: `scripts/12_validate_dataset.py`
- Modify: `data/dataset_manifest.template.yaml`
- Create: `tests/test_dataset_validation.py`

**Interfaces:**
- Produces: `validate_openalex_collection`, `validate_provisional_bundles`, `scan_public_artifacts`, and a report with `openalex_collection_valid`, `provisional_bundle_valid`, `final_evidence_packet_ready`.

- [ ] **Step 1: Write failing three-state report tests**

```python
def test_valid_openalex_collection_is_explicitly_not_final(tmp_path, complete_fixture_dataset):
    report = validate_dataset(complete_fixture_dataset)
    assert report["openalex_collection_valid"] is True
    assert report["provisional_bundle_valid"] is True
    assert report["final_evidence_packet_ready"] is False
    assert "faculty_status_unverified" in report["final_blockers"]
```

- [ ] **Step 2: Run validation tests and confirm RED**

Run: `.venv/bin/pytest tests/test_dataset_validation.py -v`
Expected: new validation module and report fields are absent.

- [ ] **Step 3: Implement collection, join, privacy, and readiness validation**

Check required tables, schema versions, unique IDs, work-history completeness, raw hashes,
checkpoint status, 8/2 selections, foreign-key joins, task coverage, secret patterns, public names,
tracked PDFs, and deterministic metadata. Populate manifest counts/source checksums/algorithm
versions while retaining final-quality fields as false.

- [ ] **Step 4: Run validation and repository tests**

Run: `.venv/bin/pytest tests/test_dataset_validation.py tests/test_dataset_scaffolds.py -v`
Expected: valid provisional fixture passes collection/bundle gates and fails only final readiness.

- [ ] **Step 5: Commit Stage 12**

```bash
git add scripts/lib/validation.py scripts/12_validate_dataset.py data/dataset_manifest.template.yaml tests/test_dataset_validation.py
git commit -m "feat: validate provisional OpenAlex datasets"
```

---

### Task 15: End-to-end offline pipeline and operator documentation

**Files:**
- Create: `tests/fixtures/openalex/offline_pipeline/`
- Create: `tests/test_offline_pipeline.py`
- Modify: `docs/openalex_collection_guide.md`
- Modify: `docs/first_10_collection_checklist.md`
- Modify: `docs/dataset_policy.md`
- Modify: `docs/decision_log.md`
- Modify: `README.md`

**Interfaces:**
- Proves all 12 stages compose using a fake client and synthetic files.
- Documents exact dry-run, ten-candidate, status, resume, validation, and `--full-run` commands.

- [ ] **Step 1: Write a failing offline pipeline test**

```python
def test_all_twelve_stages_compose_without_network(tmp_path, offline_transport):
    result = run_offline_pipeline(tmp_path, offline_transport, seed=42, candidate_limit=10)
    assert result.network_hosts == set()
    assert result.report["openalex_collection_valid"] is True
    assert result.report["provisional_bundle_valid"] is True
    assert result.report["final_evidence_packet_ready"] is False
    assert len(result.bundles) == 10
```

- [ ] **Step 2: Run the end-to-end test and confirm RED**

Run: `.venv/bin/pytest tests/test_offline_pipeline.py -v`
Expected: missing offline composition helper or a broken stage join exposes the remaining integration gap.

- [ ] **Step 3: Complete orchestration joins and write operator commands**

Ensure each stage consumes the exact prior output contract. Document that a collector runs Stage 1,
reviews institutions, then runs Stages 2–12 with `--limit 10`; status uses the printed job ID;
resume uses the checkpoint command; and full collection requires the recorded GO decision plus
`--full-run`. State that live commands consume credits and are never executed by tests.

- [ ] **Step 4: Run the full verification gate**

Run:

```bash
.venv/bin/pytest -q
.venv/bin/ruff check scripts tests
.venv/bin/python -c "import json, pathlib, yaml; [json.loads(p.read_text()) for p in pathlib.Path('schemas').glob('*.json')]; yaml.safe_load(pathlib.Path('config/dataset.yaml').read_text()); print('schemas and config parse')"
.venv/bin/python scripts/12_validate_dataset.py --config config/dataset.yaml --dry-run
git check-ignore -q .env data/raw/progress/example.json data/private/professor_identity_map.csv data/private/raw_pdfs/example.pdf
git diff --check
```

Expected: all tests pass; Ruff reports no errors; schemas/config parse; validation dry-run prints a deterministic plan; all private paths are ignored; no whitespace errors are reported.

- [ ] **Step 5: Scan for secret leakage and real records**

Run:

```bash
git grep -n "OPENALEX_API_KEY=" -- ':!.env.example'
find data/raw data/interim data/final data/private -type f ! -name '.gitkeep' -print
```

Expected: no tracked credential values and no live professor/dataset records created during implementation.

- [ ] **Step 6: Commit integration and documentation**

```bash
git add tests/fixtures/openalex/offline_pipeline tests/test_offline_pipeline.py docs/openalex_collection_guide.md docs/first_10_collection_checklist.md docs/dataset_policy.md docs/decision_log.md README.md
git commit -m "docs: add OpenAlex dataset operator workflow"
```

---

## Execution notes

- Do not run a live command while implementing this plan.
- The user's ignored `.env` stays local and must never be staged.
- Before each commit, inspect `git diff --cached --name-only` to ensure unrelated pre-existing work is not included.
- If a stage reveals an ambiguous OpenAlex response shape, add a synthetic fixture and specify the normalization behavior in `docs/openalex_collection_guide.md`; do not infer unsupported fields.
- Stop after the offline verification gate. The user initiates the first live ten-candidate run manually.
