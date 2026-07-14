#!/usr/bin/env python
"""Validate evidence packets against the schema + dataset-policy quality gates.

Usage:
    python scripts/validate_packet.py data/evidence/CS-01.json [more.json ...]
    python scripts/validate_packet.py data/evidence/*.json
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pydantic import ValidationError

from outreach_eval.schemas import EvidencePacket

MIN_PAPERS_PILOT = 6
MIN_FOCAL_PASSAGES = 2


def check(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        packet = EvidencePacket.model_validate_json(path.read_text())
    except ValidationError as e:
        return [f"schema: {err['loc']} — {err['msg']}" for err in e.errors()]

    is_mock = packet.professor_id.startswith("MOCK")
    if path.stem != packet.professor_id:
        problems.append(f"filename {path.stem!r} != professor_id {packet.professor_id!r}")
    if not is_mock and len(packet.papers) < MIN_PAPERS_PILOT:
        problems.append(f"only {len(packet.papers)} papers; pilot requires >= {MIN_PAPERS_PILOT}")
    if not is_mock and len(packet.focal_passages) < MIN_FOCAL_PASSAGES:
        problems.append(
            f"only {len(packet.focal_passages)} focal passages; requires >= {MIN_FOCAL_PASSAGES}"
        )
    if len(packet.faculty_summary.split()) < 15:
        problems.append("faculty_summary too short to carry research themes")

    paper_ids = {p.paper_id for p in packet.papers}
    if len(paper_ids) != len(packet.papers):
        problems.append("duplicate paper_id values")
    for fp in packet.focal_passages:
        if fp.paper_id not in paper_ids:
            problems.append(f"focal passage references unknown paper_id {fp.paper_id!r}")
    for p in packet.papers:
        if not is_mock and not p.doi:
            problems.append(f"{p.paper_id}: missing DOI")
        if not p.abstract.strip():
            problems.append(f"{p.paper_id}: empty abstract")
        if not p.provenance.source_url:
            problems.append(f"{p.paper_id}: missing provenance source_url")
    return problems


def main() -> int:
    paths = [Path(a) for a in sys.argv[1:]]
    if not paths:
        print(__doc__)
        return 2
    failed = False
    for path in paths:
        problems = check(path)
        if problems:
            failed = True
            print(f"FAIL {path}")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"OK   {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
