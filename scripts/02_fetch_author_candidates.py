#!/usr/bin/env python3
"""Plan discovery of 500-1,000 OpenAlex author candidates from the reviewed institution pool."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(2, "fetch_author_candidates", __doc__, "data/interim/institutions.csv", "data/raw/author_candidates.jsonl", "openalex", True)

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
