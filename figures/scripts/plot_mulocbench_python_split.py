"""
Python vs. non-Python LoC (raw, not %) by repo, one separate file per size
tier (small/medium/large, MULocBench's own bucketing) rather than combined
into one image or normalized to %.

Reads figures/data/mulocbench_python_split.csv (compute_mulocbench_python_split.py).
Writes figures/mulocbench_python_split_{small,medium,large}.png.
"""
import os

import pandas as pd
import matplotlib.pyplot as plt

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "figures", "data", "mulocbench_python_split.csv")

SIZE_ORDER = ["small", "medium", "large"]
SIZE_TITLE = {"small": "Small (< 10k LoC)", "medium": "Medium (10k–100k LoC)", "large": "Large (≥ 100k LoC)"}
SIZE_FILE = {
    "small": "mulocbench_python_split_small.png",
    "medium": "mulocbench_python_split_medium.png",
    "large": "mulocbench_python_split_large.png",
}

PYTHON_COLOR = "#2a78d6"  # slot 1, blue
OTHER_COLOR = "#c3c2b7"   # muted gray


def main():
    df = pd.read_csv(DATA_CSV)
    df["total_loc"] = df["python_loc"] + df["other_loc"]
    df["pct_python"] = df["python_loc"] / df["total_loc"] * 100

    for size in SIZE_ORDER:
        sub = df[df["size"] == size].sort_values("python_loc")
        out_png = os.path.join(_ROOT, "figures", SIZE_FILE[size])

        fig, ax = plt.subplots(figsize=(10, max(3.5, len(sub) * 0.45)))
        y = range(len(sub))

        ax.barh(y, sub["python_loc"], color=PYTHON_COLOR, label="Python (.py)", zorder=3)
        ax.barh(y, sub["other_loc"], left=sub["python_loc"], color=OTHER_COLOR,
                label="Other languages", zorder=3)

        for yi, (_, row) in zip(y, sub.iterrows()):
            ax.annotate(f"{row['pct_python']:.1f}%", xy=(row["total_loc"], yi),
                        xytext=(6, 0), textcoords="offset points",
                        va="center", fontsize=9.5, color="#52514e")

        ax.set_yticks(list(y))
        ax.set_yticklabels(sub["repo"], fontsize=10.5)
        ax.set_xlabel("Lines of Code", fontsize=12)
        ax.set_xlim(right=sub["total_loc"].max() * 1.12)
        ax.set_title(SIZE_TITLE[size], loc="left", fontsize=13)
        ax.tick_params(axis="x", labelsize=10.5)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        for spine in ("left", "bottom"):
            ax.spines[spine].set_color("#c3c2b7")
        ax.legend(frameon=False, loc="lower right", fontsize=10.5)

        fig.tight_layout()
        fig.savefig(out_png, dpi=300, bbox_inches="tight")
        plt.close(fig)
        print(f"Saved: {out_png}")


if __name__ == "__main__":
    main()
