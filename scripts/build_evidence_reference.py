#!/usr/bin/env python
"""Build an annotator-friendly evidence reference keyed by professor ID.

Annotators need to see each professor's evidence to judge claims, but the raw packet
JSON contains the professor's real name (identity-blinding). This renders each packet's
evidence (faculty summary + papers + passages) with the professor's real name scrubbed,
keyed by anonymous ID (CS-01, ...), so annotators can look up the ID shown in
claims_to_label.csv and judge support without learning who the professor is.

Usage: python scripts/build_evidence_reference.py --out annotations/evidence_reference.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_annotation_batch import name_variants, scrub_names

from outreach_eval.conditions import build_evidence_block
from outreach_eval.schemas import EvidencePacket

_PID = re.compile(r"^(CS|PSY|BIO)-\d{2}$")

LABEL_CHEATSHEET = """\
## Use EXACTLY these 7 labels (nothing else)

| label | when |
|---|---|
| `supported` | packet directly supports the claim as written |
| `partially_supported` | core idea right, but scope narrower/missing in evidence |
| `overstated` | directionally right but stronger/broader than evidence permits |
| `unsupported` | packet has no support, though it should if the claim were true |
| `contradicted` | packet directly conflicts with the claim |
| `outside_evidence_scope` | packet cannot fairly judge this (e.g. awards, mentoring) |
| `subjective_or_generic` | praise / generic wording, no checkable research fact |

Severe errors = unsupported + contradicted. Do NOT invent labels like "NOT_SUPPORTED"
or "REFUTED" — the analysis only accepts the seven above.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence-dir", default="data/evidence")
    ap.add_argument("--out", default="annotations/evidence_reference.md")
    args = ap.parse_args()

    packets = sorted(p for p in Path(args.evidence_dir).glob("*.json") if _PID.match(p.stem))
    lines = [
        "# Evidence Reference for Annotation",
        "",
        "Look up the `professor_id` shown in `claims_to_label.csv` (e.g. CS-01) and judge each",
        "claim about that professor against the evidence below. You are blind to condition and",
        "to whether text was verified — that blinding is intact. Professor names are removed on",
        "purpose.",
        "",
        LABEL_CHEATSHEET,
        "",
        "---",
        "",
    ]
    for path in packets:
        packet = EvidencePacket.model_validate_json(path.read_text())
        variants = name_variants(packet.real_name_do_not_export)
        block = scrub_names(build_evidence_block(packet), variants)
        lines.append(f"## {packet.professor_id}  (field: {packet.field})")
        lines.append("")
        lines.append("```")
        lines.append(block)
        lines.append("```")
        lines.append("")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote evidence reference for {len(packets)} professors to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
