"""Metrics for the outreach-eval study (Workstream 3 analysis half).

Pure, dependency-light functions (stdlib only) so they are testable without the
optional `analysis` extras. Figures and mixed-effects models live in
`scripts/compute_results.py`, which imports matplotlib/statsmodels lazily.

Label handling is tolerant: annotators may write "Supported" or "supported",
"Outside evidence scope" or "outside_evidence_scope" — `normalize_label` canonicalizes
both to the `ClaimLabel` enum (see docs/annotation_rubric.md).
"""

from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass

from .schemas import ClaimLabel

# Denominator rules (docs/analysis_plan.md):
FACTUAL_LABELS = {
    ClaimLabel.SUPPORTED,
    ClaimLabel.PARTIALLY_SUPPORTED,
    ClaimLabel.OVERSTATED,
    ClaimLabel.UNSUPPORTED,
    ClaimLabel.CONTRADICTED,
}
SEVERE_LABELS = {ClaimLabel.UNSUPPORTED, ClaimLabel.CONTRADICTED}
NON_FACTUAL_LABELS = {ClaimLabel.OUTSIDE_EVIDENCE_SCOPE, ClaimLabel.SUBJECTIVE_OR_GENERIC}


def normalize_label(raw: object) -> ClaimLabel | None:
    """Map a free-form annotator label to a ClaimLabel, or None if unrecognized."""
    if raw is None:
        return None
    key = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if not key:
        return None
    try:
        return ClaimLabel(key)
    except ValueError:
        return None


def _factual(labels: list[ClaimLabel]) -> list[ClaimLabel]:
    return [x for x in labels if x in FACTUAL_LABELS]


def severe_error_rate(labels: list[ClaimLabel]) -> float | None:
    """(unsupported + contradicted) / factual claims. None if no factual claims."""
    factual = _factual(labels)
    if not factual:
        return None
    severe = sum(1 for x in factual if x in SEVERE_LABELS)
    return severe / len(factual)


def label_rate(labels: list[ClaimLabel], target: set[ClaimLabel]) -> float | None:
    factual = _factual(labels)
    if not factual:
        return None
    return sum(1 for x in factual if x in target) / len(factual)


def supported_personalization_density(n_supported: int, total_words: int) -> float | None:
    """Supported research-specific claims per 100 words. None if no words."""
    if total_words <= 0:
        return None
    return 100.0 * n_supported / total_words


def cohen_kappa(pairs: list[tuple[ClaimLabel, ClaimLabel]]) -> float | None:
    """Cohen's kappa for two annotators over paired label decisions.

    None if fewer than one pair. Returns 1.0 for perfect agreement even when only a
    single category appears (degenerate p_e == 1 is treated as full agreement).
    """
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    a_counts = Counter(a for a, _ in pairs)
    b_counts = Counter(b for _, b in pairs)
    expected = sum((a_counts[c] / n) * (b_counts[c] / n) for c in set(a_counts) | set(b_counts))
    if math.isclose(expected, 1.0):
        return 1.0 if math.isclose(observed, 1.0) else 0.0
    return (observed - expected) / (1.0 - expected)


def bootstrap_ci(
    values: list[float], *, iterations: int = 2000, alpha: float = 0.05, seed: int = 42
) -> tuple[float, float] | None:
    """Percentile bootstrap CI for the mean of per-unit values (e.g. per-email SER).

    Deterministic given `seed`. None if no values.
    """
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    rng = random.Random(seed)
    n = len(clean)
    means = []
    for _ in range(iterations):
        sample = [clean[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int((alpha / 2) * iterations)]
    hi = means[min(iterations - 1, int((1 - alpha / 2) * iterations))]
    return (lo, hi)


@dataclass
class ConditionMetrics:
    condition: str
    n_emails: int
    n_factual_claims: int
    severe_error_rate: float | None
    overstatement_rate: float | None
    email_level_severe_rate: float | None
    supported_personalization_density: float | None
    ser_ci: tuple[float, float] | None
    verifier_deletion_rate: float | None
    verifier_rewrite_rate: float | None


def condition_metrics(
    condition: str,
    *,
    claims_by_email: dict[str, list[ClaimLabel]],
    words_by_email: dict[str, int],
    verifier_edits_by_email: dict[str, list[str]] | None = None,
) -> ConditionMetrics:
    """Aggregate all metrics for one experimental condition.

    `claims_by_email`: run_id -> list of claim labels in that email.
    `words_by_email`: run_id -> final-email word count.
    `verifier_edits_by_email`: run_id -> list of edit actions (for C/D only).
    """
    all_labels = [lbl for labels in claims_by_email.values() for lbl in labels]
    factual_total = len(_factual(all_labels))

    per_email_ser = [
        ser for labels in claims_by_email.values() if (ser := severe_error_rate(labels)) is not None
    ]
    email_severe = [
        1.0 if any(x in SEVERE_LABELS for x in labels) else 0.0
        for labels in claims_by_email.values()
        if _factual(labels)
    ]
    n_supported = sum(1 for x in all_labels if x == ClaimLabel.SUPPORTED)
    total_words = sum(words_by_email.get(rid, 0) for rid in claims_by_email)

    del_rate = rewrite_rate = None
    if verifier_edits_by_email:
        edits = [a for actions in verifier_edits_by_email.values() for a in actions]
        if edits:
            del_rate = sum(1 for a in edits if a == "delete") / len(edits)
            rewrite_rate = sum(1 for a in edits if a in ("rewrite", "soften")) / len(edits)

    return ConditionMetrics(
        condition=condition,
        n_emails=len(claims_by_email),
        n_factual_claims=factual_total,
        severe_error_rate=severe_error_rate(all_labels),
        overstatement_rate=label_rate(all_labels, {ClaimLabel.OVERSTATED}),
        email_level_severe_rate=(sum(email_severe) / len(email_severe) if email_severe else None),
        supported_personalization_density=supported_personalization_density(
            n_supported, total_words
        ),
        ser_ci=bootstrap_ci(per_email_ser),
        verifier_deletion_rate=del_rate,
        verifier_rewrite_rate=rewrite_rate,
    )
