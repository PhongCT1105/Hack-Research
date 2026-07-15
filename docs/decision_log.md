# Decision Log

This log records design choices that affect multiple workstreams. Entries marked **pre-existing** restate repository decisions so later changes do not silently override them.

## D001 - Offline 2 x 2 factorial experiment

- **Status:** Accepted, pre-existing; reaffirmed 2026-07-14
- **Decision:** Preserve conditions A-D that independently vary evidence to the writer and evidence-based post-generation verification. Generated emails are never sent.
- **Reason:** The design estimates grounding, verification, and their interaction; B vs C directly compares evidence-at-write-time with repair.
- **Source:** `docs/experimental_design.md`, `docs/research_proposal.md`.

## D002 - Pilot and pre-freeze checkpoint remain unchanged

- **Status:** Accepted, pre-existing; reaffirmed 2026-07-14
- **Decision:** The pilot remains 12 professors, 3 domains, 4 conditions, 2 seeds, and 96 emails. The existing 2-professor/16-email run remains the pre-freeze checkpoint.
- **Reason:** The user requested an expanded benchmark without replacing the pilot. The smaller checkpoint catches schema, prompt, evidence, and annotation failures before the 96-email pilot.

## D003 - Expanded benchmark is a separate versioned collection layer

- **Status:** Accepted 2026-07-14
- **Decision:** Add `benchmark-v1` with approximately 100 professors and schemas under `schemas/`. These collection contracts do not retroactively change a frozen pilot runtime schema.
- **Reason:** This permits richer sampling and evidence fields while respecting the existing freeze rule. Any later runtime integration requires an explicit versioned migration and decision entry.

## D004 - OpenAlex is the backbone, not the sole source of truth

- **Status:** Accepted 2026-07-14
- **Decision:** Use official pages for current role/title, ORCID for identity support, OpenAlex for discovery/graph metadata, Semantic Scholar for secondary matching, Crossref for DOI metadata, and Unpaywall/OpenAlex OA locations for legal full text.
- **Reason:** OpenAlex author identity and metadata can be merged, split, missing, or stale. No materially uncertain paper enters a final packet.

## D005 - Seven benchmark constructs remain separate

- **Status:** Accepted 2026-07-14
- **Decision:** Store researcher visibility, paper popularity, paper complexity, research breadth, topic coherence, cross-paper synthesis difficulty, and evidence completeness as distinct variables.
- **Reason:** They represent model familiarity, individual-paper exposure, technical description difficulty, portfolio spread, agenda unity, cross-paper summarization risk, and adjudication coverage respectively. A single difficulty score would confound them.

## D006 - Complexity excludes citations

- **Status:** Accepted 2026-07-14
- **Decision:** Use the requested 25/20/15/15/15/10 weighted complexity composite. Retain research-objective count and hedging density as unweighted diagnostic fields in v1.
- **Reason:** The requested weighted components already sum to 100%. Citations measure popularity/visibility, not technical complexity.

## D007 - Synthesis difficulty v1 operational score

- **Status:** Accepted 2026-07-14
- **Decision:** Weight topic entropy 0.15, mean semantic distance 0.15, cluster count 0.10, method diversity 0.10, dataset/population diversity 0.10, temporal evolution 0.10, cross-domain breadth 0.10, and inverse topic coherence 0.20. Store all components and require human review of the final tier.
- **Reason:** This creates a reproducible screening score while giving the largest single weight to whether the portfolio supports a shared agenda. It remains an operational benchmark heuristic, not an objective property of a researcher.
- **Review trigger:** Revisit after the first ten-professor test if component distributions collapse or reviewers systematically override tiers.

## D008 - Representative paper slot allocation

- **Status:** Accepted 2026-07-14
- **Decision:** Select 3 recent, 2 influential, 2 topic/method-diversifying, and 1 seeded-random eligible paper per professor. Resolve duplicate slots deterministically. Choose exactly 2 focal papers.
- **Reason:** This balances recency, possible model familiarity, portfolio coverage, and protection against hand-picking.

## D009 - Constrained sampling objective and seed

