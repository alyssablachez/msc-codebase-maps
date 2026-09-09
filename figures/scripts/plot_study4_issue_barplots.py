"""
Study 4 -- one figure per expanded-replication issue (DEVLOG 2026-08-08),
each scoped to whichever outcome/grouping is actually meaningful for that
issue rather than a single forced template:

- flask/18, requests/12: single model, few conditions -- simple bar chart
  of success rate (%) by condition (success is a non-degenerate metric
  for both).
- gpt-engineer/9: 4 models x 11 non-baseline conditions -- too many
  conditions for the categorical palette, and the documented pattern is
  about consistency across conditions, not any one condition -- so this
  shows baseline vs. all non-baseline conditions POOLED, complete-miss
  rate (%), grouped by model.
- keras/5, localstack/19: 4 models x small condition set -- grouped bar,
  model on x-axis, condition colour-coded, complete-miss rate (%) (the
  metric that actually carries signal for both, per
  scripts/stats_study4_success_fishers.py).
- localstack/2: single model, 12 conditions -- grouped by DELIVERY
  MECHANISM (injection/on-demand-voluntary/on-demand-required) rather
  than individual condition, turn-cap hit rate (%), matching
  scripts/stats_study4_localstack2_turncap.py's actual test.
- scikit-learn/45: single model, 2 conditions -- simple bar chart,
  complete-miss rate (%) (the confirmed p=.0063 finding).

Reads data/compiled_results_combined.pkl directly.
Writes figures/study4_<repo>_<issue_idx>_barplot.png, one per issue.

Usage:
    python3 figures/scripts/plot_study4_issue_barplots.py
"""
import os
import sys

import matplotlib.pyplot as plt
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
from stats_study4_config import ISSUES, MODEL_LABELS  # noqa: E402

DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
FIG_DIR = os.path.join(_ROOT, "figures")

