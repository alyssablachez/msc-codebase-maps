"""
Figure: current (June 2026 clone) package LoC vs. median per-task package
LoC, same axis, one row per repo -- ALL 17 repos ever in the panel, not just
the final 15. Dark dot = current size, light dot (same hue) = median task
size, connected by a horizontal line. Colour = final-panel tier
(small/medium/large); repos removed from the panel (Deep-Live-Cam,
open-interpreter) are gray since they have no final tier.

Reads figures/data/repo_current_vs_task_median_loc.csv
(compute_repo_current_vs_task_median_loc.py).
Writes figures/repo_current_vs_task_median_loc.png.
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "figures", "data", "repo_current_vs_task_median_loc.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "repo_current_vs_task_median_loc.png")

TIER_COLOR = {
    "small":   "#1baf7a",  # slot 3, aqua
    "medium":  "#eb6834",  # slot 2, orange
    "large":   "#2a78d6",  # slot 1, blue
    "removed": "#8a8a85",  # gray
}
TIER_LABEL = {"small": "small", "medium": "medium", "large": "large", "removed": "removed from panel"}
DARK_ALPHA = 1.0   # current
LIGHT_ALPHA = 0.4  # median task

# Original (pre-2026-07-12-audit) tier, for the two removed repos only --
# confirmed against ORIG_TIER in compute_panel_loc.py / DEVLOG 2026-07-09.
ORIGINAL_TIER = {"Deep-Live-Cam": "small", "open-interpreter": "medium"}
ADDED_REPOS = {"core", "transformers"}


def main():
    df = pd.read_csv(DATA_CSV)
    df = df.sort_values("current_loc")

    fig, ax = plt.subplots(figsize=(9, 8))
    y_positions = range(len(df))

    for y, (_, row) in zip(y_positions, df.iterrows()):
        color = TIER_COLOR[row["tier"]]
        ax.plot([row["median_task_loc"], row["current_loc"]], [y, y],
                color=color, alpha=0.5, linewidth=1.4, zorder=1)
        ax.scatter(row["median_task_loc"], y, s=75, color=color, alpha=LIGHT_ALPHA,
                   zorder=3, edgecolors="none")
        ax.scatter(row["current_loc"], y, s=75, color=color, alpha=DARK_ALPHA,
                   zorder=3, edgecolors="white", linewidths=0.6)

        if row["repo"] in ORIGINAL_TIER:
            ax.annotate(f"originally {ORIGINAL_TIER[row['repo']]}",
                        xy=(row["current_loc"], y), xytext=(10, 0),
                        textcoords="offset points", ha="left", va="center",
                        fontsize=8.5, color="#52514e", style="italic")
        if row["repo"] in ADDED_REPOS:
            ax.annotate("added", xy=(row["median_task_loc"], y), xytext=(-10, 0),
                        textcoords="offset points", ha="right", va="center",
                        fontsize=8.5, color="#52514e", style="italic")

    ax.set_xscale("log")
    ax.set_yticks(list(y_positions))
    ax.set_yticklabels(df["repo"])
    ax.set_xlabel("Python package LoC (log scale)")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")
    ax.tick_params(axis="y", length=0)

    # Two legends: light/dark meaning (series) and tier colour (identity) --
    # kept separate since they encode different things.
    shade_handles = [
        plt.Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                   markerfacecolor="#52514e", alpha=DARK_ALPHA, markeredgecolor="white",
                   label="current (June 2026)"),
        plt.Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                   markerfacecolor="#52514e", alpha=LIGHT_ALPHA,
                   label="median per-task"),
    ]
    shade_legend = ax.legend(handles=shade_handles, frameon=False, title="series",
                              loc="upper right", bbox_to_anchor=(0.46, -0.08), ncol=1)
    ax.add_artist(shade_legend)

    tier_handles = [
        plt.Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                   markerfacecolor=TIER_COLOR[t], markeredgecolor="none", label=TIER_LABEL[t])
        for t in ["small", "medium", "large", "removed"]
    ]
    ax.legend(handles=tier_handles, frameon=False, title="final size category",
              loc="upper left", bbox_to_anchor=(0.54, -0.08), ncol=1)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
