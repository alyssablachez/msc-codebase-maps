"""
Single-panel version of plot_delta_f1_histograms.py: every per-model
delta F1 across all 3 studies pooled into ONE histogram (not grouped/
colored by study -- the 3 studies' distributions turned out similar
enough in shape that a per-study color split wasn't adding anything).
Same source data, same "pure descriptive power" caveat (per-model
deltas aren't independent draws -- see that script's docstring).

The dominant zero-delta spike (~66% of all deltas) flattens every other
bin under a plain linear y-axis, so this renders the SAME pooled
histogram under several y-axis treatments as a comparison sheet:
  1. linear      -- the honest baseline; spike dominates by construction.
  2. symlog      -- log-like compression above a small linear threshold
                    near 0, so zero-count bins don't break (pure log
                    can't render a bar of height 0).
  3. sqrt        -- gentler compromise; height ~ sqrt(count), keeps zero
                    at zero without log's aggressive small-count blowup.
  4. broken axis -- two stacked panels sharing one x-axis, a short lower
                    panel for the tail bins at full linear resolution and
                    a separate upper panel (own scale) for the spike,
                    with a break mark -- the standard publication fix for
                    exactly this "one huge outlier bar, rest is the
                    story" shape.

Usage:
    python3 figures/scripts/plot_delta_f1_histogram_combined.py
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIG_DIR = os.path.join(_ROOT, "figures")

SOURCES = [
    os.path.join(_ROOT, "data", "issue_map_effect_ranking.csv"),
    os.path.join(_ROOT, "data", "issue_map_effect_ranking_study2.csv"),
    os.path.join(_ROOT, "data", "issue_map_effect_ranking_study3.csv"),
]
BAR_COLOR = "#2a78d6"

BIN_EDGES = np.linspace(-1.0, 1.0, 21)  # width 0.1, edge exactly at 0
BIN_WIDTH = BIN_EDGES[1] - BIN_EDGES[0]
BIN_CENTERS = (BIN_EDGES[:-1] + BIN_EDGES[1:]) / 2


def extract_deltas(csv_path):
    df = pd.read_csv(csv_path)
    deltas = []
    for s in df["per_model_delta_f1"]:
        for part in s.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            _, v = part.rsplit("=", 1)
            deltas.append(float(v))
    return np.array(deltas)


def pooled_counts():
    all_deltas = np.concatenate([extract_deltas(p) for p in SOURCES])
    counts, _ = np.histogram(all_deltas, bins=BIN_EDGES)
    return counts, all_deltas


def draw_bars(ax, counts):
    ax.bar(BIN_CENTERS, counts, width=BIN_WIDTH * 0.88, color=BAR_COLOR,
          zorder=3, edgecolor="white", linewidth=0.5)
    ax.axvline(0, color="#8a8980", linewidth=1, zorder=1, linestyle="--")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")
    ax.tick_params(axis="both", labelsize=9.5)


def main():
    counts, all_deltas = pooled_counts()
    n = len(all_deltas)
    print(f"n={n}, mean={all_deltas.mean():+.4f}, median={np.median(all_deltas):+.4f}, "
          f"up={int((all_deltas>0).sum())}, flat={int((all_deltas==0).sum())}, down={int((all_deltas<0).sum())}")
    spike_max = counts.max()

    # broken axis (own figure -- needs its own gridspec)
    fig2 = plt.figure(figsize=(11, 6))
    gs = fig2.add_gridspec(2, 1, height_ratios=[1, 2.6], hspace=0.08)
    ax_top = fig2.add_subplot(gs[0])
    ax_bot = fig2.add_subplot(gs[1], sharex=ax_top)

    draw_bars(ax_top, counts)
    draw_bars(ax_bot, counts)
    tail_max = counts[counts < spike_max * 0.3].max()
    ax_top.set_ylim(spike_max * 0.85, spike_max * 1.08)
    ax_bot.set_ylim(0, tail_max * 1.25)
    ax_top.spines["bottom"].set_visible(False)
    ax_bot.spines["top"].set_visible(False)
    ax_top.tick_params(axis="x", bottom=False, labelbottom=False)
    ax_top.set_yticks([spike_max])

    # break marks
    d = 0.012
    kwargs = dict(transform=ax_top.transAxes, color="#52514e", clip_on=False, linewidth=1)
    ax_top.plot((-d, +d), (-d * 3, +d * 3), **kwargs)
    kwargs.update(transform=ax_bot.transAxes)
    ax_bot.plot((-d, +d), (1 - d, 1 + d), **kwargs)

    ax_bot.set_xlabel("Delta F1 (condition − baseline), per model per issue x condition",
                     fontsize=10.5)
    fig2.text(0.02, 0.5, "Count", va="center", rotation="vertical", fontsize=10.5)
    fig2.tight_layout(rect=[0.02, 0, 1, 1])
    out2 = os.path.join(FIG_DIR, "delta_f1_histogram_combined_broken_axis.png")
    fig2.savefig(out2, dpi=300, bbox_inches="tight")
    plt.close(fig2)
    print(f"Saved: {out2}")


if __name__ == "__main__":
    main()
