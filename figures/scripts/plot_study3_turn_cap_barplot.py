"""
Study 3 (on-demand/required map tools vs. baseline) -- % of trials
hitting the turn cap, by map condition, same convention as
figures/scripts/plot_study1_turn_cap_barplot.py and
figures/scripts/plot_study2_turn_cap_barplot.py. `baseline` is Study 1's
shared cross-study control.

Reads data/compiled_results_combined.pkl directly.
Writes figures/study3_turn_cap_barplot.png.

Usage:
    python3 figures/scripts/plot_study3_turn_cap_barplot.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_PNG = os.path.join(_ROOT, "figures", "study3_turn_cap_barplot.png")

MAP_ORDER = ["baseline", "structural", "temporal_frequency", "temporal_cochange", "all_tools"]
MAP_LABELS = {"baseline": "no map\ntools", "structural": "structural",
             "temporal_frequency": "frequency", "temporal_cochange": "co-change",
             "all_tools": "all tools"}
MAP_COLOR = {"baseline": "#8a8980", "structural": "#2a78d6",
            "temporal_frequency": "#eb6834", "temporal_cochange": "#1baf7a",
            "all_tools": "#eda100"}


def load_study3():
    df = pd.read_pickle(DATA_PKL)
    return df[(df["rep"] <= 3) & ((df["study"] == 3) |
                                  ((df["study"] == 1) & (df["map_condition"] == "baseline")))].copy()


def main():
    df = load_study3()

    heights = [df.loc[df["map_condition"] == m, "hit_turn_cap"].mean() * 100 for m in MAP_ORDER]
    positions = list(range(len(MAP_ORDER)))
    colors = [MAP_COLOR[m] for m in MAP_ORDER]

    fig, ax = plt.subplots(figsize=(7.5, 6.5))

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
