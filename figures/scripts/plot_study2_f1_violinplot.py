"""
Study 2 (on-demand/voluntary map tools vs. baseline) -- pooled F1 violin
plot by map condition, same convention as
figures/scripts/plot_study1_f1_violinplot.py. 5 conditions instead of
Study 1's 4 (Study 2 adds `all_tools`), colour palette extended with
slot 4 (yellow, #eda100) from the dataviz skill's reference categorical
order. `baseline` is Study 1's shared cross-study control, joined in the
same way as scripts/stats_study2_f1.py.

Reads data/compiled_results_combined.pkl directly.
Writes figures/study2_f1_violinplot.png.

Usage:
    python3 figures/scripts/plot_study2_f1_violinplot.py
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_PNG = os.path.join(_ROOT, "figures", "study2_f1_violinplot.png")

MAP_ORDER = ["baseline", "structural", "temporal_frequency", "temporal_cochange", "all_tools"]
MAP_LABELS = {"baseline": "no map\ntools", "structural": "structural",
             "temporal_frequency": "frequency", "temporal_cochange": "co-change",
             "all_tools": "all tools"}
MAP_COLOR = {"baseline": "#8a8980", "structural": "#2a78d6",
            "temporal_frequency": "#eb6834", "temporal_cochange": "#1baf7a",
            "all_tools": "#eda100"}


def load_study2():
    df = pd.read_pickle(DATA_PKL)
    return df[(df["rep"] <= 3) & ((df["study"] == 2) |
                                  ((df["study"] == 1) & (df["map_condition"] == "baseline")))].copy()


def main():
    df = load_study2()

    data = [df.loc[df["map_condition"] == m, "f1"].dropna().values for m in MAP_ORDER]
    positions = list(range(len(MAP_ORDER)))

    fig, ax = plt.subplots(figsize=(7.5, 6.5))

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
