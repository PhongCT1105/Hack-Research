#!/usr/bin/env python
"""Fast human-validation sheet: build a fillable ~30-claim sheet, then parse it back.

build : write annotations/human_check.md — claims grouped by professor with the evidence
        inline and a blank `LABEL:` line each. A human fills one of the 7 labels per claim
        (blind to condition and to the automatic label).
parse : read the filled sheet -> annotations/human_labels.csv (claim_id, final_label,
        label_annotator_1) so validate_evaluator.py / compute_results.py can use it.

Usage:
  python scripts/human_check.py build --per-prof 3
  python scripts/human_check.py parse
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_annotation_batch import name_variants, scrub_names

from outreach_eval.conditions import build_evidence_block
from outreach_eval.schemas import EvidencePacket

LABELS = ("supported | partially_supported | overstated | unsupported | "
          "contradicted | outside_evidence_scope | subjective_or_generic")
CLAIM_RE = re.compile(r"\[(?P<cid>[A-Za-z0-9_-]+)\][^\n]*\n\s*LABEL:\s*(?P<label>[A-Za-z_]*)")


def build(sheet_csv: Path, evidence_dir: Path, out: Path, per_prof: int) -> None:
    rows = list(csv.DictReader(sheet_csv.open()))
    by_prof: dict[str, list[dict]] = {}
    for r in rows:
        by_prof.setdefault(r["professor_id"], []).append(r)

    lines = [
        "# Quick human validation — fill a LABEL after each claim",
        "",
        f"Use exactly one of: **{LABELS}**",
        "",
        "For each claim, read the professor's evidence above it and decide whether the claim",
        "is supported by that evidence. You do not know which condition/model produced it —",
        "that is intentional. Leave a label blank only if you truly cannot decide.",
        "",
        "---",
    ]
    picked = 0
    for pid in sorted(by_prof):
        packet = EvidencePacket.model_validate_json((evidence_dir / f"{pid}.json").read_text())
        variants = name_variants(packet.real_name_do_not_export)
        evidence = scrub_names(build_evidence_block(packet), variants)
        claims = sorted(by_prof[pid], key=lambda r: r["claim_id"])[:per_prof]
        if not claims:
            continue
        lines += [f"\n## {pid}  (field: {packet.field})", "", "<details><summary>EVIDENCE (click)</summary>",
                  "", "```", evidence, "```", "", "</details>", "", "### Claims:"]
        for c in claims:
            lines.append(f"\n[{c['claim_id']}] {c['atomic_claim']}")
            lines.append("LABEL: ")
            picked += 1
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {picked} claims across {len(by_prof)} professors to {out}")


def parse(sheet_md: Path, out_csv: Path) -> None:
    text = sheet_md.read_text(encoding="utf-8")
    filled = [(m.group("cid"), m.group("label").strip())
              for m in CLAIM_RE.finditer(text) if m.group("label").strip()]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["claim_id", "label_annotator_1", "final_label"])
        w.writeheader()
        for cid, label in filled:
            w.writerow({"claim_id": cid, "label_annotator_1": label, "final_label": label})
    print(f"Parsed {len(filled)} human labels -> {out_csv}")
    if not filled:
        print("  (none filled yet — add a label after each 'LABEL:' line and re-run parse)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--sheet", default="annotations/claims_to_label.csv")
    b.add_argument("--evidence-dir", default="data/evidence")
    b.add_argument("--out", default="annotations/human_check.md")
    b.add_argument("--per-prof", type=int, default=3)
    p = sub.add_parser("parse")
    p.add_argument("--in", dest="infile", default="annotations/human_check.md")
    p.add_argument("--out", default="annotations/human_labels.csv")
    args = ap.parse_args()

    if args.cmd == "build":
        build(Path(args.sheet), Path(args.evidence_dir), Path(args.out), args.per_prof)
    else:
        parse(Path(args.infile), Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
