"""Recompute every manuscript statistic for the NSRI revision (NSRI-J-2026-0178).

The original `compute_results.py` reports point estimates with a percentile
bootstrap over per-email severe-error rates. That bootstrap is degenerate when a
condition contains zero severe errors: every resample is zero, so the interval
collapses to [0, 0] and reads as a guarantee of zero risk. This script replaces
those intervals with exact (Clopper-Pearson) bounds, adds the cluster-aware
zero-event bound, and computes the reliability, coverage, and heterogeneity
statistics the revision requires.

Outputs (written to analysis/revision/):
    table3_primary.csv           per-condition factuality + specificity
    table3b_both_evaluators.csv  per-condition SER under each automatic evaluator
    table4_confusion.csv         human x automatic confusion matrix
    table5_human_coverage.csv    human-subset coverage and human SER per condition
    table6_field.csv             per-field severe-error rates
    table6_professor.csv         per-professor rates + leave-one-field-out sensitivity
    reliability.csv              agreement statistics with confidence intervals
    verifier_edits.csv           verifier delete/soften/keep decisions
    run_metadata.csv             de-identified per-run word counts + verifier actions,
                                 so the tables reproduce without the withheld emails
    report.md                    human-readable summary of all of the above

Run:
    python scripts/compute_revision_stats.py
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy import stats
from statsmodels.stats.inter_rater import cohens_kappa

REPO = Path(__file__).resolve().parents[1]

# Labels excluded from the SER denominator, and the two that count as severe.
NON_FACTUAL = frozenset({"outside_evidence_scope", "subjective_or_generic"})
SEVERE = frozenset({"unsupported", "contradicted"})
CONDITIONS = ("A", "B", "C", "D")
FIELD_OF = {"CS": "computer science", "PSY": "psychology", "BIO": "biomedicine"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact binomial interval. Well defined at k=0 and k=n, unlike the bootstrap."""
    if n == 0:
        return (float("nan"), float("nan"))
    lo = 0.0 if k == 0 else float(stats.beta.ppf(alpha / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1 - alpha / 2, k + 1, n - k))
    return (lo, hi)


def cluster_bootstrap(per_cluster: list[tuple[int, int]], seed: int = 20260909,
                      iters: int = 10000) -> tuple[float, float]:
    """Percentile CI resampling whole emails, pooling claims within a resample.

    Resampling emails (not claims) respects the nesting of claims within emails.
    Still collapses to [0, 0] when no cluster contains an event, which is exactly
    why it is reported alongside, not instead of, the exact bounds.
    """
    if not per_cluster:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    arr = np.array(per_cluster, dtype=float)
    idx = rng.integers(0, len(arr), size=(iters, len(arr)))
    sev = arr[:, 0][idx].sum(axis=1)
    tot = arr[:, 1][idx].sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        rates = np.where(tot > 0, sev / tot, np.nan)
    return tuple(float(v) for v in np.nanpercentile(rates, [2.5, 97.5]))


def kappa_with_ci(a: list[str], b: list[str]) -> tuple[float, float, float, float, float]:
    """Cohen's kappa plus a Wald interval, and raw agreement."""
    labels = sorted(set(a) | set(b))
    pos = {lab: i for i, lab in enumerate(labels)}
    table = np.zeros((len(labels), len(labels)))
    for x, y in zip(a, b):
        table[pos[x], pos[y]] += 1
    res = cohens_kappa(table)
    raw = float(np.mean([x == y for x, y in zip(a, b)]))
    return (float(res.kappa), float(res.std_kappa),
            float(res.kappa - 1.96 * res.std_kappa),
            float(res.kappa + 1.96 * res.std_kappa), raw)


def landis_koch(k: float) -> str:
    for bound, name in ((0.0, "poor"), (0.21, "slight"), (0.41, "fair"),
                        (0.61, "moderate"), (0.81, "substantial")):
        if k < bound:
            return name
    return "almost perfect"


