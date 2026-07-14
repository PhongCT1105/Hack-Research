#!/usr/bin/env python3
"""Plan field/year-normalized paper complexity scoring with popularity kept separate."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(7, "score_paper_complexity", __doc__, "data/interim/reconciled_candidate_papers.jsonl", "data/interim/scored_candidate_papers.jsonl")

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
