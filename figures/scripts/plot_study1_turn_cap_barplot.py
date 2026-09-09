"""
Study 1 -- % of trials hitting the turn cap, by map condition, pooled
across all 4 models x 45 issues x 3 reps (rep<=3, primary sample only).
Same colour convention as the other Study 1 charts.

Reads data/compiled_results_combined.pkl directly.
Writes figures/study1_turn_cap_barplot.png.

Usage:
    python3 figures/scripts/plot_study1_turn_cap_barplot.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_PNG = os.path.join(_ROOT, "figures", "study1_turn_cap_barplot.png")

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

    heights = [df.loc[df["map_condition"] == m, "hit_turn_cap"].mean() * 100 for m in MAP_ORDER]
    positions = list(range(len(MAP_ORDER)))
    colors = [MAP_COLOR[m] for m in MAP_ORDER]

    fig, ax = plt.subplots(figsize=(7, 6.5))

    ax.bar(positions, heights, width=0.6, color=colors, zorder=3)
    for x, h in zip(positions, heights):
        ax.text(x, h + max(heights) * 0.02, f"{h:.0f}%", ha="center", va="bottom",
                fontsize=10.5, color="#52514e")

    ax.set_xticks(positions)
    ax.set_xticklabels([MAP_LABELS[m] for m in MAP_ORDER], fontsize=10.5)
    ax.set_xlabel("Map condition", fontsize=12)
    ax.set_ylabel("Trials hitting the turn cap (%)", fontsize=12)
    ax.set_ylim(0, max(heights) * 1.15)
    ax.tick_params(axis="y", labelsize=10.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
