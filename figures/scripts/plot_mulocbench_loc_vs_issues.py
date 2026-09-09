"""
Recreation of explore_dataset.ipynb's "Issues vs Codebase Size (MULocBench)"
scatter -- all 46 MULocBench repos with usable LoC data, repo-name labels
kept, coloured by this study's panel membership (final panel takes
priority over original-only where a repo is in both).

Label placement: a small custom vertical-collision resolver, not adjustText
-- adjustText repels in raw data space and doesn't understand log-scaled
axes (it previously flung a label to an extreme coordinate and corrupted
the output to a ~1.7-billion-pixel file). This resolver works entirely in
rendered display/pixel space and only ever moves labels vertically, so the
x-axis being log-scaled never enters the collision math.

Reads figures/data/mulocbench_repo_stats.csv (compute_mulocbench_repo_stats.py).
Writes figures/mulocbench_loc_vs_issues.png.
"""
import os

import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_CSV = os.path.join(_ROOT, "figures", "data", "mulocbench_repo_stats.csv")
OUT_PNG = os.path.join(_ROOT, "figures", "mulocbench_loc_vs_issues.png")

CATEGORY_ORDER = ["Final Panel", "Original Panel", "Never Included"]
CATEGORY_COLOR = {
    "Final Panel":    "#2a78d6",  # slot 1, blue
    "Original Panel": "#eb6834",  # slot 2, orange
    "Never Included": "#c3c2b7",  # muted gray -- background category
}
CATEGORY_SIZE = {"Final Panel": 65, "Original Panel": 65, "Never Included": 35}
CATEGORY_ZORDER = {"Final Panel": 4, "Original Panel": 4, "Never Included": 2}

LABEL_FONTSIZE = 10.5


def _shift_text_y(text, shift_px):
    x, y = text.get_position()
    transform = text.get_transform()
    disp = transform.transform((x, y))
    new_data = transform.inverted().transform((disp[0], disp[1] + shift_px))
    text.set_position((x, new_data[1]))


def declutter_vertical(fig, ax, texts, min_gap_px=3.0, max_passes=600):
    """Resolve vertical overlaps between text bboxes in display space only.

    All-pairs check each pass (n=46, negligible cost) rather than only
    adjacent-in-sorted-order pairs -- ties in y (common here, since issue
    counts are small integers) can otherwise let a pair's overlap survive
    sorting ambiguity. Overlapping pairs are pushed apart symmetrically:
    whichever has the larger y-center moves up, the other moves down.
    Never touches x, so the log-scaled x-axis is irrelevant to the math.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    for _ in range(max_passes):
        boxes = [(t, t.get_window_extent(renderer)) for t in texts]
        moved = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                t1, b1 = boxes[i]
                t2, b2 = boxes[j]
                x_overlap = not (b1.x1 < b2.x0 or b2.x1 < b1.x0)
                y_overlap = not (b1.y1 + min_gap_px < b2.y0 or b2.y1 + min_gap_px < b1.y0)
                if x_overlap and y_overlap:
                    overlap_amount = min(b1.y1, b2.y1) - max(b1.y0, b2.y0) + min_gap_px
                    half = overlap_amount / 2
                    if b1.y0 + b1.y1 >= b2.y0 + b2.y1:
                        _shift_text_y(t1, half)
                        _shift_text_y(t2, -half)
                    else:
                        _shift_text_y(t1, -half)
                        _shift_text_y(t2, half)
                    moved = True
        if not moved:
            break
        renderer = fig.canvas.get_renderer()


def main():
    df = pd.read_csv(DATA_CSV)

    fig, ax = plt.subplots(figsize=(14, 9.5))

    for cat in CATEGORY_ORDER:
        sub = df[df["category"] == cat]
        ax.scatter(sub["loc"], sub["issues"], color=CATEGORY_COLOR[cat],
                   s=CATEGORY_SIZE[cat], label=cat, zorder=CATEGORY_ZORDER[cat],
                   edgecolors="white" if cat != "Never Included" else "none",
                   linewidths=0.7)

    # Fixed pixel offset from the marker baked into the transform, so the
    # collider below can move labels in *data* y without disturbing the
    # marker-relative x nudge.
    px_offset = mtransforms.offset_copy(ax.transData, fig=fig, x=6, y=4, units="points")
    texts = []
    for _, row in df.iterrows():
        t = ax.text(row["loc"], row["issues"], row["repo"], fontsize=LABEL_FONTSIZE,
                    transform=px_offset, va="bottom", ha="left",
                    color="#0b0b0b" if row["category"] != "Never Included" else "#6b6a66")
        texts.append(t)

    ax.set_xscale("log")
    ax.set_ylim(bottom=0)
    ax.set_xlabel("Python Lines of Code (log scale)", fontsize=13)
    ax.set_ylabel("Number of Issues", fontsize=13)
    ax.tick_params(axis="both", labelsize=11)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color("#c3c2b7")
    ax.legend(frameon=False, loc="upper left", fontsize=12)

    declutter_vertical(fig, ax, texts)

    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    print(f"Saved: {OUT_PNG}")


if __name__ == "__main__":
    main()
