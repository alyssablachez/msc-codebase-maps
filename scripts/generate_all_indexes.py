"""
Generate the full, path-indexed AST / edit-frequency / co-change indexes
(ast_index_full.json, freq_index_full.json, cochange_index_full.json) for
all 45 selected issues -- the storage layer for tool-based, on-demand map
retrieval (see DEVLOG 2026-07-14/15). Piloted on 3 issues (core/20,
pandas/26, scikit-learn/45); this regenerates all of them identically for
consistency and extends coverage to the remaining 42.

Mirrors generate_all_maps.py's repo/commit/package-name/skip-dir
resolution (REPO_DIR_MAP, PACKAGE_MAP, data/repo_skip_config.yaml) but
calls the three *_index.py generators instead of the budget-capped ones,
and reads base_commit directly from data/issue_selection_final.csv rather
than the raw issue pickle -- the CSV already carries it per issue.

Usage:
    python3 scripts/generate_all_indexes.py
    python3 scripts/generate_all_indexes.py --dry-run
    python3 scripts/generate_all_indexes.py --only core:20 pandas:26
"""
import argparse
import csv
import os
import subprocess
import sys
import time

import pandas as pd
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repo_config import REPO_DIR_MAP, PACKAGE_MAP

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(_ROOT, "scripts")

SEL_CSV           = os.path.join(_ROOT, "data", "issue_selection_final.csv")
SKIP_CONFIG_YAML  = os.path.join(_ROOT, "data", "repo_skip_config.yaml")
STATS_CSV         = os.path.join(_ROOT, "repo_maps", "index_generation_stats.csv")
STATS_COLS = [
    "repo", "issue_idx", "base_commit",
    "ast_files", "ast_bytes", "freq_files", "freq_bytes",
    "cochange_files", "cochange_bytes",
    "status", "error_message", "duration_seconds",
]


def load_skip_dirs(repo, issue_idx):
    with open(SKIP_CONFIG_YAML, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    defaults = cfg.get("defaults", {}).get("skip_dirs", [])
    key = f"{repo}/{issue_idx}"
    extra = cfg.get("issues", {}).get(key, {}).get("extra_skip_dirs", [])
    return defaults + extra


def run(cmd):
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr, time.time() - t0


def n_keys_and_size(path):
    if not os.path.exists(path):
        return None, None
    size = os.path.getsize(path)
    try:
        import json
        with open(path, encoding="utf-8") as f:
            n = len(json.load(f))
    except (json.JSONDecodeError, OSError):
        n = None
    return n, size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                     help="Print plan without running anything")
    ap.add_argument("--only", nargs="+", default=None,
                     help="Only (re)generate specific issues, e.g. --only core:20 pandas:26")
    args = ap.parse_args()

    issues = pd.read_csv(SEL_CSV)

    if args.only:
        only_keys = set()
        for spec in args.only:
            repo, idx = spec.rsplit(":", 1)
            only_keys.add((repo, int(idx)))
        all_keys = set(zip(issues["repo"], issues["issue_idx"].astype(int)))
        missing = only_keys - all_keys
        if missing:
            print(f"ERROR: not in issue_selection_final.csv: {missing}", file=sys.stderr)
            sys.exit(1)
        issues = issues[
            issues.apply(lambda r: (r["repo"], int(r["issue_idx"])) in only_keys, axis=1)
        ].reset_index(drop=True)

    print(f"Generating full indexes for {len(issues)} issues across "
          f"{issues['repo'].nunique()} repos")

    if args.dry_run:
        for _, row in issues.iterrows():
            repo, issue_idx = row["repo"], int(row["issue_idx"])
            skip = load_skip_dirs(repo, issue_idx)
            print(f"  {repo:<20} issue={issue_idx:>3}  commit={row['base_commit'][:8]}  "
                  f"pkg={PACKAGE_MAP[repo]}  skip=[{', '.join(skip[:4])}"
                  f"{'...' if len(skip) > 4 else ''}]")
        return

    os.makedirs(os.path.dirname(STATS_CSV), exist_ok=True)
    all_stats = []
    t0 = time.time()

    for enum_i, (_, row) in enumerate(issues.iterrows()):
        repo        = row["repo"]
        issue_idx   = int(row["issue_idx"])
        base_commit = row["base_commit"]
        repo_dir    = os.path.join(_ROOT, REPO_DIR_MAP[repo])
        pkg_name    = PACKAGE_MAP[repo]
        skip_dirs   = load_skip_dirs(repo, issue_idx)

        out_dir      = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx))
        ast_out      = os.path.join(out_dir, "ast_index_full.json")
        freq_out     = os.path.join(out_dir, "freq_index_full.json")
        cochange_out = os.path.join(out_dir, "cochange_index_full.json")
        os.makedirs(out_dir, exist_ok=True)

        stat = {c: None for c in STATS_COLS}
        stat.update({"repo": repo, "issue_idx": issue_idx, "base_commit": base_commit[:8]})
        errors = []
        issue_t0 = time.time()

        print(f"[{enum_i + 1}/{len(issues)}] {repo}/{issue_idx} ({base_commit[:8]})...",
              end=" ", flush=True)

        for label, script, out_path, file_key, byte_key in [
            ("ast", "generate_ast_index.py", ast_out, "ast_files", "ast_bytes"),
            ("freq", "generate_freq_index.py", freq_out, "freq_files", "freq_bytes"),
            ("cochange", "generate_cochange_index.py", cochange_out, "cochange_files", "cochange_bytes"),
        ]:
            cmd = [
                sys.executable, os.path.join(SCRIPTS, script),
                "--repo", repo_dir, "--commit", base_commit,
                "--out", out_path, "--package-name", pkg_name,
            ]
            if skip_dirs:
                cmd += ["--skip-dirs"] + skip_dirs
            rc, stdout, stderr, _ = run(cmd)
            if rc != 0:
                errors.append(f"{label} rc={rc}: {stderr.strip()[:300]}")
            else:
                n, size = n_keys_and_size(out_path)
                stat[file_key] = n
                stat[byte_key] = size

        stat["duration_seconds"] = round(time.time() - issue_t0, 1)
        stat["status"] = "failed" if errors else "success"
        stat["error_message"] = "; ".join(errors) if errors else ""
        all_stats.append(stat)

        print("OK" if not errors else f"FAILED ({stat['error_message'][:120]})")

    with open(STATS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=STATS_COLS)
        w.writeheader()
        w.writerows(all_stats)

    n_ok = sum(1 for s in all_stats if s["status"] == "success")
    n_failed = len(all_stats) - n_ok
    print(f"\nDone in {time.time() - t0:.1f}s. {n_ok} succeeded, {n_failed} failed.")
    print(f"Stats -> {STATS_CSV}")
    if n_failed:
        print("\nFailed issues:")
        for s in all_stats:
            if s["status"] == "failed":
                print(f"  {s['repo']}/{s['issue_idx']}: {s['error_message']}")


if __name__ == "__main__":
    main()
