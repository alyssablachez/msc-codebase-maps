"""
Study 4 -- F1 strip plots (one figure per expanded-replication issue),
companion to plot_study4_issue_barplots.py's success/complete-miss charts.

Box plots don't work well here: F1 in this data is extremely tie-heavy
(each issue only has a handful of achievable values -- e.g.
scikit-learn/45 is only ever 0 or .667), so a box's quartiles frequently
collapse onto each other or the median line, which reads as "no spread"
even where there is real, discrete-valued signal. A jittered strip plot
(every trial as its own point, small random horizontal jitter to avoid
perfect overplotting) shows the actual discrete clustering honestly,
with a mean marker overlaid for reference -- consistent with the rest of
this project's stats layer, which treats F1 nonparametrically rather
than assuming a continuous, unimodal distribution.

Same per-issue grouping choices as plot_study4_issue_barplots.py:
- flask/18, requests/12, scikit-learn/45: single model -- strip by
  condition.
- keras/5, localstack/19: 4 models -- grouped strip, model on x-axis,
  condition colour-coded (dodged).
- gpt-engineer/9: 4 models, baseline vs. all 11 non-baseline conditions
  POOLED (same pooling as the complete-miss chart), grouped strip.
- localstack/2: grouped by DELIVERY MECHANISM (matching
  scripts/stats_study4_localstack2_turncap.py and its companion chart),
  not by individual condition.

Reads data/compiled_results_combined.pkl directly.
Writes figures/study4_<repo>_<issue_idx>_f1.png, one per issue.

Usage:
    python3 figures/scripts/plot_study4_f1_stripplot.py
"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stats_study4_config import ISSUES, MODEL_LABELS  # noqa: E402
from plot_study4_issue_barplots import PALETTE, CONDITION_LABELS, MECH_LABELS  # noqa: E402

DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
FIG_DIR = os.path.join(_ROOT, "figures")

RNG = np.random.default_rng(20260901)
JITTER = 0.14
LINE_HALF_WIDTH = 0.16
POINT_SIZE = 34
POINT_ALPHA = 0.55
CAPTION = "each point = one trial \n the bar marks the group mean"


def load_df():
    df = pd.read_pickle(DATA_PKL)
    return df.dropna(subset=["f1"]).copy()


def _jitter_scatter(ax, x_center, vals, color, jitter=JITTER, line_half_width=LINE_HALF_WIDTH):
    if len(vals) == 0:
        return
    x = x_center + RNG.uniform(-jitter, jitter, size=len(vals))
    ax.scatter(x, vals, s=POINT_SIZE, color=color, alpha=POINT_ALPHA,
              edgecolors="none", zorder=2)
    mean = np.mean(vals)
    ax.hlines(mean, x_center - line_half_width, x_center + line_half_width,
              color=color, linewidth=3, zorder=4, capstyle="round")
    ax.text(x_center, mean + 0.028, f"{mean:.2f}", ha="center", va="bottom",
           fontsize=8.5, color="#52514e", zorder=5)


def style_axes(ax, xlabel, ylabel, title, show_title=False, caption_pos="below-legend"):
    ax.set_xlabel(xlabel, fontsize=11.5)
    ax.set_ylabel(ylabel, fontsize=11.5)
    # Title pad and the caption's offset are both in points (not axes
    # fraction), so the gap between them stays consistent regardless of
    # this chart's figure size -- an axes-fraction offset for the caption
    # scaled differently per figure height and collided with the title.
    if show_title:
        ax.set_title(title, fontsize=11, color="#52514e", pad=6)
    if caption_pos == "top":
        ax.annotate(CAPTION, xy=(0.5, 1.0), xycoords="axes fraction",
                   xytext=(0, 28), textcoords="offset points",
                   ha="center", fontsize=8.5, color="#8a8980")
    elif caption_pos == "bottom-right":
        ax.text(0.98, 0.03, CAPTION, transform=ax.transAxes, ha="right", va="bottom",
               fontsize=8.5, color="#52514e",
               bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#c3c2b7",
                        linewidth=0.8, alpha=1.0))
    elif caption_pos == "below-legend":
        # Outside the axes entirely, left-aligned with the legend's anchor
        # (1.01, 1) but low enough to clear it -- the legend only occupies
        # roughly the top fifth of the axes height here (title + 4 entries).
        ax.text(1.01, 0.75, CAPTION, transform=ax.transAxes, ha="left", va="top",
               fontsize=8.5, color="#52514e", clip_on=False,
               bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#c3c2b7",
                        linewidth=0.8, alpha=1.0))
    ax.set_ylim(-0.05, 1.1)
    ax.tick_params(axis="y", labelsize=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")
    ax.axhline(0, color="#e5e4da", linewidth=1, zorder=0)


def strip_by_condition(df, repo, issue_idx, model, conditions, baseline, title):
    sub = df[(df["repo"] == repo) & (df["issue_idx"] == issue_idx) & (df["model"] == model)]
    all_conds = [baseline] + conditions
    fig, ax = plt.subplots(figsize=(7.5, 6))
    for i, cond in enumerate(all_conds):
        vals = sub[sub["map_condition_raw"] == cond]["f1"].values
        _jitter_scatter(ax, i, vals, PALETTE[i % len(PALETTE)])
    ax.set_xticks(range(len(all_conds)))
    ax.set_xticklabels([CONDITION_LABELS.get(c, c) for c in all_conds], fontsize=9.5)
    ax.set_xlim(-0.6, len(all_conds) - 0.4)
    style_axes(ax, "Condition", "F1", title)
    fig.tight_layout()
    out = os.path.join(FIG_DIR, f"study4_{repo}_{issue_idx}_f1.png")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def strip_by_model_grouped(df, repo, issue_idx, models, conditions, baseline, title,
                           cond_labels=None, palette_offset=0, show_title=True,
                           caption_pos="top"):
    all_conds = [baseline] + conditions
    n_c = len(all_conds)
    # Use nearly the full 1.0 model slot (leaving a small margin so
    # clusters don't touch the divider line), and size the jitter/mean-line
    # to that slot's own width rather than a fixed constant -- otherwise
    # (as originally shipped) the jitter band is wider than the gap between
    # condition slots and adjacent conditions' point clouds bleed together.
    slot_width = 0.92 / n_c
    offsets = [(-0.46 + slot_width / 2) + i * slot_width for i in range(n_c)]
    jitter = slot_width * 0.30
    line_half_width = slot_width * 0.40
    cond_labels = cond_labels or CONDITION_LABELS

    fig, ax = plt.subplots(figsize=(9.5, 6))
    for i, cond in enumerate(all_conds):
        color = PALETTE[(i + palette_offset) % len(PALETTE)]
        for m_i, model in enumerate(models):
            vals = df[(df["repo"] == repo) & (df["issue_idx"] == issue_idx) &
                     (df["model"] == model) & (df["map_condition_raw"] == cond)]["f1"].values
            _jitter_scatter(ax, m_i + offsets[i], vals, color, jitter=jitter,
                           line_half_width=line_half_width)
        ax.scatter([], [], color=color, s=60, alpha=0.9,
                  label=cond_labels.get(cond, cond).replace("\n", " "))

    for m_i in range(1, len(models)):
        ax.axvline(m_i - 0.5, color="#e5e4da", linewidth=1, zorder=1)

    ax.set_xticks(range(len(models)))
    ax.set_xticklabels([MODEL_LABELS[m] for m in models], fontsize=10)
    ax.set_xlim(-0.6, len(models) - 0.4)
    style_axes(ax, "Model", "F1", title, show_title=show_title, caption_pos=caption_pos)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1), fontsize=9, frameon=True,
             framealpha=0.9, edgecolor="none", title="Condition", title_fontsize=9)

    fig.tight_layout()
    out = os.path.join(FIG_DIR, f"study4_{repo}_{issue_idx}_f1.png")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


def main():
    df = load_df()

    strip_by_condition(df, "flask", 18, "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
                       ISSUES[("flask", 18)]["conditions"], "none",
                       "flask/18 -- Nemotron, F1 by condition (n=15/cell)")

    strip_by_condition(df, "requests", 12, "deepseek/deepseek-v4-flash",
                       ISSUES[("requests", 12)]["conditions"], "none",
                       "requests/12 -- DeepSeek, F1 by condition (n=15/cell)")

    strip_by_condition(df, "scikit-learn", 45, "mistral/ministral-3b-latest",
                       ISSUES[("scikit-learn", 45)]["conditions"], "none",
                       "scikit-learn/45 -- Ministral, F1 by condition (n=15/cell)")

    strip_by_model_grouped(df, "keras", 5, ISSUES[("keras", 5)]["models"],
                           ISSUES[("keras", 5)]["conditions"], "none",
                           "keras/5 -- F1 by model and condition (n=15/cell)",
                           show_title=False, caption_pos="below-legend")

    strip_by_model_grouped(df, "localstack", 19, ISSUES[("localstack", 19)]["models"],
                           ISSUES[("localstack", 19)]["conditions"], "none",
                           "localstack/19 -- F1 by model and condition (n=15/cell)",
                           show_title=False, caption_pos="below-legend")

    cfg = ISSUES[("gpt-engineer", 9)]
    df_ge9 = df.copy()
    df_ge9["pooled_cond"] = df_ge9["map_condition_raw"].apply(
        lambda c: "pooled_maps" if c in cfg["conditions"] else c)
    df_ge9 = df_ge9.drop(columns=["map_condition_raw"]).rename(columns={"pooled_cond": "map_condition_raw"})
    strip_by_model_grouped(df_ge9, "gpt-engineer", 9, cfg["models"], ["pooled_maps"], "none",
                           "gpt-engineer/9 -- baseline vs. any map condition (pooled, 11 conditions), F1",
                           palette_offset=0, show_title=False, caption_pos="below-legend")

    sub = df[(df["repo"] == "localstack") & (df["issue_idx"] == 2) &
            (df["model"] == "deepseek/deepseek-v4-flash")].copy()
    sub["mechanism"] = sub.apply(
        lambda r: "injection" if r["delivery_mechanism"] == "injection"
        else ("on_demand_required" if r["submission_mode"] == "required" else "on_demand_voluntary"),
        axis=1,
    )
    mech_order = ["injection", "on_demand_voluntary", "on_demand_required"]
    fig, ax = plt.subplots(figsize=(7, 6))
    for i, mech in enumerate(mech_order):
        vals = sub[sub["mechanism"] == mech]["f1"].values
        _jitter_scatter(ax, i, vals, PALETTE[(i + 1) % len(PALETTE)])
    ax.set_xticks(range(3))
    ax.set_xticklabels([MECH_LABELS[m] for m in mech_order], fontsize=9.5)
    ax.set_xlim(-0.6, 2.4)
    style_axes(ax, "Delivery mechanism", "F1",
              "localstack/2 -- DeepSeek, F1 by delivery mechanism (n=45/group)")
    fig.tight_layout()
    out = os.path.join(FIG_DIR, "study4_localstack_2_f1.png")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
