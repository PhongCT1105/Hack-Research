#!/usr/bin/env python3
"""Plan cursor-paginated retrieval of eligible works for verified OpenAlex authors."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(4, "fetch_author_works", __doc__, "data/interim/verified_professors.csv", "data/raw/author_works.jsonl", "openalex")

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
