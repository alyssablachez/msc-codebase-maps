"""
Audit per-issue directory structure at each base commit and produce
data/repo_skip_config.yaml with per-issue skip_dirs lists.

For each of the 45 issues, checks which vendored/non-source directories
actually exist at the specific base commit, so the config is exact.

Usage:
    python3 scripts/generate_skip_config.py
    python3 scripts/generate_skip_config.py --dry-run   # print only, no write
"""
import argparse
import ast as pyast
import os
import pickle
import subprocess
import sys

import pandas as pd
import yaml

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

# Dirs to always skip regardless of repo (applies inside the package walk).
# Tests/docs/examples nested inside a package dir are safe to exclude — GT
# files are never in those dirs for any of the 45 selected issues.
ALWAYS_SKIP = [
    "__pycache__",
    "build", "dist", ".eggs", ".tox",
    "venv", ".venv", "env", "site-packages",
    "tests", "test", "testing",
    "docs", "doc", "documentation",
    "examples", "example",
    "benchmarks", "benchmark",
    "scripts",   # only hits for gpt-engineer/32 flat walk; maintenance script
]

# Per-repo candidate dirs to check: only add to skip if they exist at the
# specific commit.  Tuple: (dir_name_inside_package, reason_comment).
# Check is performed by git ls-tree at the package level.
CANDIDATE_EXTRA = {
    "requests": [
        ("packages", "vendored urllib3/chardet/poster at early commits"),
    ],
    "scrapy": [
        ("xlib", "vendored pydispatch + Twisted compat (only at old commits)"),
    ],
    "scikit-learn": [
        ("externals",     "bundled joblib + six (vendored, despite some edits)"),
        ("__check_build", "build self-test scaffolding"),
        ("_build_utils",  "build helpers (only at newer commits)"),
    ],
    "open-interpreter": [
        ("archive", "old pre-refactor code, added in one commit, never updated"),
    ],
    "stable-diffusion-webui": [
        ("codeformer", "CodeFormer arch files from external research project"),
    ],
}


def git_ls_tree_dirs(repo_dir, commit, path=""):
    """Return list of directory names directly under `path` at `commit`."""
    cmd = ["git", "-C", repo_dir, "ls-tree", "-d", "--name-only", commit]
    if path:
        cmd.append(path.rstrip("/") + "/")
    r = subprocess.run(cmd, capture_output=True, text=True)
    lines = []
    prefix = (path.rstrip("/") + "/") if path else ""
    for line in r.stdout.splitlines():
        line = line.strip()
        if line:
            # strip the leading path prefix git sometimes includes
            name = line[len(prefix):] if line.startswith(prefix) else line
            # take only the first component (direct child)
            parts = name.split("/")
            if parts:
                lines.append(parts[0])
    return lines


def package_subdir_path(repo, pkg_name, repo_dir, commit):
    """
    Return the git tree path to query for package subdirs.
    For src/ layout repos, may need to check src/<pkg>/ instead of <pkg>/.
    Falls back to empty string (repo root) if package not found — this
    handles gpt-engineer/32 flat-structure commits.
    """
    # Check src/<pkg> first
    r = subprocess.run(
        ["git", "-C", repo_dir, "ls-tree", "--name-only", commit, f"src/{pkg_name}/"],
        capture_output=True, text=True
    )
    if r.returncode == 0 and r.stdout.strip():
        return f"src/{pkg_name}"
    # Then <pkg>
    r = subprocess.run(
        ["git", "-C", repo_dir, "ls-tree", "--name-only", commit, f"{pkg_name}/"],
        capture_output=True, text=True
    )
    if r.returncode == 0 and r.stdout.strip():
        return pkg_name
    # Flat structure: fall back to repo root
    return ""