# Fixed categorical order, dataviz skill's reference palette (slots 1-8)
PALETTE = ["#8a8980", "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]

CONDITION_LABELS = {
    "none": "no map", "ast_compact": "structural\n(injected)", "freq": "frequency\n(injected)",
    "cochange": "co-change\n(injected)", "structural": "structural\n(voluntary)",
    "temporal_frequency": "frequency\n(voluntary)", "temporal_cochange": "co-change\n(voluntary)",
    "all_tools": "all tools\n(voluntary)", "structural_required": "structural\n(required)",
    "temporal_frequency_required": "frequency\n(required)",
    "temporal_cochange_required": "co-change\n(required)", "all_tools_required": "all tools\n(required)",
    "pooled_maps": "any map\n(pooled)",
}
MECH_LABELS = {"injection": "injection", "on_demand_voluntary": "on-demand\n(voluntary)",
              "on_demand_required": "on-demand\n(required)"}


def load_df():
    df = pd.read_pickle(DATA_PKL)
    df = df.dropna(subset=["success", "f1"]).copy()
    df["complete_miss"] = df["f1"] == 0.0
    return df


def bar_with_labels(ax, positions, heights, colors, labels):
    ax.bar(positions, heights, width=0.6, color=colors, zorder=3)
    for x, h in zip(positions, heights):
        ax.text(x, h + max(heights + [1]) * 0.02, f"{h:.0f}%", ha="center", va="bottom",
                fontsize=10, color="#52514e")
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, fontsize=9.5)
    ax.set_ylim(0, max(heights + [1]) * 1.2)
    ax.tick_params(axis="y", labelsize=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")


def simple_barplot(df, repo, issue_idx, model, conditions, baseline, outcome_col, ylabel, title):
    sub = df[(df["repo"] == repo) & (df["issue_idx"] == issue_idx) & (df["model"] == model)]
    all_conds = [baseline] + conditions
    heights = [sub[sub["map_condition_raw"] == c][outcome_col].mean() * 100 for c in all_conds]
    colors = PALETTE[:len(all_conds)]
    labels = [CONDITION_LABELS.get(c, c) for c in all_conds]

    fig, ax = plt.subplots(figsize=(7.5, 6))
    bar_with_labels(ax, list(range(len(all_conds))), heights, colors, labels)
    ax.set_xlabel("Condition", fontsize=11.5)
    ax.set_ylabel(ylabel, fontsize=11.5)
    ax.set_title(title, fontsize=11, color="#52514e")
    fig.tight_layout()
    out = os.path.join(FIG_DIR, f"study4_{repo}_{issue_idx}_barplot.png")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def grouped_by_model_barplot(df, repo, issue_idx, models, conditions, baseline, outcome_col, ylabel, title):
    all_conds = [baseline] + conditions
    n_c = len(all_conds)
    width = 0.7 / n_c
    offsets = [(-0.35 + width / 2) + i * width for i in range(n_c)]

    fig, ax = plt.subplots(figsize=(9.5, 6))
    for i, cond in enumerate(all_conds):
        heights = []
        for model in models:
            sub = df[(df["repo"] == repo) & (df["issue_idx"] == issue_idx) &
                    (df["model"] == model) & (df["map_condition_raw"] == cond)]
            heights.append(sub[outcome_col].mean() * 100)
        positions = [m_i + offsets[i] for m_i in range(len(models))]
        ax.bar(positions, heights, width=width * 0.9, color=PALETTE[i], zorder=3,
              label=CONDITION_LABELS.get(cond, cond).replace("\n", " "))
        for x, h in zip(positions, heights):
            ax.text(x, h + 2, f"{h:.0f}", ha="center", va="bottom", fontsize=7.5, color="#52514e")

    for m_i in range(1, len(models)):
        ax.axvline(m_i - 0.5, color="#e5e4da", linewidth=1, zorder=1)

    ax.set_xticks(range(len(models)))
    ax.set_xticklabels([MODEL_LABELS[m] for m in models], fontsize=10)
    ax.set_xlabel("Model", fontsize=11.5)
    ax.set_ylabel(ylabel, fontsize=11.5)
    ax.set_ylim(0, 105)
    ax.set_title(title, fontsize=11, color="#52514e")
    ax.tick_params(axis="y", labelsize=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9, frameon=True,
             framealpha=0.9, edgecolor="none", title="Condition", title_fontsize=9)

    fig.tight_layout()
    out = os.path.join(FIG_DIR, f"study4_{repo}_{issue_idx}_barplot.png")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def main():
    df = load_df()

    # flask/18 -- single model, success rate
    simple_barplot(df, "flask", 18, "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
                   ISSUES[("flask", 18)]["conditions"], "none", "success",
                   "Success rate (%)", "flask/18 -- Nemotron, success rate by condition (n=15/cell)")

    # requests/12 -- single model, success rate
    simple_barplot(df, "requests", 12, "deepseek/deepseek-v4-flash",
                   ISSUES[("requests", 12)]["conditions"], "none", "success",
                   "Success rate (%)", "requests/12 -- DeepSeek, success rate by condition (n=15/cell)")

    # scikit-learn/45 -- single model, complete-miss rate
    simple_barplot(df, "scikit-learn", 45, "mistral/ministral-3b-latest",
                   ISSUES[("scikit-learn", 45)]["conditions"], "none", "complete_miss",
                   "Complete-miss rate (%)", "scikit-learn/45 -- Ministral, complete-miss rate by condition (n=15/cell)")

    # keras/5 -- 4 models, complete-miss rate, grouped
    grouped_by_model_barplot(df, "keras", 5, ISSUES[("keras", 5)]["models"],
                             ISSUES[("keras", 5)]["conditions"], "none", "complete_miss",
                             "Complete-miss rate (%)", "keras/5 -- complete-miss rate by model and condition (n=15/cell)")

    # localstack/19 -- 4 models, complete-miss rate, grouped
    grouped_by_model_barplot(df, "localstack", 19, ISSUES[("localstack", 19)]["models"],
                             ISSUES[("localstack", 19)]["conditions"], "none", "complete_miss",
                             "Complete-miss rate (%)", "localstack/19 -- complete-miss rate by model and condition (n=15/cell)")

    # gpt-engineer/9 -- 4 models, baseline vs. all maps pooled, complete-miss rate
    cfg = ISSUES[("gpt-engineer", 9)]
    df_ge9 = df.copy()
    df_ge9["pooled_cond"] = df_ge9["map_condition_raw"].apply(
        lambda c: "pooled_maps" if c in cfg["conditions"] else c)
    grouped_by_model_barplot(df_ge9, "gpt-engineer", 9, cfg["models"], ["pooled_maps"], "none",
                             "complete_miss", "Complete-miss rate (%)",
                             "gpt-engineer/9 -- baseline vs. any map condition (pooled, 11 conditions), complete-miss rate")

    # localstack/2 -- delivery mechanism, turn-cap hit rate
    sub = df[(df["repo"] == "localstack") & (df["issue_idx"] == 2) &
            (df["model"] == "deepseek/deepseek-v4-flash")].copy()
    sub["mechanism"] = sub.apply(
        lambda r: "injection" if r["delivery_mechanism"] == "injection"
        else ("on_demand_required" if r["submission_mode"] == "required" else "on_demand_voluntary"),
        axis=1,
    )
    mech_order = ["injection", "on_demand_voluntary", "on_demand_required"]
    heights = [sub[sub["mechanism"] == m]["hit_turn_cap"].mean() * 100 for m in mech_order]
    colors = PALETTE[1:4]
    labels = [MECH_LABELS[m] for m in mech_order]
    fig, ax = plt.subplots(figsize=(7, 6))
    bar_with_labels(ax, list(range(3)), heights, colors, labels)
    ax.set_xlabel("Delivery mechanism", fontsize=11.5)
    ax.set_ylabel("Trials hitting the turn cap (%)", fontsize=11.5)
    ax.set_title("localstack/2 -- DeepSeek, turn-cap hit rate by delivery mechanism (n=45/group)",
                fontsize=11, color="#52514e")
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "study4_localstack_2_barplot.png")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
