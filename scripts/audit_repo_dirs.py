"""
Audit top-level and package subdirectories for all 15 repos at their
issue base commits. Outputs structured text for config writing.
"""
import ast as pyast
import os
import pickle
import re
import subprocess
from collections import defaultdict

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


def git_ls_tree_dirs(repo_dir, commit, path=""):
    cmd = ["git", "-C", repo_dir, "ls-tree", "-d", "--name-only", commit]
    if path:
        cmd.append(path)
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    # strip leading path prefix if present
    if path:
        prefix = path.rstrip("/") + "/"
        lines = [l[len(prefix):] if l.startswith(prefix) else l for l in lines]
    return lines


def parse_freq(issue_dir):
    """Return {rel_path: edit_count} from existing freq_map.txt."""
    path = os.path.join(issue_dir, "freq_map.txt")
    if not os.path.exists(path):
        return {}
    pattern = re.compile(r"^(.+?)\s+\[(\d+) edits")
    result = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                result[m.group(1)] = int(m.group(2))
    return result


def freq_for_dir(freq, prefix):
    """Sum edit counts for files under prefix (e.g. 'requests/packages/')."""
    total_files = 0
    total_edits = 0
    for path, count in freq.items():
        if path.startswith(prefix):
            total_files += 1
            total_edits += count
    return total_files, total_edits


def parse_gt(gt_str):
    try:
        val = pyast.literal_eval(str(gt_str))
        return val if isinstance(val, list) else [str(val)]
    except Exception:
        return []


def main():
    sel_csv  = os.path.join(_ROOT, "data", "issue_selection_random.csv")
    pkl_file = os.path.join(_ROOT, "data",
                            "all_issues_with_pr_commit_comment_all_project_0922.pkl")

    sel = pd.read_csv(sel_csv)
    with open(pkl_file, "rb") as f:
        pkl_df = pd.DataFrame(pickle.load(f))

    # Group by repo
    repo_issues = defaultdict(list)
    for _, row in sel.iterrows():
        repo = row["repo"]
        idx  = int(row["issue_idx"])
        subset = pkl_df[pkl_df["repo_name"] == repo].reset_index(drop=True)
        commit = subset.iloc[idx]["base_commit"]
        gt     = parse_gt(row["ground_truth"])
        repo_issues[repo].append((idx, commit, gt))

    for repo in [
        "requests", "thefuck", "flask", "gpt-engineer", "Deep-Live-Cam",
        "scrapy", "rich", "fastapi", "open-interpreter", "stable-diffusion-webui",
        "yt-dlp", "keras", "scikit-learn", "localstack", "pandas",
    ]:
        issues   = repo_issues[repo]
        repo_dir = os.path.join(_ROOT, REPO_FOLDER[repo])
        pkg      = PACKAGE_NAME[repo]

        print(f"\n{'='*72}")
        print(f"REPO: {repo}  (package: {pkg})")
        print(f"{'='*72}")

        # Print issues / commits / GT
        for idx, commit, gt in issues:
            gt_str = ", ".join(gt)
            print(f"  issue={idx:>3}  commit={commit[:8]}  GT: {gt_str}")

        # Collect dirs across all 3 commits
        all_toplevel_sets = []
        all_pkg_subdirs_sets = []
        for idx, commit, gt in issues:
            toplevel = git_ls_tree_dirs(repo_dir, commit)
            all_toplevel_sets.append((commit[:8], toplevel))
            pkg_subdirs = git_ls_tree_dirs(repo_dir, commit, pkg + "/")
            all_pkg_subdirs_sets.append((commit[:8], pkg_subdirs))

        # Top-level dirs — show per-commit if they differ
        if len({tuple(sorted(d)) for _, d in all_toplevel_sets}) == 1:
            dirs = all_toplevel_sets[0][1]
            print(f"\n  Top-level dirs (stable across 3 commits):")
            for d in dirs:
                print(f"    {d}/")
        else:
            for sha, dirs in all_toplevel_sets:
                print(f"\n  Top-level dirs at {sha}:")
                for d in dirs:
                    print(f"    {d}/")

        # Package subdirs — show per-commit if they differ
        if len({tuple(sorted(d)) for _, d in all_pkg_subdirs_sets}) == 1:
            dirs = all_pkg_subdirs_sets[0][1]
            print(f"\n  {pkg}/ subdirs (stable):")
            for d in dirs:
                print(f"    {d}/")
        else:
            for sha, dirs in all_pkg_subdirs_sets:
                print(f"\n  {pkg}/ subdirs at {sha}:")
                for d in dirs:
                    print(f"    {d}/")

        # Freq data: aggregate across all existing freq maps for this repo
        all_freq = {}
        for idx, commit, gt in issues:
            issue_dir = os.path.join(_ROOT, "repo_maps", repo, str(idx))
            freq = parse_freq(issue_dir)
            for path, count in freq.items():
                all_freq[path] = max(all_freq.get(path, 0), count)

        # Identify directories from union of top-level dirs across commits
        all_toplevel_union = sorted(set(
            d for _, dirs in all_toplevel_sets for d in dirs
        ))

        # Check each top-level dir for edit activity
        print(f"\n  Freq-map edit activity (max across 3 issues):")
        for d in all_toplevel_union:
            prefix = d + "/"
            n_files, n_edits = freq_for_dir(all_freq, prefix)
            if n_files > 0:
                avg = n_edits / n_files
                print(f"    {d}/  — {n_files} files, {n_edits} total edits (avg {avg:.1f})")
            else:
                # also check if it's a package subdir implicitly
                print(f"    {d}/  — not in freq map (outside package dir or no files walked)")

        # GT coverage check
        all_gt = sorted(set(f for _, _, gt in issues for f in gt))
        print(f"\n  Ground-truth files (union across 3 issues):")
        for f in all_gt:
            top = f.split("/")[0]
            print(f"    {f}  [top-dir: {top}/]")


if __name__ == "__main__":
    main()
