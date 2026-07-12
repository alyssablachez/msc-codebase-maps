"""
Add python_loc and total_loc columns to repo_maps/map_generation_stats.csv.

Counts lines of code in the source directory at each issue's base commit
using git archive (no checkout required). Counts are over the package
directory only (same tree that the maps walk), without skip-dir filtering.

  python_loc — lines in .py files
  total_loc  — lines in all text files (binary files skipped)

Usage:
    python3 scripts/add_loc_to_stats.py
    python3 scripts/add_loc_to_stats.py --dry-run
"""
import argparse
import io
import os
import subprocess
import tarfile

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REPO_FOLDER = {
    "requests":               "repos/requests_full",
    "thefuck":                "repos/thefuck_full",
    "flask":                  "repos/flask_full",
    "gpt-engineer":           "repos/gpt_engineer_full",
    "Deep-Live-Cam":          "repos/deep_live_cam_full",
    "scrapy":                 "repos/scrapy_full",
    "rich":                   "repos/rich_full",
    "fastapi":                "repos/fastapi_full",
    "open-interpreter":       "repos/open_interpreter_full",
    "stable-diffusion-webui": "repos/stable_diffusion_webui_full",
    "yt-dlp":                 "repos/ytdlp_full",
    "keras":                  "repos/keras_full",
    "scikit-learn":           "repos/scikit_learn_full",
    "localstack":             "repos/localstack_full",
    "pandas":                 "repos/pandas_full",
}

PACKAGE_NAME = {
    "requests":               "requests",
    "thefuck":                "thefuck",
    "flask":                  "flask",
    "gpt-engineer":           "gpt_engineer",
    "Deep-Live-Cam":          "modules",
    "scrapy":                 "scrapy",
    "rich":                   "rich",
    "fastapi":                "fastapi",
    "open-interpreter":       "interpreter",
    "stable-diffusion-webui": "modules",
    "yt-dlp":                 "yt_dlp",
    "keras":                  "keras",
    "scikit-learn":           "sklearn",
    "localstack":             "localstack",
    "pandas":                 "pandas",
}


def pkg_tree_path(repo_dir, commit, pkg_name):
    """
    Return the path within the git tree for the package at this commit.
    Returns '' for flat-structure repos (gpt-engineer/32).
    """
    for candidate in [f"src/{pkg_name}", pkg_name]:
        r = subprocess.run(
            ["git", "-C", repo_dir, "ls-tree", "--name-only", commit,
             candidate + "/"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            return candidate
    return ""   # flat / repo-root walk


def count_loc(repo_dir, commit, tree_path):
    """
    Count (python_loc, total_loc) in tree_path at commit using git archive.
    Skips binary files (detected by null bytes in first 1024 bytes).
    """
    cmd = ["git", "-C", repo_dir, "archive", commit]
    if tree_path:
        cmd.append(tree_path + "/")

    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        return None, None

    python_loc = 0
    total_loc  = 0

    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                try:
                    content = f.read()
                    if b"\x00" in content[:1024]:   # binary file
                        continue
                    lines = content.count(b"\n")
                    total_loc += lines
                    if member.name.endswith(".py"):
                        python_loc += lines
                except Exception:
                    pass
    except Exception:
        return None, None

    return python_loc, total_loc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    stats_path = os.path.join(_ROOT, "repo_maps", "map_generation_stats.csv")
    stats = pd.read_csv(stats_path)

    python_locs = []
    total_locs  = []

    for _, row in stats.iterrows():
        repo      = row["repo"]
        commit    = row["base_commit"]   # 8-char sha
        repo_dir  = os.path.join(_ROOT, REPO_FOLDER[repo])
        pkg_name  = PACKAGE_NAME[repo]

        tree_path = pkg_tree_path(repo_dir, commit, pkg_name)

        py_loc, tot_loc = count_loc(repo_dir, commit, tree_path)
        python_locs.append(py_loc)
        total_locs.append(tot_loc)

        path_display = tree_path + "/" if tree_path else "(root)"
        print(f"  {repo}/{int(row['issue_idx']):<3}  @{commit}  "
              f"{path_display:<20}  python={py_loc:>7,}  total={tot_loc:>7,}")

    stats["python_loc"] = python_locs
    stats["total_loc"]  = total_locs

    if args.dry_run:
        print("\n(dry-run — not written)")
        return

    stats.to_csv(stats_path, index=False)
    print(f"\nWrote {stats_path}  ({len(stats)} rows)")

    # Summary by repo
    print(f"\n{'repo':<28}  {'python_loc':>10}  {'total_loc':>10}")
    print("-" * 54)
    for repo, grp in stats.groupby("repo"):
        py  = grp["python_loc"].mean()
        tot = grp["total_loc"].mean()
        print(f"{repo:<28}  {py:>10,.0f}  {tot:>10,.0f}")


if __name__ == "__main__":
    main()
