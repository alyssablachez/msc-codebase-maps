"""
Study 0 wall-time boxplot -- seconds per trial (wall_time) per model, grouped
into the 6 small/large pairs the study was designed around. Structurally
identical to plot_study0_cost_boxplot.py (same pair grouping, same
small/large tint convention) so the two figures read as a set; only the
metric and pair order differ.

Note: wall_time is raw trial duration and is NOT comparable across
providers -- it reflects each API's serving latency/load as much as the
model itself, unlike cost_usd which is normalised through a fixed price
sheet. Read this figure as "time cost to the user of running a trial
against a given provider," not as a model-efficiency comparison on its own.

Reads study_0/results_all.csv directly (already collated by
scripts/collate_results.py -- no separate compute step needed here).
Writes figures/study0_time_boxplot.png.

Usage:
    python3 figures/scripts/plot_study0_time_boxplot.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "study_0", "results_all.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "study0_time_boxplot.png")

# Pair order: ranked by the LARGE model's median wall_time, ascending
# (recomputed from study_0/results_all.csv -- not a fixed convention,
# re-derive if the underlying timing data changes). Independent of
# plot_study0_cost_boxplot.py's PAIR_ORDER, which is ranked by cost.
PAIR_ORDER = ["Ministral", "DeepSeek-V4", "gpt-oss", "Qwen3-VL", "Nemotron-3", "GLM-4.7"]
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
    data = []
    colors = []
    alphas = []
    labels = []
    pos = 0
    box_width = 0.75
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
        data.append(sub["wall_time"].dropna().values)
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
        showmeans=True,
        meanprops=dict(marker="D", markersize=6, markerfacecolor="white",
                       markeredgecolor="#0b0b0b", markeredgewidth=1.3, zorder=5),
        zorder=3,
    )
    for patch, color, alpha in zip(bp["boxes"], colors, alphas):
        patch.set_facecolor(color)
        patch.set_alpha(alpha)
        patch.set_edgecolor(color)

    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Wall time per trial (s)", fontsize=12)
    ax.tick_params(axis="y", labelsize=10.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    size_handles = [
        plt.Rectangle((0, 0), 1, 1, facecolor="#52514e", alpha=SMALL_ALPHA, label="small"),
        plt.Rectangle((0, 0), 1, 1, facecolor="#52514e", alpha=LARGE_ALPHA, label="large"),
    ]
    size_legend = ax.legend(handles=size_handles, frameon=False, loc="upper left",
                            fontsize=10.5, title="Model size")
    ax.add_artist(size_legend)

    stat_handles = [
        plt.Line2D([0], [0], color="#0b0b0b", linewidth=1.6, label="Median"),
        plt.Line2D([0], [0], marker="D", linestyle="none", markersize=6,
                   markerfacecolor="white", markeredgecolor="#0b0b0b",
                   markeredgewidth=1.3, label="Mean"),
    ]
    ax.legend(handles=stat_handles, frameon=False, loc="upper left",
             fontsize=10.5, bbox_to_anchor=(0.16, 1.0))

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
