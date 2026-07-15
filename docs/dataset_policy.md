# Dataset Policy

## Scope

This policy governs professor discovery, publication evidence, packet construction, and release boundaries for the pilot and expanded benchmark. Generated emails are offline evaluation artifacts and are never sent.

The existing pilot remains 12 professors across three domains, four experimental conditions, and two generations per condition (96 emails), with a 2-professor/16-email pre-freeze checkpoint. The expanded `benchmark-v1` collection targets approximately 100 professors across five domains. It extends the sampling frame; it does not replace the pilot or reopen frozen pilot prompts and runtime contracts.

## Data stages and allowed content

| Stage | Path | Purpose | Manual edits |
|---|---|---|---|
| Source/raw | `data/raw/` | Timestamped API responses and normalized source snapshots | Never edit a captured response; append a corrected retrieval |
| Transformed/interim | `data/interim/` | Reconstructed abstracts, reconciled metadata, scores, and reviewer queues | Review fields only through documented scripts/workflows |
| Selected/final | `data/final/` | Versioned benchmark tables and internal evidence packets | Never silently overwrite; issue a new version |
| Private | `data/private/` | Identity map, downloaded PDFs, reviewer-only identity notes | Never commit; access limited to authorized team members |
| Generated outputs | `outputs/` | Versioned email and verifier records | Pipeline writes only; never hand-edit |
| Annotations | `annotations/` | Blinded claims and adjudicated labels | Must not reveal condition or identity |

Identity-bearing raw and interim records must be handled as internal research data even when their source metadata is public. A public analysis export uses anonymous professor IDs and strips direct identity mappings.

## Inclusion policy

A final professor must have a confirmed current faculty or comparable independent research role on an official faculty, university, or laboratory page; a valid institutional association; at least 8 eligible works; at least 6 usable abstracts; recent publication activity appropriate to the field; usable OpenAlex topic metadata; and 2 focal papers with legally accessible full-text evidence.

ORCID is useful identity support but is not mandatory because adoption varies by field and geography.

Reject or defer candidates when faculty status cannot be confirmed, the OpenAlex author profile appears merged or materially split, affiliation is clearly wrong, paper ownership is ambiguous, fewer than eight eligible papers remain after reconciliation, or two focal papers lack usable evidence.

## Sampling policy

Build a raw pool of 500-1,000 author candidates from a geographically and institutionally diverse institution pool. Do not select exactly 100 at discovery time. The institution pool should include the United States and Canada, Europe, East/South/Southeast Asia, Latin America, Africa, and the Middle East/Oceania where metadata quality permits. These are diversity targets, not rigid quotas.

Select the final sample through the seeded constrained procedure in `docs/benchmark_design.md`. Record the candidate-pool version, algorithm version, seed, targets, achieved margins, excluded candidates, and exclusion reasons. Do not sample only the most cited, famous, English-language, open-access, or easiest-to-verify researchers.

## Source and validation hierarchy

No single provider is the source of truth for every field:

1. **Official faculty or laboratory page:** current role, title, broad research summary.
2. **ORCID:** identity support and public researcher-linked records.
3. **OpenAlex:** discovery, scholarly graph, topics, works, citation metadata, affiliations, abstracts, and OA locations.
4. **Semantic Scholar:** secondary author-paper matching and abstract enrichment.
5. **Crossref:** DOI, title, venue, publication date, and author reconciliation.
6. **Unpaywall or OpenAlex OA locations:** legal full-text discovery.

Resolve works by DOI when possible, then compare normalized title, year, venue, and author list. Check an official publication list or ORCID if ambiguity remains. A selected paper cannot enter a final packet while material authorship uncertainty remains.

## Evidence policy

Each expanded packet contains around eight representative papers: three recent, two influential, two that expand topic or method coverage, and one seeded random eligible paper. Paper popularity and technical complexity remain separate variables.

Two papers are focal. Prefer legal full text, clear methods and results, strong portfolio representation, and low authorship ambiguity. Extract 2-4 short passages per focal paper from the objective/introduction, methods, results, and discussion/limitations as available. Store paper ID, section, page number when available, passage text, source URL, retrieval date, license/access note, and selection rationale.

Abstracts are breadth evidence, not a complete answer key. Full-text passages support method, result, and limitation claims that abstracts may underspecify. Claims the packet cannot fairly decide receive `outside_evidence_scope`; do not call them globally false.

Do not place copyrighted full PDFs in the public repository. Locally downloaded PDFs belong in ignored `data/private/raw_pdfs/`. Store DOI/URL metadata, permitted abstracts, and short attributed passages instead. A passage must be no longer than necessary for adjudication and must retain source attribution.

