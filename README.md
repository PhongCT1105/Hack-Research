# Recipient-Focused Hallucinations in AI-Generated Professor Outreach Emails

An offline, benchmark-style study of whether large language models **misrepresent a
professor's research** when generating "personalized" academic outreach emails — and
whether two interventions reduce that risk:

1. **Grounding** — giving the writer a verified publication evidence packet *before* drafting.
2. **Verification** — applying a separate evidence-based correction step *after* drafting.

Emails are generated and evaluated against public publication records. **No email is ever sent.**

## The 2×2 Experimental Design

| Condition | Writer receives evidence | Post-generation verification | Purpose |
|-----------|--------------------------|------------------------------|---------|
| **A** | No | No | Closed-book baseline |
| **B** | Yes | No | Effect of grounding during writing |
| **C** | No | Yes | Effect of correction after ungrounded writing |
| **D** | Yes | Yes | Combined safeguards |

**Pilot scope:** 12 professors × 3 fields (CS/AI, Psychology/CogSci, Biomedicine/Public Health)
× 4 conditions × 2 seeds = **96 emails**, with human validation on ≥25% of extracted claims.

**Expanded benchmark:** approximately 100 professors across five broad domains, with
about eight selected papers, two focal papers, and 2–4 evidence passages per focal paper.
This is a versioned extension of the dataset, not a replacement for the pilot.

The core outcome is claim-level: every atomic claim about a professor's topics, methods,
findings, impact, authorship, or research direction is labeled **supported, partially
supported, overstated, unsupported, contradicted, or outside evidence scope** — and we
measure whether factuality gains come at the cost of useful personalization
(the **supported-specificity trade-off**).

## Repository Map

| Path | What it is | Owner |
|------|-----------|-------|
| `docs/` | Research proposal, experimental design, dataset policy, rubric, analysis plan | All |
| `schemas/` | Expanded benchmark professor, paper, and packet JSON Schemas | Phong |
| `config/dataset.yaml` | Expanded benchmark targets, scoring versions, seed, and paths | Phong |
| `tasks/` | Agent-executable task specs, one per workstream | See below |
| `data/raw/` | Immutable source/API captures; never hand-edited | Phong |
| `data/interim/` | Reconciled metadata, scores, and review queues | Phong |
| `data/final/` | Versioned benchmark tables and internal evidence packets | Phong |
| `data/private/` | Ignored identity map and local PDFs; never commit | Phong |
| `prompts/` | Versioned writer / verifier / claim-extractor prompts (frozen after pilot) | Abhinav |
| `src/outreach_eval/` | Python package: schemas, LLM adapters, generation + verification pipeline | Abhinav |
| `scripts/` | Entry points: `run_pilot.py`, `validate_packet.py` | Abhinav |
| `outputs/` | Generated emails (JSONL). Never hand-edited. | Pipeline only |
| `logs/` | Run manifests (model, seed, prompt version per run) | Pipeline only |
| `annotations/` | Rubric, blinded annotation sheets, human labels | Kanan |
| `analysis/` | Metrics, mixed-effects models, figures | Kanan |
| `paper/` | Outline, related-work matrix, draft | Azhdar |
| `docs/source/` | Original planning documents (docx) | — |

## Workstreams

| # | Workstream | Owner | Spec |
|---|-----------|-------|------|
| 1 | Dataset & evidence packets | Phong | [`tasks/01_dataset.md`](tasks/01_dataset.md) |
| 2 | Generation & verification pipeline | Abhinav | [`tasks/02_pipeline.md`](tasks/02_pipeline.md) |
| 3 | Annotation & evaluation | Kanan | [`tasks/03_annotation.md`](tasks/03_annotation.md) |
| 4 | Related work & paper | Azhdar | [`tasks/04_paper.md`](tasks/04_paper.md) |

Workstreams are designed to run **in parallel**: the pipeline builds against
`data/evidence/MOCK-01.json` before real packets exist; annotation tooling builds
against sample claims; the paper skeleton starts immediately.

## Quickstart

```bash
# 1. Install (Python ≥ 3.11)
pip install -e ".[dev]"

# 2. Set API keys for the providers you use
export ANTHROPIC_API_KEY=...
export OPENAI_API_KEY=...

# 3. Validate an evidence packet
python scripts/validate_packet.py data/evidence/MOCK-01.json

# 4. Run the 16-email pilot (2 professors × 4 conditions × 2 seeds)
python scripts/run_pilot.py --config config/config.yaml
```

## Expanded benchmark collection

Read these in order:

1. [`docs/benchmark_design.md`](docs/benchmark_design.md) — population, dimensions,
   formulas, targets, sampling, and experiment joins.
2. [`docs/dataset_policy.md`](docs/dataset_policy.md) — inclusion, evidence, privacy,
   licensing, table contracts, and quality gates.
3. [`docs/openalex_collection_guide.md`](docs/openalex_collection_guide.md) — staged
   collection commands and reconciliation workflow.
4. [`docs/first_10_collection_checklist.md`](docs/first_10_collection_checklist.md) —
   go/no-go gate before scaling.
5. [`docs/decision_log.md`](docs/decision_log.md) — settled pilot and benchmark decisions.

After installing dependencies, inspect candidate-author discovery without making network
calls or writing data:

```bash
python scripts/02_fetch_author_candidates.py \
  --config config/dataset.yaml \
  --input data/interim/institutions.csv \
  --output data/raw/author_candidates.jsonl \
  --seed 42 \
  --dry-run
```

Network stage bodies remain gated until the dry-run contracts and first-ten process are
reviewed. Local abstract reconstruction and repository validation are implemented.

## Ground Rules (non-negotiable)

- **Freeze after pilot.** Prompts, evidence schema, output schema, and rubric are frozen
  once the 16-email pilot is reviewed. After that: bug fixes only, no method changes.
- **One owner per file.** No simultaneous edits to the same artifact.
- **Never hand-edit generated outputs.** `outputs/` and `logs/` are written only by the pipeline.
- **Blind the annotators.** Condition labels are hidden during human grading.
- **Anonymous IDs only** (`CS-01`, `PSY-01`, `BIO-01`, …) in all public analysis outputs.
- **Private identity mapping.** Keep real-name/OpenAlex-ID mappings only in
  `data/private/professor_identity_map.csv`; never commit raw PDFs or private mappings.
- **Log every decision** in `docs/decision_log.md`.

See [`CLAUDE.md`](CLAUDE.md) for the full agent/contributor guide and
[`docs/research_proposal.md`](docs/research_proposal.md) for the scientific rationale.
