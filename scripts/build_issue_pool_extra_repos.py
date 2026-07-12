"""
Build a filtered issue pool for the 4 extra candidate repos:
    youtube-dl, ComfyUI, transformers, home-assistant/core

Identical logic to build_issue_pool_with_loc.py — only the repo
configuration and output paths differ. Results can be concatenated
with data/issue_pool_with_loc.csv after both runs complete.

Output:
    data/issue_pool_extra_repos.csv
    data/issue_pool_extra_repos_summary.txt

Usage:
    python3 scripts/build_issue_pool_extra_repos.py
    python3 scripts/build_issue_pool_extra_repos.py --dry-run
"""

import argparse
import math
import os
import pickle
import subprocess
import sys
import traceback

import pandas as pd
import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "scripts"))

from git_utils import checkout, current_head, restore
from package_resolver import resolve_package_dir
from source_filter import source_files_only

# ── Repo configuration ────────────────────────────────────────────────────────
# Pickle repo_name → (folder, package_name, tier)
# Tiers are best-guess placeholders — adjust after reviewing LoC output.

REPO_FOLDER = {
    "youtube-dl": "repos/youtube_dl_full",
    "ComfyUI":    "repos/ComfyUI_full",
    "transformers":"repos/transformers_full",
    "core":       "repos/core_full",
}

PACKAGE_NAME = {
    "youtube-dl":  "youtube_dl",
    "ComfyUI":     "comfy",
    "transformers": "transformers",   # resolver finds src/transformers/
    "core":        "homeassistant",
}

TIER = {
    "youtube-dl":  "large",
    "ComfyUI":     "medium",
    "transformers": "large",
    "core":        "large",
}

SKIP_CONFIG_YAML = os.path.join(_ROOT, "data", "repo_skip_config.yaml")


# ── ASCII heuristic ───────────────────────────────────────────────────────────

def _is_ascii_enough(text, threshold=0.85):
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / len(text) >= threshold


# ── Skip-dirs loader ──────────────────────────────────────────────────────────

_skip_cfg = None


def _get_skip_cfg():
    global _skip_cfg
    if _skip_cfg is None:
        with open(SKIP_CONFIG_YAML, encoding="utf-8") as f:
            _skip_cfg = yaml.safe_load(f)
    return _skip_cfg


def load_skip_dirs(repo, issue_idx):
    cfg = _get_skip_cfg()
    defaults = cfg.get("defaults", {}).get("skip_dirs", [])
    key = f"{repo}/{issue_idx}"
    extra = cfg.get("issues", {}).get(key, {}).get("extra_skip_dirs", [])
    return defaults + extra


# ── LoC counting ──────────────────────────────────────────────────────────────

def count_py_loc(pkg_dir, skip_dirs_set):
    py_loc = 0
    n_files = 0
    for dirpath, dirs, filenames in os.walk(pkg_dir):
        dirs[:] = [d for d in dirs if d not in skip_dirs_set]
        for fname in sorted(filenames):
            if not fname.endswith(".py"):
                continue
            filepath = os.path.join(dirpath, fname)
            try:
                with open(filepath, encoding="utf-8", errors="replace") as fh:
                    for line in fh:
                        if line.strip():
                            py_loc += 1
                n_files += 1
            except OSError:
                pass
    return py_loc, n_files


# ── Git helpers ───────────────────────────────────────────────────────────────

