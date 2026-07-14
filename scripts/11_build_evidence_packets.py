#!/usr/bin/env python3
"""Plan construction of anonymous, provenance-rich eight-paper evidence packets."""

from _dataset_cli import StageSpec, run_scaffold

SPEC = StageSpec(11, "build_evidence_packets", __doc__, "data/final/verified_professors.csv", "data/final/evidence_packets")

if __name__ == "__main__":
    raise SystemExit(run_scaffold(SPEC))
