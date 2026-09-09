"""
Study 0 Goal 3 -- pooled F1 boxplot by map condition (none / ast /
ast_compact), all 12 models x 5 tasks x 5 reps pooled into each box (n=300
per condition). This is the aggregate-level view of the Friedman/Wilcoxon
null result documented in
tables/thesis_appendix_map_comparison_{friedman,wilcoxon}.tex -- the three
distributions look near-identical, matching the non-significant omnibus
test. (A per-model mean-F1 line plot was also tried as a companion figure,
but was dropped: it didn't actually represent the by-model CSV's paired-
difference finding -- see git history if reviving that idea -- and was
visually too noisy across 12 crossing lines to be useful on its own.)

"None" (no map, the control condition) is colored neutral gray; ast and
ast_compact get distinct hues (slots 1/2 of the dataviz skill's reference
categorical palette) since they're the two treatment conditions being
compared against it and against each other.

Note on shape: F1 is a discrete, bounded score (few possible values given
small per-task ground-truth-file counts), so expect boxes with edges
landing on exact fractions (0, .5, .67, .8, 1.0) rather than smooth
quartiles -- this is real data shape, not a rendering artefact (same
pattern seen in the now-superseded per-model F1 boxplot).

Reads study_0/results_all.csv directly (already collated by
scripts/collate_results.py -- no separate compute step needed here).
Writes figures/study0_map_f1_boxplot.png.

Usage:
    python3 figures/scripts/plot_study0_map_f1_boxplot.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "study_0", "results_all.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "study0_map_f1_boxplot.png")

MAP_ORDER = ["none", "ast", "ast_compact"]
MAP_LABELS = {"none": "None", "ast": "ast", "ast_compact": "ast-compact"}
MAP_COLOR = {"none": "#8a8980", "ast": "#2a78d6", "ast_compact": "#eb6834"}


def main():
    df = pd.read_csv(DATA_CSV)
    df = df[df["map_type"].isin(MAP_ORDER)]

    data = [df.loc[df["map_type"] == m, "f1"].dropna().values for m in MAP_ORDER]
    positions = list(range(len(MAP_ORDER)))

    fig, ax = plt.subplots(figsize=(6.5, 6.5))

    bp = ax.boxplot(
        data, positions=positions, widths=0.55, patch_artist=True,
        medianprops=dict(color="#0b0b0b", linewidth=1.6),
        whiskerprops=dict(color="#52514e"),
        capprops=dict(color="#52514e"),
        flierprops=dict(marker="o", markersize=4, markerfacecolor="none",
                        markeredgecolor="#52514e", linestyle="none"),
        showmeans=True,
        meanprops=dict(marker="D", markersize=6, markerfacecolor="white",
                       markeredgecolor="#0b0b0b", markeredgewidth=1.3, zorder=5),
        zorder=3,
    )
    for patch, m in zip(bp["boxes"], MAP_ORDER):
        patch.set_facecolor(MAP_COLOR[m])
        patch.set_alpha(0.85)
        patch.set_edgecolor(MAP_COLOR[m])

    ax.set_xticks(positions)
    ax.set_xticklabels([MAP_LABELS[m] for m in MAP_ORDER], fontsize=11)
    ax.set_xlabel("Map condition", fontsize=12)
    ax.set_ylabel("F1 per trial", fontsize=12)
    ax.set_ylim(-0.05, 1.05)
    ax.tick_params(axis="y", labelsize=10.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    stat_handles = [
        plt.Line2D([0], [0], color="#0b0b0b", linewidth=1.6, label="Median"),
        plt.Line2D([0], [0], marker="D", linestyle="none", markersize=6,
                   markerfacecolor="white", markeredgecolor="#0b0b0b",
                   markeredgewidth=1.3, label="Mean"),
    ]
    ax.legend(handles=stat_handles, loc="lower right", fontsize=10, frameon=True,
             framealpha=0.9, edgecolor="none")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
