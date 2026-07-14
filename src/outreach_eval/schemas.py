"""Data contracts for the outreach-eval study.

These Pydantic models are the source of truth for every artifact in the pipeline.
`data/evidence/evidence_packet.schema.json` is exported from EvidencePacket
(see `python -m outreach_eval.schemas` at the bottom). If a contract must change
before the freeze, update models + JSON schema together and log it in
docs/decision_log.md. After the freeze: no changes.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Experimental conditions (2x2 factorial)
# ---------------------------------------------------------------------------


class Condition(str, Enum):
    A = "A"  # no evidence to writer, no verification (closed-book baseline)
    B = "B"  # evidence to writer, no verification
    C = "C"  # no evidence to writer, evidence-based verification afterward
    D = "D"  # evidence to writer and verification afterward

    @property
    def writer_receives_evidence(self) -> bool:
        return self in (Condition.B, Condition.D)

    @property
    def verification_applied(self) -> bool:
        return self in (Condition.C, Condition.D)


# ---------------------------------------------------------------------------
# Evidence packet (one JSON file per professor, data/evidence/<ID>.json)
# ---------------------------------------------------------------------------


class Provenance(BaseModel):
    source_url: str
    retrieved: date
    access_method: str = Field(
        description="How the item was obtained, e.g. 'faculty page', 'openalex api', 'pdf'"
    )
    notes: str = ""


class Paper(BaseModel):
    paper_id: str = Field(description="Packet-local id, e.g. 'P1'")
    title: str
    year: int
    venue: str
    authors: list[str] = Field(description="Full author list, order as published")
    doi: str = ""
    abstract: str
    provenance: Provenance


class FocalPassage(BaseModel):
    paper_id: str = Field(description="Must reference a Paper.paper_id in the same packet")
    section: str = Field(description="intro | methods | results | discussion | project page")
    text: str = Field(description="Short verbatim passage (a few sentences)")
    provenance: Provenance


class EvidencePacket(BaseModel):
    """Everything the writer (conditions B/D) and verifier (C/D) may rely on.

    'Unsupported' in annotation means unsupported by THIS packet — the packet is
    the agreed evidence scope, so its construction quality is load-bearing.
    """

    professor_id: str = Field(pattern=r"^(CS|PSY|BIO|MOCK)-\d{2}$")
    field: str = Field(description="cs_ai | psychology | biomedicine (mock allowed)")
    career_stage: str = Field(description="assistant | associate | full")
    visibility_band: str = Field(description="low | medium | high citation-visibility band")
    faculty_summary: str = Field(
        description="Short research summary from the official faculty/lab page (themes only)"
    )
    faculty_summary_provenance: Provenance
    papers: list[Paper] = Field(min_length=1, description="6 for pilot, 8 recommended at scale")
    focal_passages: list[FocalPassage] = Field(
        default_factory=list,
        description="2-4 passages for 1-2 focal papers; cover method/result detail",
    )
    # Real name lives ONLY here and in the gitignored private roster.
    real_name_do_not_export: str = Field(
        default="",
        description="Never copied into outputs, annotations, analysis, or the paper",
    )


# ---------------------------------------------------------------------------
# Claims and verifier edits
# ---------------------------------------------------------------------------


class ClaimType(str, Enum):
    RESEARCH_TOPIC = "research_topic"
    METHOD = "method"
    DATASET = "dataset"
    RESULT = "result"
    IMPACT = "impact"
    NOVELTY = "novelty"
    COLLABORATION = "collaboration"
    AUTHORSHIP = "authorship"
    CROSS_PAPER_SYNTHESIS = "cross_paper_synthesis"


class ClaimLabel(str, Enum):
    SUPPORTED = "supported"
    PARTIALLY_SUPPORTED = "partially_supported"
    OVERSTATED = "overstated"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    OUTSIDE_EVIDENCE_SCOPE = "outside_evidence_scope"
    SUBJECTIVE_OR_GENERIC = "subjective_or_generic"


SEVERE_LABELS = {ClaimLabel.UNSUPPORTED, ClaimLabel.CONTRADICTED}
# Excluded from the factual denominator (reported separately):
NON_FACTUAL_LABELS = {ClaimLabel.OUTSIDE_EVIDENCE_SCOPE, ClaimLabel.SUBJECTIVE_OR_GENERIC}


class ExtractedClaim(BaseModel):
    claim_id: str
    atomic_claim: str = Field(description="Smallest independently checkable proposition")
    claim_type: ClaimType | None = None
    source_sentence: str = ""
    # Machine label from the auto-evaluator/verifier; human gold lives in
    # annotations/human_labels.csv and always wins.
    machine_label: ClaimLabel | None = None
    evidence_excerpt: str = ""


class EditAction(str, Enum):
    KEEP = "keep"
    SOFTEN = "soften"
    REWRITE = "rewrite"
    DELETE = "delete"


class VerifierEdit(BaseModel):
    claim_id: str
    action: EditAction
    original_span: str
    revised_span: str = Field(default="", description="Empty when action == delete")
    reason: str


# ---------------------------------------------------------------------------
# Output record (one JSONL line per generated email)
# ---------------------------------------------------------------------------


class EmailRecord(BaseModel):
    run_id: str = Field(description="'{professor_id}_{condition}_{seed}'")
    professor_id: str
    condition: Condition
    seed: int
    writer_received_evidence: bool
    verification_applied: bool
    original_email: str
    verified_email: str = Field(
        default="", description="Empty in conditions A/B (no verification)"
    )
    extracted_claims: list[ExtractedClaim] = Field(default_factory=list)
    verifier_edits: list[VerifierEdit] = Field(default_factory=list)
    model: str
    prompt_version: str = "v1"
    timestamp: str = ""

    @property
    def final_email(self) -> str:
        return self.verified_email if self.verification_applied else self.original_email


if __name__ == "__main__":
    # Export the evidence packet JSON schema:
    #   python -m outreach_eval.schemas > data/evidence/evidence_packet.schema.json
    import json

    print(json.dumps(EvidencePacket.model_json_schema(), indent=2))
