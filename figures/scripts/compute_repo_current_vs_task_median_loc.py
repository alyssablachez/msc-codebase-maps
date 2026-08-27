"""
Current (June 2026 clone) package LoC vs. median per-task package LoC, for
ALL 17 repos ever in the panel -- the 13 unchanged, core + transformers
(added 2026-07-12), and Deep-Live-Cam + open-interpreter (removed
2026-07-12). Removed repos get tier="removed" (plotted gray); the rest use
their current (final-panel) small/medium/large tier.

Current-LoC counting matches scripts/generate_all_maps.py's count_loc()
convention (raw newline count within the resolved package dir, no blank-line
filtering) -- same method already used for the 15 final-panel repos in
figures/data/repo_current_vs_task_loc.csv, reused here rather than
re-walked. Deep-Live-Cam/open-interpreter are walked fresh (small repos,
fast) since they were never in that file.

Median-task LoC: the 13 unchanged + core + transformers from
repo_maps/map_generation_stats.csv (final-panel issues); Deep-Live-Cam/
open-interpreter from figures/data/panel_composition_loc.csv's
panel=="original" rows (their original 3 sampled issues -- see
compute_panel_loc.py for how that was built).

Usage:
    python3 figures/scripts/compute_repo_current_vs_task_median_loc.py
"""
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
from package_resolver import resolve_package_dir  # noqa: E402

OUT_CSV = os.path.join(_ROOT, "figures", "data", "repo_current_vs_task_median_loc.csv")

EXTRA_REPOS = {
    "Deep-Live-Cam":    ("repos/deep_live_cam_full", "modules"),
    "open-interpreter": ("repos/open_interpreter_full", "interpreter"),
}

SKIP_DIRS = {
    ".git", "__pycache__", "build", "dist", ".eggs", ".tox",
    "venv", ".venv", "env", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


def count_loc_on_disk(root):
    py_loc = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "rb") as f:
                    content = f.read()
            except OSError:
                continue
            if b"\x00" in content[:1024]:
                continue
            py_loc += content.count(b"\n")
    return py_loc


def main():
    existing = pd.read_csv(os.path.join(_ROOT, "figures", "data", "repo_current_vs_task_loc.csv"))
    stats = pd.read_csv(os.path.join(_ROOT, "repo_maps", "map_generation_stats.csv"))
    median_final = stats.groupby(["repo", "tier"])["python_loc"].median().reset_index()

    rows = []
    for _, row in median_final.iterrows():
        current_loc = existing.loc[existing["repo"] == row["repo"], "current_loc"].iloc[0]
        rows.append({
            "repo": row["repo"], "tier": row["tier"],
            "current_loc": int(current_loc), "median_task_loc": int(row["python_loc"]),
        })

    panel_loc = pd.read_csv(os.path.join(_ROOT, "figures", "data", "panel_composition_loc.csv"))
    for repo, (rel_dir, pkg_name) in EXTRA_REPOS.items():
        repo_dir = os.path.join(_ROOT, rel_dir)
        pkg_dir = resolve_package_dir(repo_dir, pkg_name)
        current_loc = count_loc_on_disk(pkg_dir)

        orig = panel_loc[(panel_loc["repo"] == repo) & (panel_loc["panel"] == "original")]
        median_task_loc = int(orig["python_loc"].median())

        rows.append({
            "repo": repo, "tier": "removed",
            "current_loc": current_loc, "median_task_loc": median_task_loc,
        })
        print(f"{repo:<20} current_loc={current_loc:>10,}  median_task_loc={median_task_loc:>10,}")

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
