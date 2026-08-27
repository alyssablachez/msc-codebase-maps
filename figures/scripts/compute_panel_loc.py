"""
Compute per-issue Python LoC for the ORIGINAL 15-repo panel (before the
2026-07-12 Deep-Live-Cam/open-interpreter -> core/transformers swap) and the
FINAL 15-repo panel (current issue_selection_final.csv), for a size-envelope
comparison figure.

"Original panel" = data/issue_selection_final.csv as of commit d40f375c^ (the
commit immediately before the repo swap) -- the exact 45-issue selection under
the original 15 repos, tiered per the pre-audit tier_map recorded in
DEVLOG.md's 2026-07-09 methodology entry. This is deliberately NOT
data/issue_selection_random.csv: that file is an earlier, noisier draft --
diffing it against issue_selection_final.csv shows nearly every repo's issue
indices differ, dominated by unrelated per-issue resampling (English/body
filters, overlap fixes) rather than the repo-panel decision this figure is
about. Pinning to d40f375c^ isolates exactly the repo-level swap.

LoC for original-panel issues comes from data/issue_pool_with_loc.csv
(the 13 unchanged repos + Deep-Live-Cam + open-interpreter's full candidate
pool, added in the same commit that performed the swap) and
data/issue_pool_extra_repos.csv (core/17, core/8 -- the pre-issue-swap core
issues). One issue (keras/27) is absent from issue_pool_with_loc.csv;
recomputed directly here via git archive + the same non-blank-line walk
build_issue_pool_with_loc.py uses, since it's a single point rather than a
batch rebuild.

Final-panel LoC comes straight from repo_maps/map_generation_stats.csv.

Usage:
    python3 figures/scripts/compute_panel_loc.py
"""
import os
import subprocess
import sys
import tarfile

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))
from package_resolver import resolve_package_dir  # noqa: E402

OUT_CSV = os.path.join(_ROOT, "figures", "data", "panel_composition_loc.csv")

# Tier map as it stood before the LoC audit re-tiering (DEVLOG 2026-07-09).
ORIG_TIER = {
    "requests": "small", "thefuck": "small", "flask": "small",
    "gpt-engineer": "small", "Deep-Live-Cam": "small",
    "scrapy": "medium", "rich": "medium", "fastapi": "medium",
    "open-interpreter": "medium", "stable-diffusion-webui": "medium",
    "yt-dlp": "large", "keras": "large", "scikit-learn": "large",
    "localstack": "large", "pandas": "large",
}

REMOVED_REPOS = {"Deep-Live-Cam", "open-interpreter"}
ADDED_REPOS = {"core", "transformers"}

SKIP_DIRS_DEFAULT = {
    "__pycache__", "build", "dist", ".eggs", ".tox", "venv", ".venv", "env",
    "site-packages", "tests", "test", "testing", "docs", "doc",
    "documentation", "examples", "example", "benchmarks", "benchmark", "scripts",
}


def git_show(commit_ish, path):
    result = subprocess.run(
        ["git", "show", f"{commit_ish}:{path}"],
        cwd=_ROOT, capture_output=True, text=True, check=True,
    )
    return result.stdout


def count_loc_via_archive(repo_dir, commit, package_name, tmp_dir):
    os.makedirs(tmp_dir, exist_ok=True)
    proc = subprocess.run(
        ["git", "-C", repo_dir, "archive", commit],
        capture_output=True, check=True,
    )
    with tarfile.open(fileobj=__import__("io").BytesIO(proc.stdout)) as tar:
        tar.extractall(tmp_dir)
    pkg_dir = resolve_package_dir(tmp_dir, package_name)
    loc = 0
    for dirpath, dirs, filenames in os.walk(pkg_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS_DEFAULT]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            with open(os.path.join(dirpath, fname), encoding="utf-8", errors="replace") as fh:
                loc += sum(1 for line in fh if line.strip())
    return loc


def build_original_panel():
    import io
    csv_text = git_show("d40f375c^", "data/issue_selection_final.csv")
    orig = pd.read_csv(io.StringIO(csv_text))[["repo", "issue_idx", "role"]]
    orig["tier"] = orig["repo"].map(ORIG_TIER)

    pool = pd.read_csv(os.path.join(_ROOT, "data", "issue_pool_with_loc.csv"))[
        ["repo", "issue_idx", "python_loc"]
    ]
    extra = pd.read_csv(os.path.join(_ROOT, "data", "issue_pool_extra_repos.csv"))[
        ["repo", "issue_idx", "python_loc"]
    ]
    lookup = pd.concat([pool, extra], ignore_index=True)

    merged = orig.merge(lookup, on=["repo", "issue_idx"], how="left")

    missing = merged[merged["python_loc"].isna()]
    for _, row in missing.iterrows():
        print(f"Recomputing LoC directly (not in pool CSV): {row['repo']}/{row['issue_idx']}")
        # keras/27-specific fallback path -- only case observed. Extend here if
        # future re-runs surface other gaps.
        repo_dir_map = {"keras": "repos/keras_full"}
        pkg_map = {"keras": "keras"}
        import pickle
        with open(os.path.join(_ROOT, "data", "all_issues_with_pr_commit_comment_all_project_0922.pkl"), "rb") as f:
            pkl_df = pd.DataFrame(pickle.load(f))
        subset = pkl_df[pkl_df["repo_name"] == row["repo"]].reset_index(drop=True)
        commit = subset.iloc[int(row["issue_idx"])]["base_commit"]
        tmp_dir = os.path.join("/tmp", f"_loc_recompute_{row['repo']}_{row['issue_idx']}")
        loc = count_loc_via_archive(
            os.path.join(_ROOT, repo_dir_map[row["repo"]]), commit, pkg_map[row["repo"]], tmp_dir
        )
        merged.loc[
            (merged["repo"] == row["repo"]) & (merged["issue_idx"] == row["issue_idx"]),
            "python_loc",
        ] = loc

    merged["panel"] = "original"
    merged["status"] = merged["repo"].apply(lambda r: "removed" if r in REMOVED_REPOS else "unchanged")
    return merged[["repo", "issue_idx", "role", "tier", "python_loc", "panel", "status"]]


def build_final_panel():
    stats = pd.read_csv(os.path.join(_ROOT, "repo_maps", "map_generation_stats.csv"))
    final = stats[["repo", "tier", "issue_idx", "role", "python_loc"]].copy()
    final["panel"] = "final"
    final["status"] = final["repo"].apply(lambda r: "added" if r in ADDED_REPOS else "unchanged")
    return final[["repo", "issue_idx", "role", "tier", "python_loc", "panel", "status"]]


def main():
    original = build_original_panel()
    final = build_final_panel()
    combined = pd.concat([original, final], ignore_index=True)
    combined["python_loc"] = combined["python_loc"].astype(int)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    combined.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}  ({len(combined)} rows)")
    print(combined.groupby(["panel", "tier"])["python_loc"].agg(["count", "min", "median", "max"]))


if __name__ == "__main__":
    main()