def parse_gt(gt_str):
    try:
        val = pyast.literal_eval(str(gt_str))
        return val if isinstance(val, list) else [str(val)]
    except Exception:
        return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sel_csv  = os.path.join(_ROOT, "data", "issue_selection_random.csv")
    pkl_file = os.path.join(_ROOT, "data",
                            "all_issues_with_pr_commit_comment_all_project_0922.pkl")
    out_yaml = os.path.join(_ROOT, "data", "repo_skip_config.yaml")

    sel = pd.read_csv(sel_csv)
    with open(pkl_file, "rb") as f:
        pkl_df = pd.DataFrame(pickle.load(f))

    issue_configs = {}   # "repo/idx" -> {commit, skip_dirs, notes}

    for _, row in sel.iterrows():
        repo      = row["repo"]
        idx       = int(row["issue_idx"])
        gt_files  = parse_gt(row["ground_truth"])
        repo_dir  = os.path.join(_ROOT, REPO_FOLDER[repo])
        pkg_name  = PACKAGE_NAME[repo]

        subset  = pkl_df[pkl_df["repo_name"] == repo].reset_index(drop=True)
        commit  = subset.iloc[idx]["base_commit"]
        sha8    = commit[:8]

        key = f"{repo}/{idx}"
        print(f"\n{'─'*60}")
        print(f"  {key}  @{sha8}")

        # Find package path in tree
        pkg_path = package_subdir_path(repo, pkg_name, repo_dir, commit)
        if pkg_path:
            print(f"  Package path: {pkg_path}/")
        else:
            print(f"  Package path: (repo root — flat structure)")

        # Get package-level subdirs at this commit
        pkg_subdirs = git_ls_tree_dirs(repo_dir, commit, pkg_path)
        print(f"  Package subdirs: {sorted(pkg_subdirs)}")

        # Check which candidate extra dirs exist
        candidates = CANDIDATE_EXTRA.get(repo, [])
        extra_skip = []
        notes = []
        for dir_name, reason in candidates:
            if dir_name in pkg_subdirs:
                extra_skip.append(dir_name)
                notes.append(f"{dir_name}: {reason}")
                print(f"  ✓ SKIP {dir_name}/  ({reason})")
            else:
                print(f"  — not present: {dir_name}/")

        # GT safety check: make sure no GT file is under an always-skip or extra-skip dir
        all_skip = set(ALWAYS_SKIP) | set(extra_skip)
        for gt in gt_files:
            parts = gt.replace("\\", "/").split("/")
            for i, part in enumerate(parts[:-1]):  # all dir components
                if part in all_skip:
                    print(f"  ⚠ WARNING: GT file {gt!r} is inside skipped dir {part!r}")

        issue_configs[key] = {
            "commit": sha8,
            "skip_dirs": ALWAYS_SKIP + extra_skip,
        }
        if notes:
            issue_configs[key]["notes"] = notes

    # Build YAML structure
    doc = {
        "defaults": {
            "skip_dirs": ALWAYS_SKIP,
        },
        "issues": {
            k: {
                "commit": v["commit"],
                "extra_skip_dirs": [d for d in v["skip_dirs"] if d not in ALWAYS_SKIP],
                **({"notes": v["notes"]} if v.get("notes") else {}),
            }
            for k, v in issue_configs.items()
        }
    }

    print(f"\n{'='*60}")
    print("YAML OUTPUT")
    print(f"{'='*60}")
    yaml_str = yaml.dump(doc, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(yaml_str)

    if not args.dry_run:
        with open(out_yaml, "w", encoding="utf-8") as f:
            f.write(
                "# data/repo_skip_config.yaml\n"
                "#\n"
                "# Per-issue skip configuration for AST/freq/co-change map generation.\n"
                "# Generated by scripts/generate_skip_config.py\n"
                "#\n"
                "# defaults.skip_dirs      — applied to every issue\n"
                "# issues.<repo>/<idx>.extra_skip_dirs — additional dirs that exist\n"
                "#                           at this specific base commit and should\n"
                "#                           be excluded (vendored / build scaffolding)\n"
                "#\n"
                "# Effective skip_dirs = defaults.skip_dirs + extra_skip_dirs\n"
                "#\n"
                "# Skip-dir matching is by directory NAME (not path), so 'tests' skips\n"
                "# any subdirectory named 'tests' anywhere inside the package walk.\n"
                "\n"
            )
            f.write(yaml_str)
        print(f"\nWrote {out_yaml}")
    else:
        print("\n(dry-run — not written)")


if __name__ == "__main__":
    main()
