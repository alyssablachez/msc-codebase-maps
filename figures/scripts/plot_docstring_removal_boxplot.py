"""
Figure: map size (estimated tokens, chars // 4) with vs. without docstrings.

Box-and-whisker, two boxes, paired 45 issues from repo_maps/compact_nodoc_stats.csv
(compact_tokens = with docstrings, nodoc_tokens = without). Outliers beyond
the whiskers are shown via matplotlib's default fliers; no jittered points.

Writes figures/docstring_removal_boxplot.png.
"""
import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "repo_maps", "compact_nodoc_stats.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "docstring_removal_boxplot.png")

COLOR_WITH = "#eb6834"     # slot 2, orange
COLOR_WITHOUT = "#2a78d6"  # slot 1, blue


def main():
    df = pd.read_csv(DATA_CSV)
    data = [df["compact_tokens"].values, df["nodoc_tokens"].values]
    labels = ["with docstrings", "without docstrings"]
    colors = [COLOR_WITH, COLOR_WITHOUT]

    fig, ax = plt.subplots(figsize=(7, 6.5))

    bp = ax.boxplot(
        data, positions=[0, 1], widths=0.45, patch_artist=True,
        medianprops=dict(color="#0b0b0b", linewidth=1.6),
        whiskerprops=dict(color="#52514e"),
        capprops=dict(color="#52514e"),
        flierprops=dict(marker="o", markersize=5, markerfacecolor="none",
                        markeredgecolor="#52514e", linestyle="none"),
        zorder=3,
    )
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.25)
        patch.set_edgecolor(color)

    ax.set_yscale("log")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(labels)
    ax.set_ylabel("Estimated token count (log scale)")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300)
    print(f"Saved: {OUT_PNG}")

    med_with = df["compact_tokens"].median()
    med_without = df["nodoc_tokens"].median()
    print(f"Median with docstrings:    {med_with:,.0f}")
    print(f"Median without docstrings: {med_without:,.0f}")
    print(f"Median reduction:          {(1 - med_without / med_with) * 100:.1f}%")


if __name__ == "__main__":
    main()