@dataclass
class Corpus:
    blinding: dict[str, dict[str, str]]
    machine: dict[str, str]
    judge2: dict[str, str]
    human: dict[str, str]
    runs: dict[str, dict]

    @classmethod
    def load(cls, repo: Path) -> "Corpus":
        ann = repo / "annotations"
        return cls(
            blinding={r["claim_id"]: r for r in read_csv(ann / "blinding_map.csv")},
            machine={r["claim_id"]: r["final_label"]
                     for r in read_csv(ann / "machine_labels.csv")},
            judge2={r["claim_id"]: r["final_label"]
                    for r in read_csv(ann / "machine_labels_judge2.csv")},
            human={r["claim_id"]: r["final_label"]
                   for r in read_csv(ann / "human_labels.csv")},
            runs={r["run_id"]: r for r in
                  (json.loads(line) for line in
                   open(repo / "outputs" / "full.jsonl", encoding="utf-8"))},
        )

    def final_words(self, run_id: str) -> int:
        run = self.runs[run_id]
        text = (run["verified_email"]
                if run.get("verification_applied") and run.get("verified_email")
                else run["original_email"])
        return len((text or "").split())

    def by_condition(self, labels: dict[str, str]) -> dict[str, dict[str, list[str]]]:
        out: dict[str, dict[str, list[str]]] = {c: collections.defaultdict(list)
                                                for c in CONDITIONS}
        for claim_id, label in labels.items():
            meta = self.blinding[claim_id]
            out[meta["condition"]][meta["run_id"]].append(label)
        return out

    def verifier_actions(self, condition: str) -> list[str]:
        acts = []
        for run in self.runs.values():
            if run["condition"] != condition:
                continue
            for edit in run.get("verifier_edits") or []:
                acts.append(edit if isinstance(edit, str)
                            else (edit.get("action") or edit.get("edit_type")))
        return [a for a in acts if a]


def table3(c: Corpus) -> list[dict]:
    rows = []
    for cond, emails in c.by_condition(c.machine).items():
        labels = [lab for v in emails.values() for lab in v]
        factual = [lab for lab in labels if lab not in NON_FACTUAL]
        severe = sum(1 for lab in factual if lab in SEVERE)
        # Emails carrying at least one factual claim: the true email-level denominator.
        judged = {rid: v for rid, v in emails.items()
                  if any(lab not in NON_FACTUAL for lab in v)}
        email_sev = sum(1 for v in judged.values() if any(lab in SEVERE for lab in v))
        cp_lo, cp_hi = clopper_pearson(severe, len(factual))
        boot = cluster_bootstrap([
            (sum(1 for lab in v if lab in SEVERE), len([lab for lab in v if lab not in NON_FACTUAL]))
            for v in judged.values()])
        e_lo, e_hi = clopper_pearson(email_sev, len(judged))
        words = sum(c.final_words(rid) for rid in emails)
        rows.append({
            "condition": cond,
            "n_emails_generated": len(emails),
            "n_emails_with_factual_claim": len(judged),
            "n_factual_claims": len(factual),
            "n_severe": severe,
            "ser": round(severe / len(factual), 4),
            "ser_ci_low_exact": round(cp_lo, 4),
            "ser_ci_high_exact": round(cp_hi, 4),
            "ser_ci_low_clusterboot": round(boot[0], 4),
            "ser_ci_high_clusterboot": round(boot[1], 4),
            "spd": round(100 * sum(1 for lab in labels if lab == "supported") / words, 4),
            "email_level_severe": f"{email_sev}/{len(judged)}",
            "email_level_rate": round(email_sev / len(judged), 4),
            "email_level_ci_low": round(e_lo, 4),
            "email_level_ci_high": round(e_hi, 4),
        })
    return rows


def table_second_evaluator(c: Corpus) -> list[dict]:
    """Per-condition SER under each automatic evaluator, side by side.

    The primary evaluator observes zero severe errors in B and D. Whether that
    zero is a property of the emails or of the judge is answerable only by
    running a second judge over the same claims, so both are reported.
    """
    rows = []
    for name, labels in (("primary_claude-3-haiku", c.machine),
                         ("second_gemini-2.5-flash-lite", c.judge2)):
        for cond, emails in c.by_condition(labels).items():
            flat = [lab for v in emails.values() for lab in v]
            factual = [lab for lab in flat if lab not in NON_FACTUAL]
            severe = sum(1 for lab in factual if lab in SEVERE)
            lo, hi = clopper_pearson(severe, len(factual))
            rows.append({
                "evaluator": name, "condition": cond,
                "n_factual_claims": len(factual), "n_severe": severe,
                "ser": round(severe / len(factual), 4),
                "ci_low": round(lo, 4), "ci_high": round(hi, 4),
            })
    return rows


