"""
Study 1 (map-as-context vs. baseline) -- pooled F1 violin plot by map
condition, all 4 models x 45 issues x 3 reps (rep<=3, primary sample only)
pooled into each violin. Same colour convention as the Study 0
map-comparison violinplots (figures/scripts/plot_study0_map_f1_boxplot.py) --
"baseline" (no map) is neutral grey, the three map conditions get distinct
hues (slots 1-3 of the dataviz skill's reference categorical palette).
Median/mean drawn manually (solid line / diamond marker) rather than using
violinplot's built-in showmedians/showmeans, so the visual language matches
every other violinplot in this project exactly rather than introducing a
second convention just for violins.

Note on shape: F1 is a discrete, bounded score (few possible values given
small per-task ground-truth-file counts) -- same caveat as the violinplot
version. A violin's kernel density estimate will render this discreteness
as a smoothed continuous shape (bulges at the recurring exact values like
0, .5, .67, .8, 1.0 rather than the sharp point-masses a violinplot's flat box
edges made obvious) -- read the bulge locations as "common exact F1
values," not as evidence of a smooth continuous distribution underneath.

This is purely descriptive -- matches the Friedman/Wilcoxon results
already computed in scripts/stats_study1_f1.py and the R GLMM fit in
scripts/stats_study1_r_glmm.R.

Reads data/compiled_results_combined.pkl directly.
Writes figures/study1_f1_violinplot.png.

Usage:
    python3 figures/scripts/plot_study1_f1_violinplot.py
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_PNG = os.path.join(_ROOT, "figures", "study1_f1_violinplot.png")

MAP_ORDER = ["baseline", "structural", "temporal_frequency", "temporal_cochange"]
MAP_LABELS = {"baseline": "no map", "structural": "structural",
             "temporal_frequency": "frequency", "temporal_cochange": "co-change"}
MAP_COLOR = {"baseline": "#8a8980", "structural": "#2a78d6",
            "temporal_frequency": "#eb6834", "temporal_cochange": "#1baf7a"}


def load_study1():
    df = pd.read_pickle(DATA_PKL)
    return df[(df["study"] == 1) & (df["rep"] <= 3)].copy()


def main():
    df = load_study1()

    data = [df.loc[df["map_condition"] == m, "f1"].dropna().values for m in MAP_ORDER]
    positions = list(range(len(MAP_ORDER)))

    fig, ax = plt.subplots(figsize=(7, 6.5))

    parts = ax.violinplot(data, positions=positions, widths=0.65,
                          showmeans=False, showmedians=False, showextrema=False)
    for body, m in zip(parts["bodies"], MAP_ORDER):
        body.set_facecolor(MAP_COLOR[m])
        body.set_edgecolor(MAP_COLOR[m])
        body.set_alpha(0.85)
        body.set_zorder(3)

    for pos, d in zip(positions, data):
        median, mean = np.median(d), np.mean(d)
        ax.hlines(median, pos - 0.22, pos + 0.22, color="#0b0b0b", linewidth=1.6, zorder=5)
        ax.scatter([pos], [mean], marker="D", s=36, facecolor="white",
                  edgecolor="#0b0b0b", linewidths=1.3, zorder=6)

    ax.set_xticks(positions)
    ax.set_xticklabels([MAP_LABELS[m] for m in MAP_ORDER], fontsize=10.5)
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
    ax.legend(handles=stat_handles, loc="upper left", fontsize=10, frameon=True,
             framealpha=0.9, edgecolor="none")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
