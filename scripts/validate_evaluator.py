#!/usr/bin/env python
"""Validate the auto-evaluator against human labels: agreement, kappa, per-label P/R/F1.

Joins machine labels and human (adjudicated) labels on blind claim id and treats the
human `final_label` as gold. This is the "auto-evaluator validated on a human subset"
step in docs/analysis_plan.md — required before trusting auto labels at scale.

Usage:
  python scripts/validate_evaluator.py \
    --machine annotations/machine_labels.csv --human annotations/human_labels.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outreach_eval.metrics import cohen_kappa, normalize_label


def _labels_by_claim(rows: list[dict]) -> dict[str, object]:
    out = {}
    for r in rows:
        label = normalize_label(r.get("final_label"))
        cid = r.get("claim_id")
        if label is not None and cid:
            out[cid] = label
    return out


def compute_agreement(machine_rows: list[dict], human_rows: list[dict]) -> dict:
    """Return agreement stats over claims present in BOTH sets (human = gold)."""
    machine = _labels_by_claim(machine_rows)
    human = _labels_by_claim(human_rows)
    shared = sorted(set(machine) & set(human))
    pairs = [(machine[c], human[c]) for c in shared]
    if not pairs:
        return {"n": 0, "agreement": None, "kappa": None, "per_label": {}}

    agree = sum(1 for m, h in pairs if m == h) / len(pairs)
    kappa = cohen_kappa(pairs)

    per_label = {}
    labels = {lbl for pair in pairs for lbl in pair}
    for lbl in labels:
        tp = sum(1 for m, h in pairs if m == lbl and h == lbl)
        machine_pos = sum(1 for m, _ in pairs if m == lbl)
        human_pos = sum(1 for _, h in pairs if h == lbl)
        precision = tp / machine_pos if machine_pos else None
        recall = tp / human_pos if human_pos else None
        f1 = (2 * precision * recall / (precision + recall)
              if precision and recall else 0.0 if (precision is not None and recall is not None) else None)
        per_label[lbl.value] = {"precision": precision, "recall": recall, "f1": f1,
                                "human_count": human_pos}
    return {"n": len(pairs), "agreement": agree, "kappa": kappa, "per_label": per_label}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--machine", default="annotations/machine_labels.csv")
    ap.add_argument("--human", default="annotations/human_labels.csv")
    ap.add_argument("--out", default="analysis/evaluator_validation.csv")
    args = ap.parse_args()

    for label, path in [("machine", args.machine), ("human", args.human)]:
        if not Path(path).exists():
            print(f"ERROR: {label} labels not found: {path}", file=sys.stderr)
            return 2

    with open(args.machine, encoding="utf-8") as f:
        machine_rows = list(csv.DictReader(f))
    with open(args.human, encoding="utf-8") as f:
        human_rows = list(csv.DictReader(f))

    stats = compute_agreement(machine_rows, human_rows)
    print(f"Claims compared (in both sets): {stats['n']}")
    print(f"Raw agreement: {stats['agreement']}")
    print(f"Cohen's kappa (auto vs human): {stats['kappa']}")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["label", "precision", "recall", "f1", "human_count"])
        for lbl, m in sorted(stats["per_label"].items()):
            w.writerow([lbl, m["precision"], m["recall"], m["f1"], m["human_count"]])
    print(f"Per-label precision/recall/F1 written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
