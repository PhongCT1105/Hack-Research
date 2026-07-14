#!/usr/bin/env python3
"""Plan collection of a geographically and institutionally varied OpenAlex institution pool."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(1, "fetch_institutions", __doc__, None, "data/raw/institutions.jsonl", "openalex")

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
