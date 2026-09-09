"""
Study 0 caching savings -- dumbbell chart, one row per model, showing mean
cost per trial actually paid (cost_usd, caching discount applied) vs. what
the same trials would have cost with no caching discount (cost_usd_uncached).
The gap between the two dots is the caching saving; cached_tokens is a
strict subset of input_tokens for every trial (verified: 0/900 rows with
cached_tokens > input_tokens), so this reads as "how much did caching save,"
not a double-counted total.

Rows ordered the same way as the cost boxplot (figures/study0_cost_boxplot.py)
-- paired by pair_name, small then large, pairs ranked by the large model's
median cost_usd ascending -- and reuse that script's PAIR_COLOR so the two
figures read as a set. Filled dot = actual (cached) cost; open dot = cost
with no caching discount.

Reads study_0/results_all.csv directly (already collated + cost-corrected
by scripts/collate_results.py -- no separate compute step needed here).
Writes figures/study0_cache_savings.png.

Usage:
    python3 figures/scripts/plot_study0_cache_savings.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "study_0", "results_all.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "study0_cache_savings.png")

# Same pair order/colors as plot_study0_cost_boxplot.py, for a matched pair
# of figures -- re-derive PAIR_ORDER if the underlying cost data changes.
PAIR_ORDER = ["DeepSeek-V4", "gpt-oss", "Nemotron-3", "Ministral", "Qwen3-VL", "GLM-4.7"]
PAIR_COLOR = {
    "Qwen3-VL":    "#2a78d6",
    "gpt-oss":     "#eb6834",
    "Ministral":   "#1baf7a",
    "DeepSeek-V4": "#eda100",
    "Nemotron-3":  "#e87ba4",
    "GLM-4.7":     "#008300",
}

MODEL_ORDER = []
for pair in PAIR_ORDER:
    MODEL_ORDER.append((pair, "small"))
    MODEL_ORDER.append((pair, "large"))


def main():
    df = pd.read_csv(DATA_CSV)
    agg = df.groupby(["pair_name", "model_size"]).agg(
        model_short=("model_short", "first"),
        cost_usd=("cost_usd", "mean"),
        cost_usd_uncached=("cost_usd_uncached", "mean"),
    )

    # Plot top-to-bottom in the same order as MODEL_ORDER, so reverse the
    # y-positions (matplotlib rows go bottom-up by default).
    n = len(MODEL_ORDER)
    ypos = list(range(n - 1, -1, -1))

    fig, ax = plt.subplots(figsize=(9, 7))

    labels = []
    for y, (pair, size) in zip(ypos, MODEL_ORDER):
        row = agg.loc[(pair, size)]
        color = PAIR_COLOR[pair]
        labels.append(row["model_short"])
        ax.plot([row["cost_usd"], row["cost_usd_uncached"]], [y, y],
                color=color, linewidth=2.0, zorder=2, alpha=0.55 if size == "small" else 1.0)
        ax.scatter(row["cost_usd_uncached"], y, s=80, facecolors="white",
                   edgecolors=color, linewidths=1.8, zorder=3)
        ax.scatter(row["cost_usd"], y, s=80, facecolors=color, edgecolors=color,
                   linewidths=1.8, zorder=4)

    ax.set_yticks(ypos)
    ax.set_yticklabels(labels, fontsize=10.5)
    ax.set_xlabel("Mean cost per trial (USD)", fontsize=12)
    ax.tick_params(axis="x", labelsize=10.5)
    ax.set_ylim(-1, n)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    handles = [
        plt.Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                   markerfacecolor="#52514e", markeredgecolor="#52514e",
                   label="Actual cost (caching applied)"),
        plt.Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                   markerfacecolor="white", markeredgecolor="#52514e", markeredgewidth=1.8,
                   label="Cost with no caching discount"),
    ]
    ax.legend(handles=handles, frameon=False, loc="lower right", fontsize=10)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
