"""Writer stage: generate one email per (professor, condition, seed).

Spec: tasks/02_pipeline.md steps 2-3; controls in docs/experimental_design.md.
The prompt template is prompts/writer_v1.md — this module only fills its slots;
wording lives in the prompt file, never in code.
"""

from __future__ import annotations

from pathlib import Path

from .conditions import professor_reference, writer_evidence_block
from .io_utils import utc_now
from .llm import LLMClient
from .schemas import Condition, EmailRecord, EvidencePacket

PROMPT_VERSION = "v1"


def load_prompt_sections(prompt_path: Path) -> tuple[str, str]:
    """Split a prompt file into (system, user) sections.

    Prompt files use '## System' and '## User' headers; the '## Slot definitions'
    section and change log are documentation, not part of the prompt.
    """
    text = prompt_path.read_text(encoding="utf-8")
    system = _section(text, "## System")
    user = _section(text, "## User")
    return system, user


def _section(text: str, header: str) -> str:
    if header not in text:
        raise ValueError(f"Prompt file missing section {header!r}")
    body = text.split(header, 1)[1]
    for stop in ("\n## ", "\n---"):
        idx = body.find(stop)
        if idx != -1:
            body = body[:idx]
    return body.strip()


def generate_email(
    packet: EvidencePacket,
    condition: Condition,
    seed: int,
    client: LLMClient,
    prompt_path: Path,
    email_word_limit: int,
) -> EmailRecord:
    """Run the writer for one cell. Verification (C/D) happens in verify.py."""
    system, user_template = load_prompt_sections(prompt_path)
    user = (
        user_template.replace("{email_word_limit}", str(email_word_limit))
        .replace("{professor_reference}", professor_reference(packet))
        .replace("{evidence_block}", writer_evidence_block(packet, condition))
    )

    email_text = client.complete(system, user, seed=seed)

    return EmailRecord(
        run_id=f"{packet.professor_id}_{condition.value}_{seed}",
        professor_id=packet.professor_id,
        condition=condition,
        seed=seed,
        writer_received_evidence=condition.writer_receives_evidence,
        verification_applied=condition.verification_applied,
        original_email=email_text,
        model=client.model,
        prompt_version=PROMPT_VERSION,
        timestamp=utc_now(),
    )
