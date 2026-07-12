"""
Audit codebase sizes across all 45 selected issues.

For each issue, counts Python LOC and total (text-file) LOC at the base commit
in two scopes:

  whole_repo_py_loc   — all tracked .py files in the entire repo
  whole_repo_tot_loc  — all tracked text files in the entire repo
  pkg_py_loc          — .py files inside the source package dir only
  pkg_tot_loc         — text files inside the source package dir only

pkg_* columns match what is already in map_generation_stats.csv.

The aim is to check whether tier labels (small / medium / large) are
consistent with actual codebase size.

Usage:
    python3 scripts/audit_codebase_sizes.py
    python3 scripts/audit_codebase_sizes.py --per-issue   # show all 45 rows
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
    for candidate in [f"src/{pkg_name}", pkg_name]:
        r = subprocess.run(
            ["git", "-C", repo_dir, "ls-tree", "--name-only", commit, candidate + "/"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            return candidate
    return ""


def loc_from_archive(repo_dir, commit, tree_path=None):
    """
    Return (python_loc, total_loc) via git archive at commit.
    tree_path=None means the whole repo.
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
                content = f.read()
                if b"\x00" in content[:1024]:   # skip binaries
                    continue
                lines = content.count(b"\n")
                total_loc += lines
                if member.name.endswith(".py"):
                    python_loc += lines
    except Exception:
        return None, None
    return python_loc, total_loc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-issue", action="store_true",
                    help="Print all 45 rows instead of per-repo summary")
    args = ap.parse_args()

    stats = pd.read_csv(os.path.join(_ROOT, "repo_maps", "map_generation_stats.csv"))

    rows = []
    seen = {}   # (repo, commit) -> (whole_py, whole_tot) to avoid recomputing

    for _, stat in stats.iterrows():
        repo     = stat["repo"]
        idx      = int(stat["issue_idx"])
        commit   = stat["base_commit"]
        tier     = stat["tier"]
        role     = stat["role"]
        repo_dir = os.path.join(_ROOT, REPO_FOLDER[repo])
        pkg_name = PACKAGE_NAME[repo]

        pkg_path = pkg_tree_path(repo_dir, commit, pkg_name)

        # Whole-repo LOC (cached per commit to avoid double work)
        cache_key = (repo, commit)
        if cache_key not in seen:
            print(f"  {repo}/{idx} @{commit} whole-repo ...", flush=True)
            w_py, w_tot = loc_from_archive(repo_dir, commit, tree_path=None)
            seen[cache_key] = (w_py, w_tot)
        else:
            w_py, w_tot = seen[cache_key]

        # Package-dir LOC
        p_py  = int(stat["python_loc"])  if pd.notna(stat["python_loc"])  else None
        p_tot = int(stat["total_loc"])   if pd.notna(stat["total_loc"])   else None

        rows.append({
            "repo":             repo,
            "tier":             tier,
            "issue_idx":        idx,
            "role":             role,
            "commit":           commit,
            "pkg_path":         pkg_path or "(root)",
            "whole_repo_py":    w_py,
            "whole_repo_tot":   w_tot,
            "pkg_py":           p_py,
            "pkg_tot":          p_tot,
            "pkg_pct_of_repo":  round(p_py / w_py * 100, 1) if (p_py and w_py) else None,
        })

    df = pd.DataFrame(rows)

    if args.per_issue:
        pd.set_option("display.max_rows", 100)
        pd.set_option("display.width", 140)
        pd.set_option("display.float_format", "{:,.0f}".format)
        print(df[["repo","tier","issue_idx","role","pkg_path",
                   "whole_repo_py","whole_repo_tot","pkg_py","pkg_tot",
                   "pkg_pct_of_repo"]].to_string(index=False))
        return

    # ── Per-repo summary (mean across 3 issues) ──────────────────────────────
    summary = (
        df.groupby(["repo", "tier"])
          .agg(
              whole_repo_py  = ("whole_repo_py",  "mean"),
              whole_repo_tot = ("whole_repo_tot", "mean"),
              pkg_py         = ("pkg_py",         "mean"),
              pkg_pct        = ("pkg_pct_of_repo","mean"),
          )
          .reset_index()
          .sort_values("whole_repo_py")
    )

    print(f"\n{'repo':<28} {'tier':<8}  {'whole_repo_py':>13}  {'whole_repo_tot':>14}  "
          f"{'pkg_py':>10}  {'pkg%':>5}")
    print("-" * 84)
    for _, r in summary.iterrows():
        print(f"{r['repo']:<28} {r['tier']:<8}  "
              f"{r['whole_repo_py']:>13,.0f}  "
              f"{r['whole_repo_tot']:>14,.0f}  "
              f"{r['pkg_py']:>10,.0f}  "
              f"{r['pkg_pct']:>4.0f}%")


if __name__ == "__main__":
    main()
