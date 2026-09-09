"""
Study 0 mean-F1 barplot -- one bar per model, labeled with its exact mean F1.
Same pair grouping and small/large tint convention as the other study0_*
figures. Replaces the F1 boxplot/precision-recall-scatter pair for the
report text -- simpler read, same underlying number.

Reads study_0/results_all.csv directly (already collated by
scripts/collate_results.py -- no separate compute step needed here).
Writes figures/study0_f1_barplot.png.

Usage:
    python3 figures/scripts/plot_study0_f1_barplot.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "study_0", "results_all.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "study0_f1_barplot.png")

# Pair order: ranked by the PAIR's own overall mean F1 (small+large
# pooled), ascending -- not by the large model alone, unlike the other
# study0_*_boxplot scripts. Recomputed from study_0/results_all.csv -- not
# a fixed convention, re-derive if the underlying scoring data changes.
PAIR_ORDER = ["Ministral", "gpt-oss", "Nemotron-3", "GLM-4.7", "Qwen3-VL", "DeepSeek-V4"]
PAIR_COLOR = {
    "Qwen3-VL":    "#2a78d6",
    "gpt-oss":     "#eb6834",
    "Ministral":   "#1baf7a",
    "DeepSeek-V4": "#eda100",
    "Nemotron-3":  "#e87ba4",
    "GLM-4.7":     "#008300",
}
SMALL_ALPHA = 0.45
LARGE_ALPHA = 1.0

MODEL_ORDER = []
for pair in PAIR_ORDER:
    MODEL_ORDER.append((pair, "small"))
    MODEL_ORDER.append((pair, "large"))


def main():
    df = pd.read_csv(DATA_CSV)

    fig, ax = plt.subplots(figsize=(12, 6.5))

    positions = []
    heights = []
    colors = []
    alphas = []
    labels = []
    pos = 0
    bar_width = 0.75
    within_gap = 0.95
    group_gap = 1.6
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
        heights.append(sub["f1"].mean())
        colors.append(PAIR_COLOR[pair])
        alphas.append(SMALL_ALPHA if size == "small" else LARGE_ALPHA)
        labels.append(model_short)

    ax.bar(positions, heights, width=bar_width, color=colors, zorder=3)
    for patch, alpha in zip(ax.patches, alphas):
        patch.set_alpha(alpha)

    for x, h in zip(positions, heights):
        ax.text(x, h + 0.015, f"{h:.2f}", ha="center", va="bottom",
                fontsize=9.5, color="#52514e")

    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Mean F1", fontsize=12)
    ax.set_ylim(0, max(heights) * 1.15)
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