- **Status:** Accepted 2026-07-14
- **Decision:** Use hard quality gates and a seeded optimizer minimizing normalized absolute deviation from target margins, with a small institutional/geographic concentration penalty. Default seed is 42 and must be recorded with algorithm/candidate-pool versions.
- **Reason:** Exact multiway stratification is infeasible; a reproducible soft-margin objective preserves all primary targets without pretending every intersection can be matched.

## D010 - Public anonymity is stricter than the legacy allowance

- **Status:** Accepted 2026-07-14
- **Decision:** Public analysis, examples, generated outputs, and annotations use anonymous IDs. The identity map is `data/private/professor_identity_map.csv`. Internal collection tables may contain identity-bearing public metadata for verification, but public exports must strip direct mappings and real names.
- **Reason:** The earlier contributor guide allowed real names inside evidence packets. The expanded policy narrows this: identity-bearing internal packets are not public outputs, and public packet exports must be sanitized. This is a privacy tightening, not a permission to remove provenance from controlled internal evidence.

## D011 - Raw data are immutable and PDFs are private

- **Status:** Accepted 2026-07-14
- **Decision:** Raw API responses are append-only and never hand-edited. Downloaded PDFs stay in ignored `data/private/raw_pdfs/`; public artifacts contain legal URLs, metadata, permitted abstracts, and short attributed passages.
- **Reason:** This preserves reproducibility and avoids unauthorized redistribution.

## D012 - Evidence-relative labels

- **Status:** Accepted, pre-existing; reaffirmed 2026-07-14
- **Decision:** `unsupported` means not warranted by the agreed packet, not globally false. Use `outside_evidence_scope` when the packet cannot fairly adjudicate the claim.
- **Reason:** Abstracts and selected passages cannot prove the absence of every true fact.

## D013 - First ten professors are a process gate

- **Status:** Accepted 2026-07-14
- **Decision:** Complete and review ten full packets before scaling. The ten-record test checks identity resolution, scoring distributions, evidence sufficiency, provenance, privacy, API behavior, and reviewer agreement.
- **Reason:** It is cheaper to revise collection logic before fetching and reviewing the full candidate pool. The test records a formal GO/REVISE/STOP decision.

## D014 - CLI scaffolds are safe before live network implementation

- **Status:** Accepted 2026-07-14
- **Decision:** All 12 stage scripts expose deterministic arguments, dry-run plans, cache/log/no-overwrite conventions, and explicit stage contracts. Abstract reconstruction and repository validation begin as functional local stages. Live network-specific mutations must be implemented and reviewed separately against the guide.
- **Reason:** This lets collectors inspect commands and file contracts without accidental API calls or partial raw writes.

## D015 - Expanded raw retention supersedes the pilot scratch-only note

- **Status:** Accepted 2026-07-14
- **Decision:** For `benchmark-v1`, retain immutable timestamped API responses under `data/raw/`. Keep only credentials, caches, identity maps, and raw PDFs ignored/private. The original pilot task's scratch-only instruction is now explicitly marked as legacy.
- **Reason:** The expanded benchmark requires reproducible source snapshots, checksums, and reprocessing without repeated API calls. This change does not modify existing pilot packets or generated outputs.

## D016 - Collection progress is local and keyed by command setup

- **Status:** Accepted 2026-07-14
- **Decision:** Store one atomic JSON checkpoint per logical collection command under `data/raw/progress/`. Derive its stable job ID from the stage, normalized non-secret setup, input checksum, dataset/candidate-pool versions, and seed. Save the current institution/professor, provider ID, cursor, completed IDs, next item, counts, and redacted resume command after every page and item. On exhausted credits, save `paused_rate_limit` and exit 75. Do not use a shared database or commit checkpoints.
- **Reason:** Different API calls and filters are independent jobs. Local per-command files make the exact stopping point visible, prevent unrelated commands from overwriting one another, and let a teammate continue by copying only the checkpoint and partial raw-output directory. API keys are deliberately excluded so each teammate supplies their own credential.
- **Implementation boundary:** The checkpoint engine and status interface are implemented; guarded network-stage bodies must invoke their lifecycle transitions when live fetching is enabled.
