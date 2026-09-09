"""Regenerate manuscript figures with honest intervals for the NSRI revision.

Figure 1 previously drew zero-height error bars on conditions B and D, because the
percentile bootstrap collapses when a condition contains no severe errors. Drawn
that way the chart asserts a measured zero. Here the zero-event conditions carry
their exact (Clopper-Pearson) upper bounds and are hatched to mark them as
upper bounds rather than point estimates.

Figure 3 is new: it shows that the closed-book severe-error rate is concentrated
in one of the three sampled fields, which the pooled rate hides.

Run:
    python scripts/make_revision_figures.py
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
BLUE, GREY, RED = "#4C72B0", "#8C8C8C", "#C44E52"
LABELS = {"A": "A\nclosed-book", "B": "B\ngrounded",
          "C": "C\nverify-only", "D": "D\ngrounded+verified"}


def read(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def figure1(rows: list[dict[str, str]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    for i, r in enumerate(rows):
        ser = float(r["ser"])
        lo, hi = float(r["ser_ci_low_exact"]), float(r["ser_ci_high_exact"])
        zero = int(r["n_severe"]) == 0
        if zero:
            # No events: draw the interval as a bounded box, not a point with whiskers.
            ax.bar(i, hi, color="white", edgecolor=RED, hatch="///", linewidth=1.4, zorder=2)
            ax.annotate(f"0/{r['n_factual_claims']} claims\nupper bound {hi:.3f}",
                        (i, hi), textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=8, color=RED)
        else:
            ax.bar(i, ser, color=BLUE, zorder=2)
            ax.errorbar(i, ser, yerr=[[ser - lo], [hi - ser]], fmt="none",
                        ecolor="black", capsize=6, linewidth=1.3, zorder=3)
            ax.annotate(f"{r['n_severe']}/{r['n_factual_claims']} claims\n{ser:.3f}",
                        (i, hi), textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=8)
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels([LABELS[r["condition"]] for r in rows], fontsize=9)
    ax.set_ylabel("Severe Error Rate")
    ax.set_ylim(0, 0.62)
    ax.set_title("Severe Error Rate by condition\n"
                 "exact 95% intervals; pilot estimates from automatic labels", fontsize=11)
    ax.legend(handles=[
        Patch(facecolor=BLUE, label="observed rate, exact 95% CI"),
        Patch(facecolor="white", edgecolor=RED, hatch="///",
              label="no severe errors observed: 95% upper bound only"),
    ], fontsize=8, loc="upper right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def figure2(rows: list[dict[str, str]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 5.2))
    for r in rows:
        x, y = float(r["ser"]), float(r["spd"])
        zero = int(r["n_severe"]) == 0
        ax.scatter(x, y, s=110, color=(RED if zero else BLUE),
                   marker=("s" if zero else "o"), zorder=3)
        if zero:
            # The horizontal bar shows the interval the zero point is consistent with.
            ax.plot([x, float(r["ser_ci_high_exact"])], [y, y],
                    color=RED, linewidth=1.4, alpha=0.85, zorder=2)
        else:
            ax.plot([float(r["ser_ci_low_exact"]), float(r["ser_ci_high_exact"])], [y, y],
                    color=BLUE, linewidth=1.4, alpha=0.6, zorder=2)
        # B (1.71) and D (1.76) sit almost on top of each other; nudge their
        # labels apart vertically so neither overprints the other.
        nudge = {"B": (10, -13), "D": (10, 6)}.get(r["condition"], (9, 7))
        ax.annotate(r["condition"], (x, y), textcoords="offset points",
                    xytext=nudge, fontsize=11, fontweight="bold")
    ax.set_xlabel("Severe Error Rate (lower is better)")
    ax.set_ylabel("Supported Personalization Density (higher is better)")
    ax.set_title("Supported-Specificity Frontier\n"
                 "horizontal bars are exact 95% intervals; upper-left is best", fontsize=11)
    ax.set_xlim(-0.03, 0.55)
    ax.set_ylim(0, 2.1)
    ax.legend(handles=[
        Patch(facecolor=BLUE, label="observed severe errors"),
        Patch(facecolor=RED, label="zero observed; bar = 95% upper bound"),
    ], fontsize=8, loc="lower right", frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def figure3(field_rows: list[dict[str, str]], out: Path) -> None:
    """Per-field closed-book rate: the pooled 0.34 is not a homogeneous effect."""
    order = ["psychology", "computer science", "biomedicine"]
    rows = sorted(field_rows, key=lambda r: order.index(r["field"]))
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for i, r in enumerate(rows):
        sev, tot = int(r["A_severe"]), int(r["A_factual"])
        ax.barh(i, sev / tot, color=BLUE, zorder=2)
        ax.annotate(f"{sev}/{tot} = {sev / tot:.2f}", (sev / tot, i),
                    textcoords="offset points", xytext=(6, -3), fontsize=9)
    ax.axvline(0.344, color=RED, linestyle="--", linewidth=1.5, zorder=3)
    # Offset the label clear of its own line so neither overprints the other.
    ax.annotate("pooled closed-book SER = 0.34", (0.364, 2.55), color=RED,
                fontsize=8.5, ha="left", va="center")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["field"] for r in rows])
    ax.set_xlabel("Severe Error Rate, condition A (closed-book)")
    ax.set_xlim(0, 1.02)
    ax.set_ylim(-0.6, 2.9)
    ax.set_title("Closed-book severe errors are concentrated in one field\n"
                 "81% of condition-A severe errors come from the 4 psychology professors",
                 fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stats", type=Path, default=REPO / "analysis" / "revision")
    ap.add_argument("--out", type=Path, default=REPO / "analysis" / "figures")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    primary = read(args.stats / "table3_primary.csv")
    fields = read(args.stats / "table6_field.csv")

    figure1(primary, args.out / "fig1_ser_by_condition_revised.png")
    figure2(primary, args.out / "fig2_frontier_revised.png")
    figure3(fields, args.out / "fig3_field_heterogeneity.png")
    for name in ("fig1_ser_by_condition_revised", "fig2_frontier_revised",
                 "fig3_field_heterogeneity"):
        print(f"[written] {args.out / (name + '.png')}")


if __name__ == "__main__":
    main()