def table4(c: Corpus) -> tuple[list[dict], dict]:
    keys = sorted(c.human)
    labels = sorted(set(c.human[k] for k in keys) | set(c.machine[k] for k in keys))
    counts = collections.Counter((c.human[k], c.machine[k]) for k in keys)
    rows = []
    for h in labels:
        row = {"human_label": h}
        row.update({f"machine_{m}": counts.get((h, m), 0) for m in labels})
        row["total"] = sum(counts.get((h, m), 0) for m in labels)
        rows.append(row)

    def severe_side(label: str) -> bool:
        return label in SEVERE or label in ("overstated", "subjective_or_generic")

    agree = lenient = strict = orthogonal = 0
    for k in keys:
        h, m = c.human[k], c.machine[k]
        if h == m:
            agree += 1
        elif severe_side(h) and not severe_side(m):
            lenient += 1
        elif severe_side(m) and not severe_side(h):
            strict += 1
        else:
            orthogonal += 1
    # How the judge loses severe claims: by moving them out of the denominator.
    dropped = sum(counts.get((h, "outside_evidence_scope"), 0) for h in SEVERE)
    generic_as_supported = counts.get(("subjective_or_generic", "supported"), 0)
    machine_supported = [k for k in keys if c.machine[k] == "supported"]
    prec = sum(1 for k in machine_supported if c.human[k] == "supported") / len(machine_supported)
    p_lo, p_hi = stats.beta.ppf(
        [0.025, 0.975],
        sum(1 for k in machine_supported if c.human[k] == "supported") + 0.5,
        len(machine_supported) - sum(1 for k in machine_supported if c.human[k] == "supported") + 0.5)
    diag = {
        "n": len(keys), "agree": agree, "machine_too_lenient": lenient,
        "machine_too_strict": strict, "orthogonal": orthogonal,
        "severe_moved_to_outside_scope": dropped,
        "generic_labelled_supported": generic_as_supported,
        "supported_precision": round(prec, 4),
        "supported_precision_ci": (round(float(p_lo), 4), round(float(p_hi), 4)),
        "overstated_ever_emitted_primary": "overstated" in set(c.machine.values()),
        "overstated_ever_emitted_judge2": "overstated" in set(c.judge2.values()),
        "overstated_used_by_human": sum(1 for k in keys if c.human[k] == "overstated"),
    }
    return rows, diag


def table5(c: Corpus) -> list[dict]:
    rows = []
    per = collections.defaultdict(lambda: {"claims": 0, "factual": 0, "severe": 0,
                                           "emails": set()})
    for claim_id, label in c.human.items():
        meta = c.blinding[claim_id]
        bucket = per[meta["condition"]]
        bucket["claims"] += 1
        bucket["emails"].add(meta["run_id"])
        if label not in NON_FACTUAL:
            bucket["factual"] += 1
            if label in SEVERE:
                bucket["severe"] += 1
    for cond in CONDITIONS:
        b = per[cond]
        lo, hi = clopper_pearson(b["severe"], b["factual"])
        rows.append({
            "condition": cond,
            "human_claims": b["claims"],
            "human_factual_claims": b["factual"],
            "human_severe": b["severe"],
            "human_emails": len(b["emails"]),
            "human_ser": round(b["severe"] / b["factual"], 4) if b["factual"] else None,
            "human_ser_ci_low": round(lo, 4),
            "human_ser_ci_high": round(hi, 4),
        })
    return rows


