#!/usr/bin/env python3
"""Plan DOI, title, author, and ownership reconciliation across scholarly sources."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(6, "reconcile_metadata", __doc__, "data/interim/author_works_with_abstracts.jsonl", "data/interim/reconciled_candidate_papers.jsonl")

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
