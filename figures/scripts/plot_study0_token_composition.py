"""
Study 0 token composition -- stacked bar of mean tokens per trial, per model,
split into non-cached input, cached input, and output tokens.

cached_tokens is a strict subset of input_tokens (verified: 0/900 rows with
cached_tokens > input_tokens), so the input segment is split into
(input_tokens - cached_tokens) + cached_tokens rather than stacking raw
input_tokens on top of cached_tokens, which would double-count the cached
portion. The three segments sum to true total tokens per trial.

Models ordered the same way as the cost boxplot / cache-savings dumbbell
(figures/study0_cost_boxplot.py, figures/study0_cache_savings.py) -- paired
by pair_name, small then large, pairs ranked by the large model's median
cost_usd ascending -- so the three figures read as a set.

Both input segments share one hue (blue, slot 1 of the dataviz skill's
reference categorical palette) and are distinguished by tint -- full colour
for non-cached, a lighter alpha for cached -- the same small/large tint
convention used in the other study0_*_boxplot figures, here signalling
"same underlying thing, different flavour" rather than two unrelated
categories. Output keeps its own distinct hue (aqua, slot 3) since it is
a genuinely different token type, not a flavour of input.

Reads study_0/results_all.csv directly (already collated by
scripts/collate_results.py -- no separate compute step needed here).
Writes figures/study0_token_composition.png.

Usage:
    python3 figures/scripts/plot_study0_token_composition.py
"""
import os

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "study_0", "results_all.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "study0_token_composition.png")

PAIR_ORDER = ["DeepSeek-V4", "Nemotron-3", "Qwen3-VL", "Ministral", "gpt-oss", "GLM-4.7"]
MODEL_ORDER = []
for pair in PAIR_ORDER:
    MODEL_ORDER.append((pair, "small"))
    MODEL_ORDER.append((pair, "large"))

SEGMENT_COLOR = {
    "Input (non-cached)": "#2a78d6",  # slot 1, blue -- full tint
    "Input (cached)":     "#2a78d6",  # slot 1, blue -- light tint (same hue as above)
    "Output":             "#1baf7a",  # slot 3, aqua -- distinct category
}
SEGMENT_ALPHA = {
    "Input (non-cached)": 1.0,
    "Input (cached)":     0.45,
    "Output":             1.0,
}
SEGMENTS = ["Input (non-cached)", "Input (cached)", "Output"]


def main():
    df = pd.read_csv(DATA_CSV)
    df = df.copy()
    df["input_noncached"] = df["input_tokens"] - df["cached_tokens"]

    agg = df.groupby(["pair_name", "model_size"]).agg(
        model_short=("model_short", "first"),
        input_noncached=("input_noncached", "mean"),
        cached_tokens=("cached_tokens", "mean"),
        output_tokens=("output_tokens", "mean"),
    )

    labels = []
    values = {seg: [] for seg in SEGMENTS}
    for pair, size in MODEL_ORDER:
        row = agg.loc[(pair, size)]
        labels.append(row["model_short"])
        values["Input (non-cached)"].append(row["input_noncached"])
        values["Input (cached)"].append(row["cached_tokens"])
        values["Output"].append(row["output_tokens"])

    x = range(len(MODEL_ORDER))
    fig, ax = plt.subplots(figsize=(12, 6.5))

    bottom = [0] * len(MODEL_ORDER)
    for seg in SEGMENTS:
        ax.bar(x, values[seg], bottom=bottom, width=0.65, color=SEGMENT_COLOR[seg],
               alpha=SEGMENT_ALPHA[seg], label=seg, edgecolor="white", linewidth=0.6, zorder=3)
        bottom = [b + v for b, v in zip(bottom, values[seg])]

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10)
    ax.set_ylabel("Mean tokens per trial", fontsize=12)
    ax.tick_params(axis="y", labelsize=10.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    ax.legend(frameon=False, loc="upper left", fontsize=10.5)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
