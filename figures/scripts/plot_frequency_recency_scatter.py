"""
Scatter of the frequency map's two dimensions for the ground-truth file
in every issue: pct_through_files (rank by edit COUNT, descending -- the
order the model actually sees, normalized to % through that issue's own
map) vs. pct_through_dates (rank if the same file list were re-sorted by
most-recent-edit instead). Percentage rather than raw rank so issues
with very different map sizes (41 to 1281 files) sit on a common scale.
A diagonal y=x reference line marks perfect agreement; points above it
are ranked worse (later) by recency than by count, points below better.

Source: data/map_position_metrics.csv's frequency rows (see
scripts/add_frequency_date_rank.py for how the date columns were added).

Usage:
    python3 figures/scripts/plot_frequency_recency_scatter.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "data", "map_position_metrics.csv")
FIG_DIR = os.path.join(_ROOT, "figures")

POINT_COLOR = "#2a78d6"
LINE_COLOR = "#8a8980"


def main():
    df = pd.read_csv(DATA_CSV)
    freq = df[df["map_type"] == "frequency"].dropna(subset=["pct_through_dates", "pct_through_files"])

    fig, ax = plt.subplots(figsize=(7.5, 7))
    ax.plot([0, 100], [0, 100], color=LINE_COLOR, linewidth=1.2, linestyle="--", zorder=1)
    ax.axvline(50, color="#c0392b", linewidth=1.2, linestyle=":", zorder=2)
    ax.axhline(50, color="#c0392b", linewidth=1.2, linestyle=":", zorder=2)
    ax.scatter(freq["pct_through_files"], freq["pct_through_dates"], s=48, color=POINT_COLOR,
              alpha=0.6, edgecolors="none", zorder=3)

    ax.set_xlim(-2, 102)
    ax.set_ylim(-2, 102)
    ax.set_xlabel("Rank by edit count (% through the map, as shown to the model)", fontsize=11)
    ax.set_ylabel("Rank by recency (% through, if re-sorted by last-edit date)", fontsize=11)
    ax.set_aspect("equal")
    ax.tick_params(axis="both", labelsize=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    fig.tight_layout()
    out = os.path.join(FIG_DIR, "frequency_recency_scatter.png")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
