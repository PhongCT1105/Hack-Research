"""The 2x2 factorial condition logic.

The ONLY differences between conditions are (1) whether the writer prompt includes the
evidence block and (2) whether verification runs afterward. Everything else — model,
temperature, max_tokens, instructions, word limit — is constant (see
docs/experimental_design.md, "Controls and Confound Management").
"""

from __future__ import annotations

from .schemas import Condition, EvidencePacket


def build_evidence_block(packet: EvidencePacket) -> str:
    """Render the packet into the writer/verifier evidence block (prompts/writer_v1.md)."""
    lines = [
        "Evidence packet (the ONLY permitted source of research-specific content):",
        "",
        "FACULTY PAGE SUMMARY:",
        packet.faculty_summary,
        "",
        "PAPERS:",
    ]
    for p in packet.papers:
        authors = ", ".join(p.authors)
        lines.append(f"[{p.paper_id}] {p.title} ({p.year}, {p.venue}). {authors}. {p.abstract}")
    if packet.focal_passages:
        lines += ["", "SELECTED PASSAGES:"]
        for fp in packet.focal_passages:
            lines.append(f"[{fp.paper_id} / {fp.section}] {fp.text}")
    return "\n".join(lines)


def writer_evidence_block(packet: EvidencePacket, condition: Condition) -> str:
    """Evidence block for the writer prompt: filled in B/D, empty in A/C."""
    return build_evidence_block(packet) if condition.writer_receives_evidence else ""


def professor_reference(packet: EvidencePacket) -> str:
    """Closed-book conditions receive only name + field; the packet carries the rest.

    Real names are inserted at generation time only and re-anonymized in all outputs
    (CLAUDE.md rule 4).
    """
    name = packet.real_name_do_not_export or f"Professor {packet.professor_id}"
    return f"{name}, a professor working in {packet.field}"
