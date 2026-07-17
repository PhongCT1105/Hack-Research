#!/usr/bin/env python
"""Auto-evaluator: label every extracted claim against its evidence packet with a judge LLM.

Produces machine labels in the same schema as annotations/human_labels.csv, keyed by the
blind claim id, so `scripts/compute_results.py --labels annotations/machine_labels.csv`
consumes them directly. Human labels (a subset) validate these via kappa.

The judge MUST be a different model family than the writer (CLAUDE.md: shared blind spots).
Default judge = anthropic/claude-3-haiku via OpenRouter; writer in the pilot is OpenAI.

Usage:
  python scripts/auto_evaluate.py --outputs outputs/full.jsonl \
    --blinding-map annotations/blinding_map.csv --out annotations/machine_labels.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outreach_eval.conditions import build_evidence_block
from outreach_eval.io_utils import read_jsonl
from outreach_eval.llm import LLMClient, RoleConfig, get_client
from outreach_eval.metrics import normalize_label
from outreach_eval.schemas import EvidencePacket

JUDGE_SYSTEM = (
    "You are a careful scientific factuality judge. For each claim about a professor's "
    "research, assign exactly ONE label based ONLY on the supplied evidence packet:\n"
    "- supported: the packet directly supports the claim as written\n"
    "- partially_supported: core idea is right but scope is narrower/missing in evidence\n"
    "- overstated: directionally related but stronger/broader/more certain than evidence\n"
    "- unsupported: no support in the packet, though the packet should contain it if true\n"
    "- contradicted: the packet directly conflicts with the claim\n"
    "- outside_evidence_scope: the packet is not designed to answer this fairly\n"
    "- subjective_or_generic: evaluative or generic praise with no checkable factual predicate\n"
    "Return JSON only."
)


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1].removeprefix("json").strip()
    try:
        return json.loads(text, strict=False)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start : end + 1], strict=False)
        raise


def judge_email(record, packet: EvidencePacket, client: LLMClient) -> dict[str, str]:
    """Return {claim_id -> canonical label string} for one email's claims."""
    claims = record.extracted_claims
    if not claims:
        return {}
    numbered = "\n".join(f"{i}. {c.atomic_claim}" for i, c in enumerate(claims, 1))
    user = (
        f"Evidence packet:\n{build_evidence_block(packet)}\n\n"
        f"Claims about the professor:\n{numbered}\n\n"
        'Return JSON: {"labels": [{"n": 1, "label": "supported", "reason": "..."}]}'
    )
    payload = _parse_json(client.complete(JUDGE_SYSTEM, user))
    out: dict[str, str] = {}
    for item in payload.get("labels", []):
        try:
            claim = claims[int(item["n"]) - 1]
        except (KeyError, ValueError, IndexError):
            continue
        label = normalize_label(item.get("label"))
        if label is not None:
            out[claim.claim_id] = label.value
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outputs", default="outputs/full.jsonl")
    ap.add_argument("--evidence-dir", default="data/evidence")
    ap.add_argument("--blinding-map", default="annotations/blinding_map.csv")
    ap.add_argument("--out", default="annotations/machine_labels.csv")
    ap.add_argument("--provider", default="openrouter")
    ap.add_argument("--model", default="anthropic/claude-3-haiku")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=2000)
    args = ap.parse_args()

    from dotenv import load_dotenv

    load_dotenv()

    records = read_jsonl(Path(args.outputs))
    with open(args.blinding_map, encoding="utf-8") as f:
        blind_by_orig = {r["original_claim_id"]: r for r in csv.DictReader(f)}
    client = get_client(
        RoleConfig(args.provider, args.model, args.temperature, args.max_tokens)
    )

    packets: dict[str, EvidencePacket] = {}
    rows, n_judged, n_fail = [], 0, 0
    for rec in records:
        pid = rec.professor_id
        if pid not in packets:
            packets[pid] = EvidencePacket.model_validate_json(
                (Path(args.evidence_dir) / f"{pid}.json").read_text()
            )
        try:
            labels = judge_email(rec, packets[pid], client)
        except Exception as exc:  # noqa: BLE001 — one bad email must not abort the sweep
            n_fail += 1
            print(f"[!] {rec.run_id} judge failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        for claim in rec.extracted_claims:
            label = labels.get(claim.claim_id)
            if label is None:
                continue
            blind = blind_by_orig.get(claim.claim_id)
            if not blind:
                continue
            n_judged += 1
            rows.append({
                "email_id": blind["email_id"], "professor_id": "", "condition_hidden": "machine",
                "claim_id": blind["claim_id"], "atomic_claim": claim.atomic_claim,
                "claim_type": claim.claim_type.value if claim.claim_type else "",
                "evidence_excerpt": "", "label_annotator_1": label, "label_annotator_2": "",
                "final_label": label, "notes": "auto-evaluator",
            })
        print(f"[{rec.run_id}] {len(labels)} claims judged")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    fields = ["email_id", "professor_id", "condition_hidden", "claim_id", "atomic_claim",
              "claim_type", "evidence_excerpt", "label_annotator_1", "label_annotator_2",
              "final_label", "notes"]
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"\nWrote {n_judged} machine labels to {args.out} ({n_fail} email(s) failed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
