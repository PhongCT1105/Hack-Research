#!/usr/bin/env python
"""Run the generation pipeline for the pilot (or a dry run on the mock packet).

Usage:
    python scripts/run_pilot.py --config config/config.yaml            # real pilot
    python scripts/run_pilot.py --config config/config.yaml --dry-run  # mock, offline

Dry run: forces the mock provider and MOCK-01 packet; produces schema-valid records
end-to-end without network access. The real pilot covers
pilot.professor_ids x conditions x seeds (2 x 4 x 2 = 16 emails).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outreach_eval.extract_claims import extract_claims
from outreach_eval.generate import generate_email
from outreach_eval.io_utils import append_jsonl, append_manifest_row, utc_now
from outreach_eval.llm import get_client, role_config_from_dict
from outreach_eval.schemas import Condition, EvidencePacket
from outreach_eval.verify import verify_email


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="mock provider + MOCK-01 packet")
    ap.add_argument("--out", default=None, help="override output JSONL path")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    roles = {name: role_config_from_dict(d) for name, d in cfg["roles"].items()}
    if args.dry_run:
        roles = {name: rc.__class__(**{**rc.__dict__, "provider": "mock"}) for name, rc in roles.items()}

    writer = get_client(roles["writer"])
    verifier = get_client(roles["verifier"])
    extractor = get_client(roles["claim_extractor"])

    evidence_dir = Path(cfg["paths"]["evidence_dir"])
    professor_ids = ["MOCK-01"] if args.dry_run else cfg["pilot"]["professor_ids"]
    conditions = [Condition(c) for c in cfg["experiment"]["conditions"]]
    seeds = cfg["experiment"]["seeds"]
    word_limit = cfg["experiment"]["email_word_limit"]

    out_path = Path(args.out) if args.out else Path(cfg["paths"]["outputs_dir"]) / (
        "dry_run.jsonl" if args.dry_run else "pilot.jsonl"
    )
    manifest_path = Path(cfg["paths"]["logs_dir"]) / "run_manifest.csv"
    writer_prompt = Path(cfg["prompts"]["writer"])
    verifier_prompt = Path(cfg["prompts"]["verifier"])
    extractor_prompt = Path(cfg["prompts"]["claim_extractor"])

    n = 0
    for pid in professor_ids:
        packet = EvidencePacket.model_validate_json((evidence_dir / f"{pid}.json").read_text())
        for condition in conditions:
            for seed in seeds:
                record = generate_email(packet, condition, seed, writer, writer_prompt, word_limit)
                if condition.verification_applied:
                    record = verify_email(record, packet, verifier, verifier_prompt)
                record = record.model_copy(
                    update={"extracted_claims": extract_claims(record, extractor, extractor_prompt)}
                )
                append_jsonl(out_path, record)
                append_manifest_row(
                    manifest_path,
                    {
                        "run_id": record.run_id,
                        "professor_id": pid,
                        "condition": condition.value,
                        "seed": seed,
                        "writer_provider": roles["writer"].provider,
                        "writer_model": writer.model,
                        "verifier_provider": roles["verifier"].provider if condition.verification_applied else "",
                        "verifier_model": verifier.model if condition.verification_applied else "",
                        "prompt_version": record.prompt_version,
                        "temperature": roles["writer"].temperature,
                        "timestamp": utc_now(),
                    },
                )
                n += 1
                print(f"[{n}] {record.run_id} ok")

    print(f"\nWrote {n} records to {out_path}; manifest at {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
