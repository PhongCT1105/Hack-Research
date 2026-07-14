"""Claim inventory for annotation: decompose every email into atomic claims.

Spec: tasks/02_pipeline.md step 8. Extraction is a DRAFT for human annotators —
optimize recall and atomicity, never labels. Runs on ALL emails (all conditions;
for C/D, on the final verified email — the artifact a recipient would read).
"""

from __future__ import annotations

import json
from pathlib import Path

from .generate import load_prompt_sections
from .llm import LLMClient
from .schemas import ClaimType, EmailRecord, ExtractedClaim


def extract_claims(
    record: EmailRecord,
    client: LLMClient,
    prompt_path: Path,
) -> list[ExtractedClaim]:
    system, user_template = load_prompt_sections(prompt_path)
    user = user_template.replace("{email_text}", record.final_email)

    raw = client.complete(system, user)
    payload = _parse_json(raw)

    claims = []
    for c in payload.get("claims", []):
        try:
            claim_type = ClaimType(c.get("claim_type"))
        except ValueError:
            claim_type = None  # annotators assign/correct types anyway
        claims.append(
            ExtractedClaim(
                claim_id=f"{record.run_id}_{c['claim_id']}",
                atomic_claim=c["atomic_claim"],
                claim_type=claim_type,
                source_sentence=c.get("source_sentence", ""),
            )
        )
    return claims


def _parse_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text.removeprefix("json").strip()
    return json.loads(text)