## Required tables

CSV files use UTF-8, one header row, ISO 8601 dates, canonical OpenAlex URLs/IDs, and empty fields rather than invented values. Multi-valued cells are JSON arrays, not delimiter-dependent strings.

### `institutions.csv`

```text
institution_id,openalex_id,ror_id,name,country,region,institution_type,
works_count,cited_by_count,homepage_url
```

### `author_candidates.csv`

```text
openalex_author_id,display_name,orcid,last_known_institution,works_count,
cited_by_count,h_index,first_publication_year,last_publication_year,
primary_domain,primary_field,primary_subfield,candidate_status
```

This table is identity-bearing and must not be included in an anonymous public analysis export.

### `verified_professors.csv`

```text
professor_id,openalex_author_id,faculty_status_verified,faculty_page_url,
faculty_title,career_stage,career_stage_source,domain,field,subfield,country,
region,visibility_percentile,visibility_tier,research_breadth_score,
research_breadth_tier,topic_coherence_score,topic_coherence_tier,
method_diversity_score,method_diversity_tier,synthesis_difficulty_score,
synthesis_difficulty_tier,paper_complexity_score,paper_complexity_tier,
quality_status
```

The internal collection table contains identity-bearing links; public exports remove them and use `professor_id` only.

### `candidate_papers.csv`

```text
professor_id,paper_id,openalex_work_id,doi,title,publication_year,venue,
citation_count,citation_percentile_field_year,abstract_available,
full_text_available,open_access,topic_ids,primary_topic,method_tags,
complexity_score,complexity_tier,selected,selection_reason,focal,
ownership_verified
```

## Career, visibility, and scoring policy

Store verified faculty title separately from estimated career stage. Prefer the official page; otherwise use academic age: early 0-8, mid 9-18, senior 19+ publication years. Mark the fallback `estimated_from_first_publication_year`.

Visibility uses field- and career-normalized citations, h-index, works count, and field-normalized citation percentiles. Paper popularity uses paper-level raw and normalized citations. Paper complexity uses textual/methodological features and never citations. Research breadth counts spread; topic coherence assesses how strongly papers form one agenda; synthesis difficulty estimates the risk of unsupported cross-paper unification. Evidence completeness measures adjudication coverage. Definitions and formulas are in `docs/benchmark_design.md`.

Automated scores must store all inputs, normalization strata, code version, and missingness. Human review is required wherever the benchmark design specifies it. Reviewers may override a tier only with a reason and timestamp; the automated score remains unchanged for auditability.

## Quality gates

Every final professor must pass:

- confirmed faculty/research role and official page;
- at least 8 eligible papers and at least 6 usable abstracts;
- 2 focal papers with usable full-text evidence;
- selected-paper authorship verified;
- no unresolved OpenAlex merge/split;
- traceable source for every evidence item.

Every final packet must pass:

- JSON Schema validation;
- unique professor ID validation;
- exact selected-paper and focal-paper counts for `benchmark-v1`;
- passage-count and source-reference validation;
- source URL and retrieval-date validation;
- authorship-verification validation;
- no real name in public outputs;
- no raw PDF committed publicly.

The first ten packets also pass the manual gate in `docs/first_10_collection_checklist.md` before collection scales.

## Privacy and ethics

- Emails are generated for offline evaluation and never sent.
- Public analysis and examples use anonymous IDs.
- The real mapping is `data/private/professor_identity_map.csv` and is gitignored.
- Public professional and scholarly metadata may be used when necessary for the benchmark, with provenance and retrieval dates.
- Do not infer sensitive demographic traits from names, photos, language, or institutional location.
- Do not contact professors or connect this repository to an email service.
- Do not expose experimental condition in blinded annotation files.
- Do not describe packet-absent claims as globally false.

## Licensing

Record the source URL, retrieval date, provider, license/access status, and any redistribution restriction. Prefer source metadata and legal OA locations. Do not redistribute publisher PDFs or excessive copyrighted text. If a passage cannot be redistributed, store its locator and a restricted internal excerpt or omit it from the public release.

## Reproducibility and change control

Every dataset release has a manifest based on `data/dataset_manifest.template.yaml`, configuration snapshot, source checksums, source retrieval window, random seed, code commit or archive identifier, candidate-pool version, scoring/sampling versions, target and achieved margins, exclusions, schema version, and validation results.

Raw responses are append-only. Corrections happen in transformed data and receive a new version. Decisions that alter sampling, scoring, evidence scope, schemas, or release policy must be added to `docs/decision_log.md`. If the pilot freeze has occurred, expanded-benchmark changes cannot alter frozen pilot artifacts without a separately approved and logged bug-fix decision.
