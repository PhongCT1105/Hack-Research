#!/usr/bin/env python3
"""Plan deterministic 3/2/2/1 representative-paper and two-focal-paper selection."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(9, "select_representative_papers", __doc__, "data/interim/scored_candidate_papers.jsonl", "data/interim/candidate_papers.csv", supports_seed=True)

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
