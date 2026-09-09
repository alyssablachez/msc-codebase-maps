"""
Study 0 cost boxplot -- $ per trial (cost_usd) per model, grouped into the
6 small/large pairs the study was designed around. Each pair gets one
categorical hue; small = lighter tint (alpha), large = full colour, so a
pair reads as one family at a glance while staying distinguishable from
its neighbours.

Reads study_0/results_all.csv directly (already collated + cost-corrected
by scripts/collate_results.py -- no separate compute step needed here).
Writes figures/study0_cost_boxplot.png.

Usage:
    python3 figures/scripts/plot_study0_cost_boxplot.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "study_0", "results_all.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "study0_cost_boxplot.png")

# Pair order: ranked by the LARGE model's median cost_usd, ascending
# (recomputed from study_0/results_summary_stats.csv -- not a fixed
# convention, re-derive if the underlying cost data changes).
PAIR_ORDER = ["DeepSeek-V4", "gpt-oss", "Nemotron-3", "Ministral", "Qwen3-VL", "GLM-4.7"]
PAIR_COLOR = {
    "Qwen3-VL":    "#2a78d6",  # slot 1, blue
    "gpt-oss":     "#eb6834",  # slot 2, orange
    "Ministral":   "#1baf7a",  # slot 3, aqua
    "DeepSeek-V4": "#eda100",  # slot 4, yellow
    "Nemotron-3":  "#e87ba4",  # slot 5, magenta
    "GLM-4.7":     "#008300",  # slot 6, green
}
SMALL_ALPHA = 0.45
LARGE_ALPHA = 1.0

# Model-short labels in pair, small-then-large order.
MODEL_ORDER = []
for pair in PAIR_ORDER:
    MODEL_ORDER.append((pair, "small"))
    MODEL_ORDER.append((pair, "large"))


def main():
    df = pd.read_csv(DATA_CSV)

    fig, ax = plt.subplots(figsize=(12, 6.5))

    positions = []
    data = []
    colors = []
    alphas = []
    labels = []
    pos = 0
    box_width = 0.75
    within_gap = 0.95   # same-pair boxes: small but clear gap (> box_width)
    group_gap = 1.6      # between pairs: clearly wider than within_gap
    prev_pair = None
    for pair, size in MODEL_ORDER:
        if prev_pair is not None and pair != prev_pair:
            pos += group_gap
        elif prev_pair is not None:
            pos += within_gap
        prev_pair = pair

        sub = df[(df["pair_name"] == pair) & (df["model_size"] == size)]
        model_short = sub["model_short"].iloc[0]
        positions.append(pos)
        data.append(sub["cost_usd"].dropna().values)
        colors.append(PAIR_COLOR[pair])
        alphas.append(SMALL_ALPHA if size == "small" else LARGE_ALPHA)
        labels.append(model_short)

    bp = ax.boxplot(
        data, positions=positions, widths=box_width, patch_artist=True,
        medianprops=dict(color="#0b0b0b", linewidth=1.6),
        whiskerprops=dict(color="#52514e"),
        capprops=dict(color="#52514e"),
        flierprops=dict(marker="o", markersize=4, markerfacecolor="none",
                        markeredgecolor="#52514e", linestyle="none"),
        zorder=3,
    )
    for patch, color, alpha in zip(bp["boxes"], colors, alphas):
        patch.set_facecolor(color)
        patch.set_alpha(alpha)
        patch.set_edgecolor(color)

    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Cost per trial (USD)", fontsize=12)
    ax.tick_params(axis="y", labelsize=10.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor="#52514e", alpha=SMALL_ALPHA, label="small"),
        plt.Rectangle((0, 0), 1, 1, facecolor="#52514e", alpha=LARGE_ALPHA, label="large"),
    ]
    ax.legend(handles=handles, frameon=False, loc="upper left", fontsize=10.5, title="Model size")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
