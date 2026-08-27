"""
Compute, for each of the 15 final-panel repos: (a) current on-disk package
LoC (as of the June 2026 clone -- no commit checkout, just what's on disk
now) and (b) mean per-task package LoC across that repo's sampled issues, at
each issue's own base_commit (from repo_maps/map_generation_stats.csv).

Both counts use the same convention -- git-archive/on-disk raw newline count
(content.count(b"\\n")) within the resolved package directory, no blank-line
filtering -- matching scripts/generate_all_maps.py's count_loc() exactly, so
the two sides of the comparison aren't using different counting rules.

Usage:
    python3 figures/scripts/compute_repo_current_vs_task_loc.py
"""
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
from package_resolver import resolve_package_dir  # noqa: E402
from repo_config import REPO_DIR_MAP, PACKAGE_MAP  # noqa: E402

OUT_CSV = os.path.join(_ROOT, "figures", "data", "repo_current_vs_task_loc.csv")

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
    stats = pd.read_csv(os.path.join(_ROOT, "repo_maps", "map_generation_stats.csv"))
    task_avg = stats.groupby(["repo", "tier"])["python_loc"].mean().reset_index()
    task_avg = task_avg.rename(columns={"python_loc": "mean_task_loc"})

    rows = []
    for repo in task_avg["repo"]:
        repo_dir = os.path.join(_ROOT, REPO_DIR_MAP[repo])
        pkg_dir = resolve_package_dir(repo_dir, PACKAGE_MAP[repo])
        current_loc = count_loc_on_disk(pkg_dir)
        rows.append({"repo": repo, "current_loc": current_loc})
        print(f"{repo:<28} current_loc={current_loc:>10,}")

    current = pd.DataFrame(rows)
    combined = task_avg.merge(current, on="repo")
    combined["mean_task_loc"] = combined["mean_task_loc"].round(0).astype(int)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    combined.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")
    print(combined.to_string(index=False))


if __name__ == "__main__":
    main()
