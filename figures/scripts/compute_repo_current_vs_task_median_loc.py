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
repo_maps/map_generation_stats.csv (final-panel issues, already computed
via generate_all_maps.py's count_loc()). Deep-Live-Cam/open-interpreter
are computed fresh here with that exact same function (imported directly,
not reimplemented) against their original 3 sampled issues' base_commits
-- NOT read from figures/data/panel_composition_loc.csv, which uses a
different counting method (non-blank lines, skip-dirs applied) and would
make these two rows inconsistent with the other 15 on the "median task"
side while being consistent on the "current" side. See DEVLOG-equivalent
note in compute_mulocbench_repo_stats.py for the broader LoC-source audit
this fix came out of.

Usage:
    python3 figures/scripts/compute_repo_current_vs_task_median_loc.py
"""
import os
import pickle
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
from package_resolver import resolve_package_dir  # noqa: E402
from generate_all_maps import count_loc, pkg_tree_path  # noqa: E402

OUT_CSV = os.path.join(_ROOT, "figures", "data", "repo_current_vs_task_median_loc.csv")
PKL_FILE = os.path.join(_ROOT, "data", "all_issues_with_pr_commit_comment_all_project_0922.pkl")

EXTRA_REPOS = {
    "Deep-Live-Cam":    ("repos/deep_live_cam_full", "modules", [1, 11, 0]),
    "open-interpreter": ("repos/open_interpreter_full", "interpreter", [5, 1, 0]),
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

    with open(PKL_FILE, "rb") as f:
        pkl_df = pd.DataFrame(pickle.load(f))

    for repo, (rel_dir, pkg_name, issue_idxs) in EXTRA_REPOS.items():
        repo_dir = os.path.join(_ROOT, rel_dir)
        pkg_dir = resolve_package_dir(repo_dir, pkg_name)
        current_loc = count_loc_on_disk(pkg_dir)

        subset = pkl_df[pkl_df["repo_name"] == repo].reset_index(drop=True)
        task_locs = []
        for idx in issue_idxs:
            base_commit = subset.iloc[idx]["base_commit"]
            tree_path = pkg_tree_path(repo_dir, base_commit, pkg_name)
            py_loc, _tot_loc = count_loc(repo_dir, base_commit, tree_path)
            task_locs.append(py_loc)
        median_task_loc = int(pd.Series(task_locs).median())
        print(f"  {repo} per-issue python_loc: {task_locs}")

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
