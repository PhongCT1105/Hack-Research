#!/usr/bin/env python
"""Turn generated emails + human labels into the results table and figures.

Workstream 3 analysis. Joins:
  outputs/*.jsonl            (EmailRecord: word counts, verifier edits)
  annotations/blinding_map.csv  (blind claim id -> run_id, condition)  [gitignored]
  annotations/human_labels.csv  (blind claim id -> final_label + two annotators)

Produces analysis/results.csv, analysis/figures/*.png, and (best-effort) a
mixed-effects model summary. Figures/model need the `analysis` extra
(`pip install -e ".[analysis]"`); the results CSV needs only the base install.

Usage:
  python scripts/compute_results.py \
    --outputs outputs/pilot.jsonl \
    --labels annotations/human_labels.csv \
    --blinding-map annotations/blinding_map.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from outreach_eval.io_utils import read_jsonl
from outreach_eval.metrics import (
    ClaimLabel,
    ConditionMetrics,
    cohen_kappa,
    condition_metrics,
    normalize_label,
)

RESULTS_FIELDS = [
    "condition",
    "n_emails",
    "n_factual_claims",
    "severe_error_rate",
    "ser_ci_low",
    "ser_ci_high",
    "overstatement_rate",
    "email_level_severe_rate",
    "supported_personalization_density",
    "verifier_deletion_rate",
    "verifier_rewrite_rate",
]


def compute(records, label_rows, map_rows):
    """Pure core: return (list[ConditionMetrics] sorted by condition, kappa)."""
    words_by_run = {r.run_id: len(r.final_email.split()) for r in records}
    edits_by_run = {r.run_id: [e.action.value for e in r.verifier_edits] for r in records}
    map_by_claim = {m["claim_id"]: m for m in map_rows}

    cond_email_labels: dict[str, dict[str, list[ClaimLabel]]] = defaultdict(
        lambda: defaultdict(list)
    )
    kappa_pairs = []
    for row in label_rows:
        mapping = map_by_claim.get(row.get("claim_id"))
        if not mapping:
            continue
        final = normalize_label(row.get("final_label"))
        if final is not None:
            cond_email_labels[mapping["condition"]][mapping["run_id"]].append(final)
        a = normalize_label(row.get("label_annotator_1"))
        b = normalize_label(row.get("label_annotator_2"))
        if a is not None and b is not None:
            kappa_pairs.append((a, b))

    results = []
    for cond in sorted(cond_email_labels):
        claims_by_email = dict(cond_email_labels[cond])
        runs = set(claims_by_email)
        words = {rid: words_by_run.get(rid, 0) for rid in runs}
        edits = {rid: edits_by_run.get(rid, []) for rid in runs if edits_by_run.get(rid)}
        results.append(
            condition_metrics(
                cond,
                claims_by_email=claims_by_email,
                words_by_email=words,
                verifier_edits_by_email=edits or None,
            )
        )
    return results, cohen_kappa(kappa_pairs)


def _round(value, digits=4):
    return "" if value is None else round(value, digits)


def write_results_csv(path: Path, results: list[ConditionMetrics]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RESULTS_FIELDS)
        writer.writeheader()
        for m in results:
            writer.writerow(
                {
                    "condition": m.condition,
                    "n_emails": m.n_emails,
                    "n_factual_claims": m.n_factual_claims,
                    "severe_error_rate": _round(m.severe_error_rate),
                    "ser_ci_low": _round(m.ser_ci[0]) if m.ser_ci else "",
                    "ser_ci_high": _round(m.ser_ci[1]) if m.ser_ci else "",
                    "overstatement_rate": _round(m.overstatement_rate),
                    "email_level_severe_rate": _round(m.email_level_severe_rate),
                    "supported_personalization_density": _round(
                        m.supported_personalization_density
                    ),
                    "verifier_deletion_rate": _round(m.verifier_deletion_rate),
                    "verifier_rewrite_rate": _round(m.verifier_rewrite_rate),
                }
            )


def render_figures(results: list[ConditionMetrics], figures_dir: Path) -> bool:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed (pip install -e '.[analysis]') — skipping figures")
        return False

    figures_dir.mkdir(parents=True, exist_ok=True)
    conds = [m.condition for m in results]

    # Figure 1: SER by condition with bootstrap CIs.
    sers = [m.severe_error_rate or 0.0 for m in results]
    lows = [(m.severe_error_rate or 0.0) - (m.ser_ci[0] if m.ser_ci else m.severe_error_rate or 0.0)
            for m in results]
    highs = [(m.ser_ci[1] if m.ser_ci else m.severe_error_rate or 0.0) - (m.severe_error_rate or 0.0)
             for m in results]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(conds, sers, yerr=[lows, highs], capsize=6, color="#4C72B0")
    ax.set_ylabel("Severe Error Rate")
    ax.set_xlabel("Condition")
    ax.set_title("Severe Error Rate by condition (95% bootstrap CI)")
    fig.tight_layout()
    fig.savefig(figures_dir / "ser_by_condition.png", dpi=150)
    plt.close(fig)

    # Figure 2: Supported-Specificity Frontier (upper-left is best).
    fig, ax = plt.subplots(figsize=(6, 5))
    for m in results:
        x = m.severe_error_rate or 0.0
        y = m.supported_personalization_density or 0.0
        ax.scatter(x, y, s=80)
        ax.annotate(m.condition, (x, y), textcoords="offset points", xytext=(6, 6))
    ax.set_xlabel("Severe Error Rate (lower better)")
    ax.set_ylabel("Supported Personalization Density (higher better)")
    ax.set_title("Supported-Specificity Frontier")
    fig.tight_layout()
    fig.savefig(figures_dir / "frontier.png", dpi=150)
    plt.close(fig)
    return True


def fit_mixed_model(records, label_rows, map_rows, out_path: Path) -> None:
    """Best-effort logistic mixed model; falls back to a per-professor note at small N."""
    map_by_claim = {m["claim_id"]: m for m in map_rows}
    rows = []
    for row in label_rows:
        mapping = map_by_claim.get(row.get("claim_id"))
        final = normalize_label(row.get("final_label"))
        if not mapping or final is None or final not in (
            ClaimLabel.SUPPORTED, ClaimLabel.PARTIALLY_SUPPORTED, ClaimLabel.OVERSTATED,
            ClaimLabel.UNSUPPORTED, ClaimLabel.CONTRADICTED,
        ):
            continue
        cond = mapping["condition"]
        rows.append({
            "error": 1 if final in (ClaimLabel.UNSUPPORTED, ClaimLabel.CONTRADICTED) else 0,
            "grounding": 1 if cond in ("B", "D") else 0,
            "verification": 1 if cond in ("C", "D") else 0,
            "professor": mapping.get("professor_id", "NA"),
            "email": mapping["run_id"],
        })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if len({r["professor"] for r in rows}) < 3 or len(rows) < 30:
        out_path.write_text(
            "Mixed-effects model skipped: too few professors/claims at this scale.\n"
            "Fallback: report per-condition SER + bootstrap CIs (analysis/results.csv) "
            "and per-professor paired comparisons. Fit the full model on the 96-email run.\n"
        )
        print(f"mixed model: fallback note written to {out_path}")
        return
    try:
        import pandas as pd
        import statsmodels.formula.api as smf

        df = pd.DataFrame(rows)
        model = smf.mixedlm(
            "error ~ grounding * verification", df, groups=df["professor"]
        ).fit()
        out_path.write_text(str(model.summary()))
        print(f"mixed model: summary written to {out_path}")
    except Exception as exc:  # noqa: BLE001 — model instability is expected; never fatal
        out_path.write_text(f"Mixed-effects fit failed ({type(exc).__name__}: {exc}).\n")
        print(f"mixed model: fit failed, note written to {out_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outputs", default="outputs/pilot.jsonl")
    ap.add_argument("--labels", default="annotations/human_labels.csv")
    ap.add_argument("--blinding-map", default="annotations/blinding_map.csv")
    ap.add_argument("--out-csv", default="analysis/results.csv")
    ap.add_argument("--figures-dir", default="analysis/figures")
    ap.add_argument("--model-summary", default="analysis/model_summary.txt")
    args = ap.parse_args()

    for label, path in [("outputs", args.outputs), ("labels", args.labels),
                        ("blinding map", args.blinding_map)]:
        if not Path(path).exists():
            print(f"ERROR: {label} not found: {path}", file=sys.stderr)
            return 2

    records = read_jsonl(Path(args.outputs))
    with open(args.labels, encoding="utf-8") as f:
        label_rows = list(csv.DictReader(f))
    with open(args.blinding_map, encoding="utf-8") as f:
        map_rows = list(csv.DictReader(f))

    results, kappa = compute(records, label_rows, map_rows)
    write_results_csv(Path(args.out_csv), results)
    render_figures(results, Path(args.figures_dir))
    fit_mixed_model(records, label_rows, map_rows, Path(args.model_summary))

    print(f"\nWrote {args.out_csv} ({len(results)} conditions)")
    print(f"Inter-annotator Cohen's kappa: {kappa if kappa is not None else 'n/a (no double-annotated pairs)'}")
    for m in results:
        print(f"  {m.condition}: SER={m.severe_error_rate} SPD={m.supported_personalization_density} "
              f"n_claims={m.n_factual_claims}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
