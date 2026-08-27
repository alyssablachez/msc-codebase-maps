"""
Plot: Study 0 pilot map sizes (requests/, 5 tasks) by map type over time.

Grouped bar chart -- tasks ordered chronologically by base_commit date along
the x-axis (evenly spaced, date shown as the tick label -- a literal
continuous-date axis was tried first and rejected: the 5 commits span
2013-2017 unevenly, so true calendar spacing squashed every bar to a
hairline with two adjacent tasks' labels overlapping), one bar per map type
per task (ast / ctags / ast_compact, fixed categorical colour order),
grouped clusters labelled with the task number.

Reads figures/data/pilot_study_map_sizes.csv (scripts/compute_pilot_map_sizes.py).
Writes figures/pilot_study_map_size_comparison.png.

Usage:
    python3 figures/scripts/plot_pilot_map_sizes.py
"""
import os

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "figures", "data", "pilot_study_map_sizes.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "pilot_study_map_size_comparison.png")

# Fixed categorical order + validated palette (skill: dataviz, references/palette.md
# slot 1/2 as-is; slot 3 swapped for a teal shifted toward blue -- passes the
# same CVD/normal-vision floors as the reference aqua while reading closer in
# family to ast, since ast_compact is a derived view of the ast map).
MAP_TYPE_ORDER = ["ctags", "ast", "ast_compact"]
MAP_TYPE_LABEL = {"ctags": "ctags", "ast": "ast", "ast_compact": "ast compact"}
MAP_TYPE_COLOR = {
    "ctags":       "#eb6834",  # slot 2, orange
    "ast":         "#2a78d6",  # slot 1, blue
    "ast_compact": "#17a398",  # teal, validated replacement for slot 3
}


def main():
    df = pd.read_csv(DATA_CSV, parse_dates=["commit_date"])
    task_dates = (
        df[["task", "commit_date"]].drop_duplicates().sort_values("commit_date")
    )
    tasks = task_dates["task"].tolist()
    positions = {task: i for i, task in enumerate(tasks)}

    fig, ax = plt.subplots(figsize=(10, 5.5))

    n_series = len(MAP_TYPE_ORDER)
    bar_width = 0.8 / n_series
    offsets = [(i - (n_series - 1) / 2) * bar_width for i in range(n_series)]

    for map_type, offset in zip(MAP_TYPE_ORDER, offsets):
        sub = df[df["map_type"] == map_type].set_index("task").loc[tasks]
        x = np.array([positions[t] for t in tasks]) + offset
        ax.bar(
            x, sub["tokens"],
            width=bar_width * 0.92,
            color=MAP_TYPE_COLOR[map_type],
            label=MAP_TYPE_LABEL[map_type],
            zorder=3,
        )

    # Task-number labels above each group's tallest bar
    for task in tasks:
        top = df[df["task"] == task]["tokens"].max()
        ax.annotate(
            f"task {task}",
            xy=(positions[task], top),
            xytext=(0, 6), textcoords="offset points",
            ha="center", va="bottom",
            fontsize=9, color="#52514e",
        )

    ax.set_ylabel("Token count (estimated)")
    ax.set_xlabel("Task base_commit date (chronological order)")

    ax.set_xticks(list(positions.values()))
    ax.set_xticklabels(task_dates["commit_date"].dt.strftime("%Y-%m-%d"))
    ax.margins(x=0.08)
    ax.set_ylim(top=df["tokens"].max() * 1.12)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")

    ax.legend(frameon=False, loc="upper left", title=None)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300)
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
