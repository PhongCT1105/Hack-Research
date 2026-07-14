#!/usr/bin/env python3
"""Plan seeded constrained sampling that minimizes deviation from benchmark margins."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(10, "stratified_sample_professors", __doc__, "data/interim/verified_professors.csv", "data/final/verified_professors.csv", supports_seed=True)

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
