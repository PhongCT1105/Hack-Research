#!/usr/bin/env python3
"""Plan the human faculty-status and author-identity verification queue."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(3, "verify_faculty_status", __doc__, "data/interim/author_candidates.csv", "data/interim/faculty_verification_queue.csv")

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
