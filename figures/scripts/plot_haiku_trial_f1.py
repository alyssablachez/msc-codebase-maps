"""
F1 strip plot for the standalone Haiku/transformers-27 trial (haiku_trial/,
isolated from the main study tree -- see harness/run_trial.py's
_is_claude_model/_system_message gate and this session's Haiku caching
work). Same jittered-strip + colored-mean-line convention as
figures/scripts/plot_study4_f1_stripplot.py, for the same reason: F1 here
is tie-heavy (few achievable values given a 12-file ground truth), so a
box plot's quartiles would collapse and hide the real, discrete spread --
particularly relevant for `freq`, whose median (0.154) sits far below its
mean (0.442), a bimodal shape a box plot would flatten into "no signal."

Includes the placebo control (co-change framing/instructions injected,
but the actual <codebase_map> content replaced with a "no co-change
history recorded" stub -- see haiku_trial/maps_placebo/). Placed
immediately next to real `cochange` for direct visual comparison: it
lands close to `none`, not `cochange`, showing the F1 lift is driven by
the map's actual relational content rather than merely being told a
co-change map exists. n=14 for placebo (one rep failed on an
Anthropic credit-balance error, not re-run) vs. n=15 for every other
condition, hence the per-point n in each condition's mean label.

Reads directly from haiku_trial/results/claude-haiku-4-5-20251001/
transformers/27/<condition>/rep*.json and
haiku_trial/results_placebo/claude-haiku-4-5-20251001/transformers/27/
cochange/rep*.json (not compiled_results_combined.pkl, which doesn't
include this run).

Usage:
    python3 figures/scripts/plot_haiku_trial_f1.py
"""
import glob
import json
import os

import matplotlib.pyplot as plt
import numpy as np

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(_ROOT, "haiku_trial", "results", "claude-haiku-4-5-20251001", "transformers", "27")
PLACEBO_DIR = os.path.join(_ROOT, "haiku_trial", "results_placebo", "claude-haiku-4-5-20251001", "transformers", "27")
FIG_DIR = os.path.join(_ROOT, "figures")

CONDITIONS = ["none", "ast_compact", "freq", "cochange", "cochange_placebo"]
COLORS = {"none": "#8a8980", "cochange": "#2a78d6", "ast_compact": "#eb6834",
         "freq": "#1baf7a", "cochange_placebo": "#a9c4e8"}
LABELS = {"none": "no map", "cochange": "co-change\n(injected)",
         "cochange_placebo": "co-change\n(framing only)",
         "ast_compact": "structural\n(injected)", "freq": "frequency\n(injected)"}
DIRS = {"none": RESULTS_DIR, "cochange": RESULTS_DIR, "cochange_placebo": PLACEBO_DIR,
       "ast_compact": RESULTS_DIR, "freq": RESULTS_DIR}
SUBDIR = {"none": "none", "cochange": "cochange", "cochange_placebo": "cochange",
         "ast_compact": "ast_compact", "freq": "freq"}

RNG = np.random.default_rng(20260901)
JITTER = 0.14
LINE_HALF_WIDTH = 0.16
POINT_SIZE = 34
POINT_ALPHA = 0.55
CAPTION = "each point = one trial\N{EM DASH}the bar marks the group mean"


def load_f1(cond):
    files = glob.glob(os.path.join(DIRS[cond], SUBDIR[cond], "rep*.json"))
    vals = []
    for f in files:
        d = json.load(open(f))
        vals.append(d["scores"]["f1"])
    return np.array(vals)


def _jitter_scatter(ax, x_center, vals, color):
    if len(vals) == 0:
        return
    x = x_center + RNG.uniform(-JITTER, JITTER, size=len(vals))
    ax.scatter(x, vals, s=POINT_SIZE, color=color, alpha=POINT_ALPHA, edgecolors="none", zorder=2)
    mean = np.mean(vals)
    ax.hlines(mean, x_center - LINE_HALF_WIDTH, x_center + LINE_HALF_WIDTH,
             color=color, linewidth=3, zorder=4, capstyle="round")
    ax.text(x_center, mean + 0.028, f"{mean:.2f} (n={len(vals)})", ha="center", va="bottom",
           fontsize=8.5, color="#52514e", zorder=5)


def main():
    fig, ax = plt.subplots(figsize=(8.2, 6))
    for i, cond in enumerate(CONDITIONS):
        vals = load_f1(cond)
        _jitter_scatter(ax, i, vals, COLORS[cond])

    ax.set_xticks(range(len(CONDITIONS)))
    ax.set_xticklabels([LABELS[c] for c in CONDITIONS], fontsize=9.5)
    ax.set_xlim(-0.6, len(CONDITIONS) - 0.4)
    ax.set_xlabel("Condition", fontsize=11.5)
    ax.set_ylabel("F1", fontsize=11.5)
    ax.text(0.98, 0.97, CAPTION, transform=ax.transAxes, ha="right", va="top",
           fontsize=8.5, color="#52514e",
           bbox=dict(boxstyle="round,pad=0.4", facecolor="white", edgecolor="#c3c2b7", linewidth=0.8, alpha=0.9))
    ax.set_ylim(-0.05, 1.1)
    ax.tick_params(axis="y", labelsize=10)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")
    ax.axhline(0, color="#e5e4da", linewidth=1, zorder=0)

    fig.tight_layout()
    out = os.path.join(FIG_DIR, "haiku_transformers_27_f1.png")
    fig.savefig(out, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