def table6(c: Corpus) -> tuple[list[dict], list[dict]]:
    by_field = collections.defaultdict(lambda: collections.defaultdict(list))
    by_prof = collections.defaultdict(list)
    for claim_id, label in c.machine.items():
        meta = c.blinding[claim_id]
        field = FIELD_OF[meta["professor_id"].split("-")[0]]
        by_field[field][meta["condition"]].append(label)
        if meta["condition"] == "A":
            by_prof[meta["professor_id"]].append(label)

    field_rows = []
    for field, conds in sorted(by_field.items()):
        row = {"field": field}
        for cond in CONDITIONS:
            factual = [lab for lab in conds[cond] if lab not in NON_FACTUAL]
            severe = sum(1 for lab in factual if lab in SEVERE)
            row[f"{cond}_severe"] = severe
            row[f"{cond}_factual"] = len(factual)
            row[f"{cond}_ser"] = round(severe / len(factual), 4) if factual else None
        field_rows.append(row)

    prof_rows = []
    for prof, labels in sorted(by_prof.items()):
        factual = [lab for lab in labels if lab not in NON_FACTUAL]
        severe = sum(1 for lab in factual if lab in SEVERE)
        prof_rows.append({
            "professor_id": prof, "condition": "A",
            "factual_claims": len(factual), "severe": severe,
            "ser": round(severe / len(factual), 4) if factual else None,
        })

    # Leave-one-field-out sensitivity for the headline closed-book rate. Snapshot the
    # per-professor rows first: appending to prof_rows while filtering it would fold
    # each synthetic row into the next iteration's denominator.
    real_profs = list(prof_rows)
    for drop_prefix, drop_name in (("PSY", "psychology"), ("CS", "computer science"),
                                   ("BIO", "biomedicine")):
        kept = [r for r in real_profs if not r["professor_id"].startswith(drop_prefix)]
        n = sum(r["factual_claims"] for r in kept)
        s = sum(r["severe"] for r in kept)
        lo, hi = clopper_pearson(s, n)
        prof_rows.append({
            "professor_id": f"[A excluding {drop_name}]", "condition": "A",
            "factual_claims": n, "severe": s, "ser": round(s / n, 4),
            "ci_low": round(lo, 4), "ci_high": round(hi, 4),
        })
    return field_rows, prof_rows


def reliability(c: Corpus) -> list[dict]:
    hk = sorted(c.human)
    both = sorted(set(c.machine) & set(c.judge2))
    pairs = [
        ("primary (claude-3-haiku) vs human", [c.machine[k] for k in hk], [c.human[k] for k in hk]),
        ("primary vs second evaluator (gemini-2.5-flash-lite)",
         [c.machine[k] for k in both], [c.judge2[k] for k in both]),
        ("second evaluator vs human", [c.judge2[k] for k in hk], [c.human[k] for k in hk]),
    ]
    rows = []
    for name, a, b in pairs:
        k, se, lo, hi, raw = kappa_with_ci(a, b)
        rows.append({
            "comparison": name, "n_claims": len(a),
            "raw_agreement": round(raw, 4), "cohens_kappa": round(k, 4),
            "kappa_se": round(se, 4), "kappa_ci_low": round(lo, 4),
            "kappa_ci_high": round(hi, 4), "landis_koch": landis_koch(k),
        })
    return rows


def verifier_rows(c: Corpus) -> tuple[list[dict], float]:
    rows = []
    counts = {}
    for cond in ("C", "D"):
        acts = c.verifier_actions(cond)
        tally = collections.Counter(acts)
        n = len(acts)
        deletes = tally.get("delete", 0)
        rewrites = tally.get("rewrite", 0) + tally.get("soften", 0)
        lo, hi = clopper_pearson(deletes, n)
        counts[cond] = (deletes, n)
        rows.append({
            "condition": cond, "n_edit_decisions": n,
            "delete": deletes, "soften_or_rewrite": rewrites, "keep": tally.get("keep", 0),
            "deletion_rate": round(deletes / n, 4) if n else None,
            "deletion_ci_low": round(lo, 4), "deletion_ci_high": round(hi, 4),
            "rewrite_rate": round(rewrites / n, 4) if n else None,
        })
    (dc, nc), (dd, nd) = counts["C"], counts["D"]
    p = float(stats.fisher_exact([[dc, nc - dc], [dd, nd - dd]])[1])
    return rows, p


