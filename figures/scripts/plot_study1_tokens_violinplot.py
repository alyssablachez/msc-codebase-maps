"""
Study 1 -- pooled input-tokens violin plot by map condition, same
convention as plot_study1_f1_violinplot.py. Input tokens (not output) is the
token metric of interest here, matching the Study 0 map-comparison
convention (figures/scripts/plot_study0_map_input_tokens_boxplot.py) --
map content is injected into the prompt, so it shows up as input tokens.

Reads data/compiled_results_combined.pkl directly.
Writes figures/study1_tokens_violinplot.png.

Usage:
    python3 figures/scripts/plot_study1_tokens_violinplot.py
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_PNG = os.path.join(_ROOT, "figures", "study1_tokens_violinplot.png")

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

    data = [df.loc[df["map_condition"] == m, "total_input_tokens"].dropna().values / 1e6 for m in MAP_ORDER]
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
    ax.set_ylabel("Input tokens per trial (millions)", fontsize=12)
    ax.set_ylim(bottom=0)
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
