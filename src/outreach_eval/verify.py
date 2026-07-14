"""Verification stage (conditions C/D): evidence-based minimal-edit correction.

Spec: tasks/02_pipeline.md step 4; protocol in docs/experimental_design.md.
Philosophy (RARR/FLEEK): preserve supported specificity, soften overstatements,
remove/generalize unsupported or contradicted content. Never add new claims.
"""

from __future__ import annotations

import json
from pathlib import Path

from .conditions import build_evidence_block
from .generate import load_prompt_sections
from .llm import LLMClient
from .schemas import ClaimLabel, ClaimType, EmailRecord, EditAction, EvidencePacket, ExtractedClaim, VerifierEdit


def verify_email(
    record: EmailRecord,
    packet: EvidencePacket,
    client: LLMClient,
    prompt_path: Path,
) -> EmailRecord:
    """Populate verified_email, extracted_claims, and verifier_edits on the record.

    Only called when record.verification_applied is True. Returns an updated copy;
    the original record is never mutated (outputs are append-only).
    """
    if not record.verification_applied:
        raise ValueError(f"verify_email called for condition {record.condition} run {record.run_id}")

    system, user_template = load_prompt_sections(prompt_path)
    user = user_template.replace("{evidence_block}", build_evidence_block(packet)).replace(
        "{draft_email}", record.original_email
    )

    raw = client.complete(system, user)
    payload = _parse_verifier_json(raw)

    claims = [
        ExtractedClaim(
            claim_id=c["claim_id"],
            atomic_claim=c["atomic_claim"],
            claim_type=_maybe(ClaimType, c.get("claim_type")),
            machine_label=_maybe(ClaimLabel, c.get("verdict")),
            evidence_excerpt=c.get("evidence_excerpt", ""),
        )
        for c in payload.get("claims", [])
    ]
    edits = [
        VerifierEdit(
            claim_id=e["claim_id"],
            action=EditAction(e["action"]),
            original_span=e.get("original_span", ""),
            revised_span=e.get("revised_span", ""),
            reason=e.get("reason", ""),
        )
        for e in payload.get("edits", [])
    ]

    return record.model_copy(
        update={
            "verified_email": payload["revised_email"],
            "extracted_claims": claims,
            "verifier_edits": edits,
        }
    )


def _parse_verifier_json(raw: str) -> dict:
    """Verifier output must be a JSON object; tolerate code fences, nothing else.

    A malformed response is a failed run: re-run it, don't hand-patch (CLAUDE.md).
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text.removeprefix("json").strip()
    return json.loads(text)


def _maybe(enum_cls, value):
    try:
        return enum_cls(value) if value else None
    except ValueError:
        return None


def deletion_rate(record: EmailRecord) -> float:
    """Fraction of verifier edits that delete content — the 'verifier wins by
    erasing specificity' guardrail metric (docs/analysis_plan.md)."""
    if not record.verifier_edits:
        return 0.0
    deletes = sum(1 for e in record.verifier_edits if e.action == EditAction.DELETE)
    return deletes / len(record.verifier_edits)