def git_ls_tree_all(repo_dir, commit):
    r = subprocess.run(
        ["git", "-C", repo_dir, "ls-tree", "-r", "--name-only", commit],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    return {
        line.strip().replace("\\", "/")
        for line in r.stdout.splitlines()
        if line.strip()
    }


def get_commit_date(repo_dir, commit):
    r = subprocess.run(
        ["git", "-C", repo_dir, "log", "-1", "--format=%ci", commit],
        capture_output=True, text=True,
    )
    s = r.stdout.strip()
    return s.split()[0] if s else "unknown"


# ── Filter helpers ────────────────────────────────────────────────────────────

def _is_nan(val):
    try:
        return math.isnan(val)
    except (TypeError, ValueError):
        return False


def _safe_str(val):
    return "" if _is_nan(val) else str(val)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Build extra-repo issue pool (youtube-dl, ComfyUI, transformers, core)."
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Process only the first 3 issues per repo; skip checkout/LoC (loc=0).",
    )
    args = ap.parse_args()

    pkl_file = os.path.join(
        _ROOT, "data", "all_issues_with_pr_commit_comment_all_project_0922.pkl"
    )
    with open(pkl_file, "rb") as f:
        all_issues = pd.DataFrame(pickle.load(f))

    output_rows   = []
    summary_lines = []

    def emit(msg):
        print(msg)
        summary_lines.append(msg)

    loc_cache  = {}
    tree_cache = {}
    date_cache = {}

    for repo in REPO_FOLDER:
        repo_dir = os.path.join(_ROOT, REPO_FOLDER[repo])
        pkg_name = PACKAGE_NAME[repo]
        tier     = TIER[repo]

        subset  = all_issues[all_issues["repo_name"] == repo].reset_index(drop=True)
        n_total = len(subset)
        n_usable = 0

        if n_total == 0:
            emit(f"{repo}: 0 usable / 0 total issues  (not found in pickle)")
            continue

        limit = 3 if args.dry_run else n_total

        for idx in range(min(n_total, limit)):
            issue  = subset.iloc[idx]
            commit = issue["base_commit"]
            title  = _safe_str(issue.get("title", ""))
            body   = _safe_str(issue.get("body", "") or "")
            gt_raw = (issue.get("loctype") or {}).get("code") or []
            label  = f"[{repo}:{idx}]"
            key    = (repo, commit)

            # ── Filter 1: non-empty GT, no None entries ───────────────────
            if not gt_raw or any(g is None for g in gt_raw):
                print(f"{label} SKIP reason=empty_or_null_GT")
                continue

            gt_strs = [str(g) for g in gt_raw]

            # ── Filter 3: no absolute paths ───────────────────────────────
            if any(
                g.startswith("/") or (len(g) > 1 and g[1] == ":")
                for g in gt_strs
            ):
                print(f"{label} SKIP reason=absolute_path_in_GT")
                continue

            # ── Source filter + filter 2: at least one .py GT source file ─
            src_files = source_files_only(gt_strs)
            if not any(f.endswith(".py") for f in src_files):
                print(f"{label} SKIP reason=no_py_source_GT")
                continue

            # ── Filter 4: title ───────────────────────────────────────────
            if not title.strip() or not _is_ascii_enough(title):
                print(f"{label} SKIP reason=bad_title")
                continue

            # ── Filter 5: body ────────────────────────────────────────────
            if len(body.strip()) < 20 or not _is_ascii_enough(body):
                print(f"{label} SKIP reason=bad_body")
                continue

            # ── Filter 6: GT files exist at base_commit ───────────────────
            if key not in tree_cache:
                tree_cache[key] = git_ls_tree_all(repo_dir, commit)

            tree_files = tree_cache[key]
            if tree_files is not None:
                missing = [
                    g for g in src_files
                    if g.replace("\\", "/") not in tree_files
                ]
                if missing:
                    print(f"{label} SKIP reason=GT_missing_from_tree({missing[0]})")
                    continue

            # ── Commit date ───────────────────────────────────────────────
            if key not in date_cache:
                date_cache[key] = get_commit_date(repo_dir, commit)
            commit_date = date_cache[key]

            # ── LoC counting ──────────────────────────────────────────────
            if args.dry_run:
                py_loc = 0
            elif key in loc_cache:
                py_loc = loc_cache[key]
            else:
                original_head = current_head(repo_dir)
                error_in_checkout = False
                try:
                    checkout(repo_dir, commit)
                    skip_dirs = set(load_skip_dirs(repo, idx))
                    pkg_dir   = resolve_package_dir(repo_dir, pkg_name)
                    py_loc, _ = count_py_loc(pkg_dir, skip_dirs)
                    loc_cache[key] = py_loc
                except Exception as exc:
                    print(f"{label} SKIP reason=checkout_error({exc})")
                    traceback.print_exc()
                    error_in_checkout = True
                finally:
                    try:
                        restore(repo_dir, original_head)
                    except Exception as restore_exc:
                        print(
                            f"{label} WARNING: failed to restore HEAD to "
                            f"{original_head[:8]} — {restore_exc}"
                        )
                if error_in_checkout:
                    continue
                py_loc = loc_cache[key]

            # ── Passed all filters ────────────────────────────────────────
            n_src     = len(src_files)
            file_type = "single" if n_src == 1 else "multi"

            print(
                f"{label} PASS loc={py_loc:,} commit={commit[:8]} "
                f"date={commit_date} n_gt={n_src} type={file_type}"
            )
            n_usable += 1
            output_rows.append({
                "repo":           repo,
                "tier":           tier,
                "issue_idx":      idx,
                "base_commit":    commit,
                "commit_date":    commit_date,
                "python_loc":     py_loc,
                "n_source_files": n_src,
                "file_type":      file_type,
                "body_len":       len(body),
                "title":          title,
                "source_files":   str(src_files),
            })

        emit(f"{repo}: {n_usable} usable / {n_total} total issues")

    # ── Build output dataframe ────────────────────────────────────────────────
    df = pd.DataFrame(output_rows)

    emit(f"\nTotal usable issues: {len(df)}")

    if len(df) == 0:
        print("No usable issues found — nothing to save.")
        return

    # ── Per-repo summary table ────────────────────────────────────────────────
    emit("\n── Per-repo summary ─────────────────────────────────────────────────────")
    hdr = (f"{'repo':<28} {'tier':<8} {'n':>4}  "
           f"{'loc_min':>8} {'loc_max':>8} {'loc_mean':>9} {'loc_med':>8}  "
           f"{'single':>6} {'multi':>5}")
    emit(hdr)
    emit("-" * len(hdr))

    for repo in REPO_FOLDER:
        rdf = df[df["repo"] == repo]
        if len(rdf) == 0:
            continue
        emit(
            f"{repo:<28} {TIER[repo]:<8} {len(rdf):>4}  "
            f"{rdf['python_loc'].min():>8,.0f} "
            f"{rdf['python_loc'].max():>8,.0f} "
            f"{rdf['python_loc'].mean():>9,.0f} "
            f"{rdf['python_loc'].median():>8,.0f}  "
            f"{(rdf['file_type']=='single').sum():>6} "
            f"{(rdf['file_type']=='multi').sum():>5}"
        )

    # ── LoC distribution ──────────────────────────────────────────────────────
    emit("\n── Overall LoC distribution ─────────────────────────────────────────────")
    emit(df["python_loc"].describe().to_string())

    bins   = [0, 5_000, 20_000, 50_000, 150_000, 300_000, float("inf")]
    labels = ["<5k", "5k-20k", "20k-50k", "50k-150k", "150k-300k", ">300k"]
    df["loc_bin"] = pd.cut(df["python_loc"], bins=bins, labels=labels)
    emit("\nIssue count by LoC range:")
    emit(df["loc_bin"].value_counts().sort_index().to_string())

    # ── Per-tier LoC distribution ─────────────────────────────────────────────
    emit("\n── LoC distribution by tier ─────────────────────────────────────────────")
    for tier in ["small", "medium", "large"]:
        tdf = df[df["tier"] == tier]
        if len(tdf) == 0:
            continue
        emit(f"\n{tier} ({len(tdf)} issues):")
        emit(
            f"  min={tdf['python_loc'].min():,.0f}  "
            f"max={tdf['python_loc'].max():,.0f}  "
            f"mean={tdf['python_loc'].mean():,.0f}  "
            f"median={tdf['python_loc'].median():,.0f}"
        )
        emit(tdf["loc_bin"].value_counts().sort_index().to_string())

    # ── Save outputs ──────────────────────────────────────────────────────────
    out_csv = os.path.join(_ROOT, "data", "issue_pool_extra_repos.csv")
    out_txt = os.path.join(_ROOT, "data", "issue_pool_extra_repos_summary.txt")

    df.drop(columns=["loc_bin"]).to_csv(out_csv, index=False)
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")

    print(f"\nSaved pool:    {out_csv}  ({len(df)} rows)")
    print(f"Saved summary: {out_txt}")


if __name__ == "__main__":
    main()
