"""
Study 2 (on-demand/voluntary map tools vs. baseline) -- input-tokens
violin plot broken out by BOTH model (x-axis clusters) and map condition
(one violin per condition within each cluster), motivated by the
significant log_size_c:model_short interaction terms found in the F1
GLMM and the per-model heterogeneity already visible in the Wilcoxon
token results. Colour here encodes MAP CONDITION (same fixed categorical
order/hues as every other Study 2 chart) -- model is the x-axis grouping
dimension instead, the reverse of this script's original layout.

Median/mean convention (solid line / diamond marker) matches every other
chart in this project. Tokens in millions, same as
figures/scripts/plot_study2_tokens_violinplot.py, to avoid matplotlib's
scientific-notation axis offset.

Reads data/compiled_results_combined.pkl directly.
Writes figures/study2_tokens_by_model_violinplot.png.

Usage:
    python3 figures/scripts/plot_study2_tokens_by_model_violinplot.py
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_PNG = os.path.join(_ROOT, "figures", "study2_tokens_by_model_violinplot.png")

MAP_ORDER = ["baseline", "structural", "temporal_frequency", "temporal_cochange", "all_tools"]
MAP_LABELS = {"baseline": "no map tools", "structural": "structural",
             "temporal_frequency": "frequency", "temporal_cochange": "co-change",
             "all_tools": "all tools"}
MAP_COLOR = {"baseline": "#8a8980", "structural": "#2a78d6",
            "temporal_frequency": "#eb6834", "temporal_cochange": "#1baf7a",
            "all_tools": "#eda100"}

MODEL_ORDER = ["deepseek/deepseek-v4-flash", "fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
              "mistral/ministral-3b-latest", "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B"]
MODEL_LABELS = {"deepseek/deepseek-v4-flash": "deepseek-flash",
               "fireworks_ai/accounts/fireworks/models/gpt-oss-120b": "gpt-oss-120b",
               "mistral/ministral-3b-latest": "ministral-3b",
               "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B": "nemotron-super"}

VIOLIN_WIDTH = 0.13
OFFSETS = [-0.32, -0.16, 0.0, 0.16, 0.32]


def load_study2():
    df = pd.read_pickle(DATA_PKL)
    return df[(df["rep"] <= 3) & ((df["study"] == 2) |
                                  ((df["study"] == 1) & (df["map_condition"] == "baseline")))].copy()


def main():
    df = load_study2()
    df = df.copy()
    df["tokens_m"] = df["total_input_tokens"] / 1e6

    fig, ax = plt.subplots(figsize=(11, 6.5))

    for group_pos, model in enumerate(MODEL_ORDER):
        for offset, cond in zip(OFFSETS, MAP_ORDER):
            vals = df.loc[(df["model"] == model) & (df["map_condition"] == cond), "tokens_m"].dropna().values
            if len(vals) == 0:
                continue
            pos = group_pos + offset
            parts = ax.violinplot([vals], positions=[pos], widths=VIOLIN_WIDTH,
                                  showmeans=False, showmedians=False, showextrema=False)
            for body in parts["bodies"]:
                body.set_facecolor(MAP_COLOR[cond])
                body.set_edgecolor(MAP_COLOR[cond])
                body.set_alpha(0.85)
                body.set_zorder(3)
            median, mean = np.median(vals), np.mean(vals)
            ax.hlines(median, pos - VIOLIN_WIDTH / 2, pos + VIOLIN_WIDTH / 2,
                      color="#0b0b0b", linewidth=1.3, zorder=5)
            ax.scatter([pos], [mean], marker="D", s=20, facecolor="white",
                      edgecolor="#0b0b0b", linewidths=1.0, zorder=6)

    for group_pos in range(1, len(MODEL_ORDER)):
        ax.axvline(group_pos - 0.5, color="#e5e4da", linewidth=1, zorder=1)

    ax.set_xticks(range(len(MODEL_ORDER)))
    ax.set_xticklabels([MODEL_LABELS[m] for m in MODEL_ORDER], fontsize=10.5)
    ax.set_xlabel("Model", fontsize=12)
    ax.set_ylabel("Input tokens per trial (millions)", fontsize=12)
    ax.set_ylim(bottom=0)
    ax.tick_params(axis="y", labelsize=10.5)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    map_handles = [plt.Rectangle((0, 0), 1, 1, facecolor=MAP_COLOR[m], edgecolor=MAP_COLOR[m],
                                 alpha=0.85, label=MAP_LABELS[m].replace("\n", " ")) for m in MAP_ORDER]
    stat_handles = [
        plt.Line2D([0], [0], color="#0b0b0b", linewidth=1.3, label="Median"),
        plt.Line2D([0], [0], marker="D", linestyle="none", markersize=6,
                   markerfacecolor="white", markeredgecolor="#0b0b0b",
                   markeredgewidth=1.0, label="Mean"),
    ]
    legend1 = ax.legend(handles=map_handles, loc="upper left", fontsize=9.5, frameon=True,
                        framealpha=0.9, edgecolor="none", title="Map condition", title_fontsize=9.5)
    ax.add_artist(legend1)
    ax.legend(handles=stat_handles, loc="upper right", fontsize=9.5, frameon=True,
             framealpha=0.9, edgecolor="none")

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
