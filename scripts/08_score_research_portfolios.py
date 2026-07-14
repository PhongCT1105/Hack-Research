#!/usr/bin/env python3
"""Plan separate breadth, coherence, method-diversity, and synthesis-difficulty scores."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(8, "score_research_portfolios", __doc__, "data/interim/scored_candidate_papers.jsonl", "data/interim/scored_professor_portfolios.jsonl")

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
