#!/usr/bin/env python
"""Build the blinded annotation batch for Workstream 3 (Kanan).

Reads generated `EmailRecord` JSONL and emits two files:

  annotations/claims_to_label.csv   blinded sheet handed to annotators
  annotations/blinding_map.csv      GITIGNORED join key (pipeline owner only)

Blinding guarantees (CLAUDE.md rule 3 + annotations/README.md):
  - no experimental condition or seed,
  - no original-vs-verified flag,
  - no professor real names (scrubbed from claim text using the evidence packets),
  - opaque, deterministically shuffled email/claim ids so annotators cannot infer
    which condition produced a claim.

The anonymous professor id (e.g. CS-01) is preserved: annotators need it to pull the
correct evidence packet when judging support. It is not a real name.

Usage:
    python scripts/build_annotation_batch.py \
        --inputs outputs/pilot.jsonl \
        --evidence-dir data/evidence \
        --out annotations/claims_to_label.csv \
        --map annotations/blinding_map.csv \
        --batch-tag pilot-01 --seed 42
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outreach_eval.io_utils import read_jsonl
from outreach_eval.schemas import EmailRecord, EvidencePacket

SHEET_FIELDS = [
    "email_id",
    "professor_id",
    "condition_hidden",
    "claim_id",
    "atomic_claim",
    "claim_type",
    "evidence_excerpt",
    "label_annotator_1",
    "label_annotator_2",
    "final_label",
    "notes",
]

MAP_FIELDS = [
    "claim_id",  # blinded id, joins to the sheet
    "email_id",  # blinded id
    "run_id",  # true run key: {professor_id}_{condition}_{seed}
    "professor_id",
    "condition",
    "seed",
    "verification_applied",
    "original_claim_id",
]

# Honorifics that must never be treated as a surname during name scrubbing.
_NAME_STOPWORDS = {"professor", "prof", "dr", "phd", "mr", "ms", "mrs", "mx"}


def name_variants(real_name: str) -> list[str]:
    """Name strings to scrub from claim text, longest first.

    Full name (minus any parenthetical) plus the trailing surname token. Honorifics
    are excluded so we never blank out the word "Professor".
    """
    base = re.sub(r"\(.*?\)", "", real_name).strip()
    if not base:
        return []
    variants = {base}
    tokens = [t for t in re.split(r"\s+", base) if t]
    for token in reversed(tokens):
        clean = token.strip(".,")
        if len(clean) >= 3 and clean.lower() not in _NAME_STOPWORDS:
            variants.add(clean)
            break
    return sorted(variants, key=len, reverse=True)


def scrub_names(text: str, variants: list[str], replacement: str = "the professor") -> str:
    """Replace each name variant (whole word, case-insensitive) with a generic phrase."""
    for variant in variants:
        text = re.sub(rf"\b{re.escape(variant)}(?:'s)?\b", replacement, text, flags=re.IGNORECASE)
    return text


def build_batch(
    records: list[EmailRecord],
    name_variants_by_pid: dict[str, list[str]],
    *,
    seed: int,
    batch_tag: str,
) -> tuple[list[dict], list[dict]]:
    """Pure core: return (sheet_rows, map_rows). No file or clock access.

    Emails are ordered by run_id then deterministically shuffled with `seed`, so the
    on-sheet order carries no condition information but is reproducible.
    """
    ordered = sorted(records, key=lambda r: r.run_id)
    random.Random(seed).shuffle(ordered)

    sheet_rows: list[dict] = []
    map_rows: list[dict] = []
    for e_idx, record in enumerate(ordered, start=1):
        email_id = f"E-{e_idx:04d}"
        variants = name_variants_by_pid.get(record.professor_id, [])
        for c_idx, claim in enumerate(record.extracted_claims, start=1):
            claim_id = f"{email_id}_c{c_idx:02d}"
            sheet_rows.append(
                {
                    "email_id": email_id,
                    "professor_id": record.professor_id,
                    "condition_hidden": batch_tag,
                    "claim_id": claim_id,
                    "atomic_claim": scrub_names(claim.atomic_claim, variants),
                    "claim_type": claim.claim_type.value if claim.claim_type else "",
                    "evidence_excerpt": "",  # annotators cite the packet excerpt they used
                    "label_annotator_1": "",
                    "label_annotator_2": "",
                    "final_label": "",
                    "notes": "",
                }
            )
            map_rows.append(
                {
                    "claim_id": claim_id,
                    "email_id": email_id,
                    "run_id": record.run_id,
                    "professor_id": record.professor_id,
                    "condition": record.condition.value,
                    "seed": record.seed,
                    "verification_applied": record.verification_applied,
                    "original_claim_id": claim.claim_id,
                }
            )
    return sheet_rows, map_rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_name_variants(evidence_dir: Path, professor_ids: set[str]) -> dict[str, list[str]]:
    variants: dict[str, list[str]] = {}
    for pid in sorted(professor_ids):
        packet_path = evidence_dir / f"{pid}.json"
        if not packet_path.exists():
            print(f"WARNING: no evidence packet for {pid}; cannot scrub its name", file=sys.stderr)
            variants[pid] = []
            continue
        packet = EvidencePacket.model_validate_json(packet_path.read_text())
        variants[pid] = name_variants(packet.real_name_do_not_export)
    return variants


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inputs", nargs="+", default=["outputs/pilot.jsonl"])
    ap.add_argument("--evidence-dir", default="data/evidence")
    ap.add_argument("--out", default="annotations/claims_to_label.csv")
    ap.add_argument("--map", default="annotations/blinding_map.csv")
    ap.add_argument("--batch-tag", default="pilot-01")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    records: list[EmailRecord] = []
    for pattern in args.inputs:
        path = Path(pattern)
        if not path.exists():
            print(f"ERROR: input not found: {path}", file=sys.stderr)
            return 2
        records.extend(read_jsonl(path))
    if not records:
        print("ERROR: no records read from inputs", file=sys.stderr)
        return 2

    pids = {r.professor_id for r in records}
    name_map = load_name_variants(Path(args.evidence_dir), pids)
    sheet_rows, map_rows = build_batch(
        records, name_map, seed=args.seed, batch_tag=args.batch_tag
    )

    _write_csv(Path(args.out), SHEET_FIELDS, sheet_rows)
    _write_csv(Path(args.map), MAP_FIELDS, map_rows)

    print(
        f"Wrote {len(sheet_rows)} claims from {len(records)} emails "
        f"({len(pids)} professors) to {args.out}; blinding map at {args.map}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
