# Annotation Rubric

**Status: DRAFT — frozen after the 16-email pilot review.**

Annotators decompose each email into atomic research-related claims, then assign each
claim exactly one **label** and one **claim type**. Annotators are blinded to condition
and to whether text is original or verified.

## Unit of Annotation: the Atomic Claim

The smallest research-relevant proposition that can be independently checked against
the evidence packet. Procedure:

1. Mark research-related sentences.
2. Split each into atomic claims (a sentence mixing propositions is split before labeling).
3. Assign one label + one claim type per claim, citing the evidence excerpt used.

## Labels

| Label | Decision rule | Example |
|---|---|---|
| `supported` | Packet directly supports the claim as written | "Professor A studies calibration in medical imaging models" (packet shows this) |
| `partially_supported` | Core idea related, but scope missing/narrower in evidence | "Works on trustworthy AI in healthcare" when packet only shows chest X-ray calibration |
| `overstated` | Directionally related but stronger/broader/more certain than evidence permits | "Dramatically outperforms prior work" when abstract reports gains on one benchmark |
| `unsupported` | No supporting evidence, though the packet *should* contain it if true | "Introduced a new benchmark for multimodal reasoning" — no such paper in packet |
| `contradicted` | Packet directly conflicts with the claim | "Uses randomized controlled trials" when the paper is observational |
| `outside_evidence_scope` | Packet is not designed to answer this fairly | "Professor A is an outstanding mentor" |
| `subjective_or_generic` | Evaluative or generic praise with no checkable factual predicate — tagged, **excluded from the factual denominator** | "Your research is very impressive" |

**Critical distinction:** `unsupported` = *not warranted by the agreed packet*, not
"false in the world." If the claim requires information the packet was never meant to
contain, use `outside_evidence_scope`.

## Claim Types

`research_topic` · `method` · `dataset` · `result` · `impact` · `novelty` ·
`collaboration` · `authorship` · `cross_paper_synthesis`

## Type-Specific Decision Rules

| Claim type | Rule |
|---|---|
| **Impact** | Support only if impact is explicitly stated *and appropriately hedged*. "Could help clinicians prioritize follow-up" is supported only if that wording appears; "has transformed clinical care" without evidence is unsupported. |
| **Novelty** | Requires unusually strong evidence. "Pioneered / first" is supported only if the packet explicitly documents priority; active work in an area ≠ pioneering (→ overstated/unsupported). |
| **Causal** (within result) | "X increased Y" requires a study design that justifies causality; association reported as causation → overstated. |
| **Cross-paper synthesis** | Accept only if ≥2 supplied papers justify the synthesized theme. A "unified theory" from loosely related papers → overstated/unsupported. |
| **Authorship** | Professor must actually be an author, with no inflated role. Wrong co-author named → contradicted. |
| **Method** | Must match the actual method family/study design. "Uses fMRI" when the paper is behavioral-only → contradicted. |
| **Dataset** | Must match the named dataset/corpus/population. |
| **Result** | Must be actually stated; numbers must be anchored. "SOTA on all major benchmarks" from one benchmark result → overstated/unsupported. |

## Annotation Sheet Fields

```
email_id, professor_id, condition_hidden, claim_id, atomic_claim, claim_type,
evidence_excerpt, label_annotator_1, label_annotator_2, final_label, notes
```

(`condition_hidden` is an opaque batch key; the true condition mapping lives in the
gitignored blinding map maintained by the pipeline owner.)

## Procedure & Quality

- **Roles:** Kanan = primary annotator/manager; Azhdar = second blinded annotator;
  Phong = disagreement adjudicator; Abhinav = condition blinding + data prep.
- **Double-annotate ≥25%** of claims; adjudicate all disagreements.
- Keep a decision log of edge cases (append to this file's companion,
  `annotations/edge_cases.md`, as they arise).
- Report Cohen's κ (or Krippendorff's α) for human–human agreement.
- Any automatic evaluator must be validated against final adjudicated human labels
  (precision/recall/F1 per label + calibration summary).

## Completion Criteria

- [ ] Claims are atomic and independently judgeable
- [ ] Annotators could not see condition or original/verified status
- [ ] ≥25% of claims double-annotated; disagreements documented and adjudicated
- [ ] Agreement statistics reported
- [ ] Both factuality AND supported-personalization metrics reported