def run_metadata(c: Corpus) -> list[dict]:
    """De-identified per-run metadata, sufficient to reproduce every statistic.

    `outputs/full.jsonl` cannot be released: condition-A emails address real
    professors by surname and contain fabricated claims about them. Everything the
    analysis actually needs from it is the final word count (the SPD denominator)
    and the verifier's edit actions, neither of which identifies anyone. Exporting
    them lets a third party recompute the tables from public files alone.
    """
    rows = []
    for run_id, run in sorted(c.runs.items()):
        actions = [a if isinstance(a, str) else (a.get("action") or a.get("edit_type"))
                   for a in (run.get("verifier_edits") or [])]
        rows.append({
            "run_id": run_id,
            "professor_id": run["professor_id"],
            "condition": run["condition"],
            "seed": run["seed"],
            "writer_received_evidence": run.get("writer_received_evidence"),
            "verification_applied": run.get("verification_applied"),
            "final_word_count": c.final_words(run_id),
            "verifier_actions": ";".join(a for a in actions if a),
        })
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list({k: None for r in rows for k in r})
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=REPO / "analysis" / "revision")
    args = ap.parse_args()

    c = Corpus.load(REPO)
    t3 = table3(c)
    t_eval = table_second_evaluator(c)
    t4, diag = table4(c)
    t5 = table5(c)
    t6_field, t6_prof = table6(c)
    rel = reliability(c)
    ver, fisher_p = verifier_rows(c)

    out = args.out
    write_csv(out / "table3_primary.csv", t3)
    write_csv(out / "table3b_both_evaluators.csv", t_eval)
    write_csv(out / "table4_confusion.csv", t4)
    write_csv(out / "table5_human_coverage.csv", t5)
    write_csv(out / "table6_field.csv", t6_field)
    write_csv(out / "table6_professor.csv", t6_prof)
    write_csv(out / "reliability.csv", rel)
    write_csv(out / "verifier_edits.csv", ver)
    write_csv(out / "run_metadata.csv", run_metadata(c))

    lines: list[str] = ["# Revision statistics — NSRI-J-2026-0178", ""]
    lines += ["All figures regenerated from `annotations/` and `outputs/full.jsonl`.",
              "Exact intervals are Clopper-Pearson; the cluster bootstrap resamples",
              "whole emails. Zero-event conditions have no informative bootstrap",
              "interval, which is why exact bounds are the primary report.", ""]

    lines += ["## Table 3 — per-condition (automatic pilot labels)", ""]
    lines += ["| Cond | emails | emails w/ >=1 factual claim | factual claims | severe | SER | 95% CI (exact) | SPD | emails w/ >=1 severe | 95% CI |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for r in t3:
        lines.append(
            f"| {r['condition']} | {r['n_emails_generated']} | {r['n_emails_with_factual_claim']} | "
            f"{r['n_factual_claims']} | {r['n_severe']} | {r['ser']:.3f} | "
            f"{r['ser_ci_low_exact']:.3f}–{r['ser_ci_high_exact']:.3f} | {r['spd']:.2f} | "
            f"{r['email_level_severe']} ({r['email_level_rate']:.3f}) | "
            f"{r['email_level_ci_low']:.3f}–{r['email_level_ci_high']:.3f} |")

    lines += ["", "## Per-condition SER under each automatic evaluator", ""]
    lines += ["| Evaluator | Cond | factual claims | severe | SER | 95% CI |",
              "|---|---|---|---|---|---|"]
    for r in t_eval:
        lines.append(f"| {r['evaluator']} | {r['condition']} | {r['n_factual_claims']} | "
                     f"{r['n_severe']} | {r['ser']:.3f} | "
                     f"{r['ci_low']:.3f}–{r['ci_high']:.3f} |")
    prim = {r["condition"]: r for r in t_eval if r["evaluator"].startswith("primary")}
    sec = {r["condition"]: r for r in t_eval if r["evaluator"].startswith("second")}
    lines += ["",
              f"- worst condition under both evaluators: "
              f"{max(prim, key=lambda k: prim[k]['ser'])} / "
              f"{max(sec, key=lambda k: sec[k]['ser'])}",
              f"- B < C (the study's key comparison) under primary: "
              f"{prim['B']['ser'] < prim['C']['ser']}; under second: "
              f"{sec['B']['ser'] < sec['C']['ser']}",
              f"- second evaluator also finds zero in B and D: "
              f"{sec['B']['n_severe'] == 0 and sec['D']['n_severe'] == 0}"]

    lines += ["", "## Reliability", ""]
    lines += ["| Comparison | n | raw agreement | kappa | 95% CI | Landis-Koch |",
              "|---|---|---|---|---|---|"]
    for r in rel:
        lines.append(f"| {r['comparison']} | {r['n_claims']} | {r['raw_agreement']:.3f} | "
                     f"{r['cohens_kappa']:.3f} | {r['kappa_ci_low']:.3f}–{r['kappa_ci_high']:.3f} | "
                     f"{r['landis_koch']} |")

    lines += ["", "## Direction of human/machine disagreement", ""]
    lines += [f"- claims compared: {diag['n']}",
              f"- agree: {diag['agree']}",
              f"- machine too lenient: {diag['machine_too_lenient']}",
              f"- machine too strict: {diag['machine_too_strict']}",
              f"- orthogonal (both non-severe, different label): {diag['orthogonal']}",
              f"- severe claims the judge moved into 'outside evidence scope' "
              f"(i.e. out of the SER denominator): {diag['severe_moved_to_outside_scope']}",
              f"- human 'subjective/generic' claims the judge called 'supported' "
              f"(inflates SPD): {diag['generic_labelled_supported']}",
              f"- precision of machine 'supported' against human: "
              f"{diag['supported_precision']:.3f} "
              f"(95% CI {diag['supported_precision_ci'][0]:.3f}–{diag['supported_precision_ci'][1]:.3f})",
              f"- 'overstated' ever emitted by primary evaluator: "
              f"{diag['overstated_ever_emitted_primary']}",
              f"- 'overstated' ever emitted by second evaluator: "
              f"{diag['overstated_ever_emitted_judge2']}",
              f"- 'overstated' used by human annotator: {diag['overstated_used_by_human']} claims"]

    lines += ["", "## Human-subset coverage per condition", ""]
    lines += ["| Cond | human claims | factual | severe | emails | human SER | 95% CI |",
              "|---|---|---|---|---|---|---|"]
    for r in t5:
        ser = "n/a" if r["human_ser"] is None else f"{r['human_ser']:.3f}"
        lines.append(f"| {r['condition']} | {r['human_claims']} | {r['human_factual_claims']} | "
                     f"{r['human_severe']} | {r['human_emails']} | {ser} | "
                     f"{r['human_ser_ci_low']:.3f}–{r['human_ser_ci_high']:.3f} |")

    lines += ["", "## Field heterogeneity", ""]
    lines += ["| Field | A | B | C | D |", "|---|---|---|---|---|"]
    for r in t6_field:
        cells = " | ".join(
            f"{r[f'{c_}_severe']}/{r[f'{c_}_factual']} = "
            f"{(r[f'{c_}_ser'] if r[f'{c_}_ser'] is not None else 0):.2f}"
            for c_ in CONDITIONS)
        lines.append(f"| {r['field']} | {cells} |")
    lines += ["", "Leave-one-field-out for condition A:"]
    for r in t6_prof:
        if r["professor_id"].startswith("["):
            lines.append(f"- {r['professor_id']}: {r['severe']}/{r['factual_claims']} = "
                         f"{r['ser']:.3f} (95% CI {r['ci_low']:.3f}–{r['ci_high']:.3f})")

    lines += ["", "## Verifier edit behaviour", ""]
    lines += ["| Cond | decisions | delete | soften/rewrite | keep | deletion rate | 95% CI |",
              "|---|---|---|---|---|---|---|"]
    for r in ver:
        lines.append(f"| {r['condition']} | {r['n_edit_decisions']} | {r['delete']} | "
                     f"{r['soften_or_rewrite']} | {r['keep']} | {r['deletion_rate']:.3f} | "
                     f"{r['deletion_ci_low']:.3f}–{r['deletion_ci_high']:.3f} |")
    lines += ["", f"Fisher exact test, C vs D deletion rate: p = {fisher_p:.4f}"]

    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[written] {out}")


if __name__ == "__main__":
    main()
