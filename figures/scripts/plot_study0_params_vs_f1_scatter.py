"""
Study 0 total-parameters-vs-F1 scatter -- one point per model, x = total
parameter count (not active/MoE-routed parameters) from
models/model_costs.xlsx's "Parameters" column, y = mean F1 across the
model's 75 trials. Colored by pair (same PAIR_COLOR as the other study0_*
figures), filled = large / open = small.

Total, not active, parameters: deliberately the more "naive" size number
(what a reader unfamiliar with the MoE architectures would assume the model
size to be) rather than active-parameter count, which would collapse most
of the MoE models onto a narrow band regardless of nominal size. X-axis is
log-scaled -- total parameters span 3B to 1.6T, ~3 orders of magnitude.

Two legends, not per-model labels: color identifies model family (pair),
fill/open identifies size -- the same split encoding as the other
study0_* figures, rather than naming all 12 individual models.

An OLS trendline is fit on log10(total_params) vs. F1 (linear-in-log, not
linear-in-params -- the right form for a relationship spanning 3 orders of
magnitude) with R2 annotated. At n=12, r=0.78 / R2=0.61 (p=0.003) and is
not an artifact of the deepseek-pro outlier at 1.6T -- excluding it gives
r=0.81 -- but R2 from 12 points is still noisy and should be read as
"moderate-to-strong positive trend," not a precise effect size.

Reads study_0/results_all.csv (F1) and models/model_costs.xlsx (parameter
counts) directly -- no separate compute step needed here.
Writes figures/study0_params_vs_f1_scatter.png.

Usage:
    python3 figures/scripts/plot_study0_params_vs_f1_scatter.py
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_CSV = os.path.join(_ROOT, "study_0", "results_all.csv")
MODEL_COSTS_XLSX = os.path.join(_ROOT, "models", "model_costs.xlsx")
OUT_PNG = os.path.join(_ROOT, "figures", "study0_params_vs_f1_scatter.png")

# model_short -> exact "Model" row name in models/model_costs.xlsx. Mirrors
# scripts/collate_results.py's MODEL_TO_PRICE_ROW (keyed there by folder
# name rather than model_short) -- kept in sync manually since the two
# scripts read different columns off the same sheet.
MODEL_TO_PRICE_ROW = {
    "Qwen3-VL-30B":         "Qwen3-VL-30B-A3B-Instruct",
    "Qwen3-VL-235B":        "Qwen3-VL-235B-A22B-Instruct",
    "gpt-oss-20b":          "gpt-oss-20b",
    "gpt-oss-120b":         "gpt-oss-120b",
    "ministral-3b":         "ministral-3b",
    "ministral-14b":        "ministral-14b",
    "deepseek-flash":       "deepseek-v4-flash",
    "deepseek-pro":         "deepseek-v4-pro",
    "Nemotron-Nano-30B":    "Nemotron-3-Nano-30B-A3B",
    "Nemotron-Super-120B":  "Nemotron-3-Super-120B-A12B",
    "GLM-4.7-Flash":        "GLM-4.7-Flash",
    "GLM-4.7":              "GLM-4.7",
}

PAIR_COLOR = {
    "Qwen3-VL":    "#2a78d6",
    "gpt-oss":     "#eb6834",
    "Ministral":   "#1baf7a",
    "DeepSeek-V4": "#eda100",
    "Nemotron-3":  "#e87ba4",
    "GLM-4.7":     "#008300",
}


def parse_params(s):
    s = str(s).strip()
    if s.endswith("T"):
        return float(s[:-1]) * 1000
    if s.endswith("B"):
        return float(s[:-1])
    raise ValueError(f"Unrecognised parameter-count format: {s!r}")


def main():
    results = pd.read_csv(RESULTS_CSV)
    f1_by_model = results.groupby(["pair_name", "model_size"]).agg(
        model_short=("model_short", "first"),
        f1=("f1", "mean"),
    ).reset_index()

    costs = pd.read_excel(MODEL_COSTS_XLSX).set_index("Model")
    f1_by_model["total_params_b"] = f1_by_model["model_short"].map(
        lambda short: parse_params(costs.loc[MODEL_TO_PRICE_ROW[short], "Parameters"])
    )

    fig, ax = plt.subplots(figsize=(9, 7))
    ax.set_xscale("log")

    # OLS trendline on log10(params) vs. F1 -- linear-in-log fits a scaling
    # relationship far better than a linear-in-params fit would across 3
    # orders of magnitude. r/R2 computed here on the same log10(x) so the
    # annotated R2 matches what the drawn line is actually fitting.
    log_params = np.log10(f1_by_model["total_params_b"])
    slope, intercept, r_value, _, _ = stats.linregress(log_params, f1_by_model["f1"])
    x_line = np.logspace(log_params.min(), log_params.max(), 100)
    y_line = slope * np.log10(x_line) + intercept
    ax.plot(x_line, y_line, color="#8a8980", linewidth=1.6, linestyle="--", zorder=2)
    ax.annotate(f"R² = {r_value**2:.2f}", xy=(0.04, 0.94), xycoords="axes fraction",
               fontsize=11, color="#52514e")

    for _, row in f1_by_model.iterrows():
        color = PAIR_COLOR[row["pair_name"]]
        is_large = row["model_size"] == "large"
        ax.scatter(row["total_params_b"], row["f1"], s=120,
                  facecolors=color if is_large else "white",
                  edgecolors=color, linewidths=2.0, zorder=4)

    ax.set_xlabel("Total parameters (billions, log scale)", fontsize=12)
    ax.set_ylabel("Mean F1", fontsize=12)
    ax.set_ylim(0.3, 0.9)
    ax.tick_params(axis="both", labelsize=10.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    # Two legends: color identifies model family (pair), fill/open
    # identifies size -- same split encoding as the other study0_* figures,
    # rather than naming all 12 individual models.
    family_handles = [
        plt.Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                  markerfacecolor=color, markeredgecolor=color, label=pair)
        for pair, color in PAIR_COLOR.items()
    ]
    family_legend = ax.legend(handles=family_handles, frameon=False, loc="lower right",
                              fontsize=10, title="Model family")
    ax.add_artist(family_legend)

    size_handles = [
        plt.Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                  markerfacecolor="#52514e", markeredgecolor="#52514e", label="Large"),
        plt.Line2D([0], [0], marker="o", linestyle="none", markersize=9,
                  markerfacecolor="white", markeredgecolor="#52514e",
                  markeredgewidth=1.8, label="Small"),
    ]
    ax.legend(handles=size_handles, frameon=False, loc="lower right", fontsize=10,
             title="Model size", bbox_to_anchor=(0.8, 0.0))

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
