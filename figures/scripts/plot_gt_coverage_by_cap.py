"""
Figure: % of the 45 issues where at least one scorable ground-truth file is
present in the map, grouped by truncation cap (no cap / 30k / 50k / 55k),
one bar per map type (structural / frequency / co-change) within each group.

Reads figures/data/gt_coverage_by_cap.csv (compute_gt_coverage_by_cap.py).
Writes figures/gt_coverage_by_cap.png.
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "figures", "data", "gt_coverage_by_cap.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "gt_coverage_by_cap.png")

CAP_ORDER = ["30k", "50k", "55k", "no_cap"]
CAP_LABEL = {"no_cap": "no cap", "30k": "30k", "50k": "50k", "55k": "55k"}

MAP_TYPE_ORDER = ["structural", "frequency", "cochange"]
MAP_TYPE_LABEL = {"structural": "structural", "frequency": "frequency", "cochange": "co-change"}
MAP_TYPE_COLOR = {
    "structural": "#4a3aa7",  # slot 7, violet
    "frequency":  "#008300",  # slot 6, green
    "cochange":   "#e34948",  # slot 8, red
}


def main():
    df = pd.read_csv(DATA_CSV)

    fig, ax = plt.subplots(figsize=(9, 5.5))

    n_series = len(MAP_TYPE_ORDER)
    bar_width = 0.8 / n_series
    offsets = [(i - (n_series - 1) / 2) * bar_width for i in range(n_series)]

    for map_type, offset in zip(MAP_TYPE_ORDER, offsets):
        sub = df[df["map_type"] == map_type].set_index("cap").loc[CAP_ORDER]
        x = np.arange(len(CAP_ORDER)) + offset
        bars = ax.bar(
            x, sub["pct_pass"],
            width=bar_width * 0.92,
            color=MAP_TYPE_COLOR[map_type],
            label=MAP_TYPE_LABEL[map_type],
            zorder=3,
        )
        for rect, pct in zip(bars, sub["pct_pass"]):
            ax.annotate(f"{pct:.0f}%", xy=(rect.get_x() + rect.get_width() / 2, rect.get_height()),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=8, color="#52514e")

    ax.set_xticks(range(len(CAP_ORDER)))
    ax.set_xticklabels([CAP_LABEL[c] for c in CAP_ORDER])
    ax.set_xlabel("Truncation cap")
    ax.set_ylabel("Percent of tasks with at least one ground-truth file in map")
    ax.set_ylim(0, 108)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
