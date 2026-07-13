"""
Regenerate ast_map.json + compact_map.txt (with docstrings) for all 45
selected issues, using the rewritten generate_ast_map.py (git-archive
based, no working-tree checkout; recovers files that previously failed
to parse due to old Python 2 syntax or the `async` reserved-keyword
migration).

Does NOT touch freq_map.txt or cochange_map.txt -- those don't parse file
contents at all, so they're unaffected by this fix and don't need
regenerating.

Updates the AST/compact-related columns of repo_maps/map_generation_stats.csv
in place (n_source_files, n_ast_records, ast_map_chars/tokens,
compact_map_chars/tokens, compact_reduction_pct); freq/cochange columns and
python_loc/total_loc are left untouched.

After this, still need to re-run (unaffected by this script):
    generate_nodoc_maps.py
    generate_pruned_maps.py --token-budget 30000/50000/55000
    check_pruned_ground_truth.py --token-budget 30000/50000/55000
    min_budget_for_gt.py

Usage:
    python3 scripts/regenerate_ast_maps.py
    python3 scripts/regenerate_ast_maps.py --only core:20 pandas:44
"""
import argparse
import csv
import json
import os
import subprocess
import sys
import time

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(_ROOT, "scripts")

sys.path.insert(0, SCRIPTS)
from repo_config import REPO_DIR_MAP, PACKAGE_MAP
from generate_all_maps import STATS_CSV, STATS_COLS, load_skip_dirs

SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")


def run(cmd):
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr, time.time() - start


def _int(text, key):
    for line in text.splitlines():
        if key in line:
            raw = line.split(":", 1)[1].strip().replace(",", "").split()[0]
            try:
                return int(raw)
            except ValueError:
                pass
    return None


def _float(text, key):
    for line in text.splitlines():
        if key in line:
            raw = line.split(":", 1)[1].strip().rstrip("%")
            try:
                return float(raw)
            except ValueError:
                pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", default=None,
                    help="Only regenerate specific issues, e.g. --only core:20 pandas:44")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    issues = pd.read_csv(SEL_CSV)

    if args.only:
        only_keys = set()
        for spec in args.only:
            repo, idx = spec.rsplit(":", 1)
            only_keys.add((repo, int(idx)))
        issues = issues[
            issues.apply(lambda r: (r["repo"], int(r["issue_idx"])) in only_keys, axis=1)
        ].reset_index(drop=True)

    total = len(issues)
    print(f"Regenerating AST + compact maps for {total} issues")

    updates = {}  # (repo, issue_idx) -> updated stats dict

    for enum_i, (_, row) in enumerate(issues.iterrows()):
        repo, issue_idx = row["repo"], int(row["issue_idx"])
        base_commit = row["base_commit"]

        repo_dir = os.path.join(_ROOT, REPO_DIR_MAP[repo])
        pkg_name = PACKAGE_MAP[repo]
        skip_dirs = load_skip_dirs(repo, issue_idx)

        out_dir = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx))
        ast_out = os.path.join(out_dir, "ast_map.json")
        compact_out = os.path.join(out_dir, "compact_map.txt")

        if args.dry_run:
            print(f"  {repo:<28} issue={issue_idx:>3}  commit={base_commit[:8]}  pkg={pkg_name}")
            continue

        stat = {}
        errors = []

        cmd_ast = [
            sys.executable, os.path.join(SCRIPTS, "generate_ast_map.py"),
            "--repo", repo_dir, "--commit", base_commit,
            "--out", ast_out, "--package-name", pkg_name,
        ]
        if skip_dirs:
            cmd_ast += ["--skip-dirs"] + skip_dirs
        rc, stdout, stderr, dt = run(cmd_ast)
        n_warnings = stderr.count("WARNING:")
        if rc != 0:
            errors.append(f"ast_map rc={rc}: {stderr.strip()[:300]}")
        else:
            stat["n_source_files"] = _int(stdout, "Files walked:")
            stat["n_ast_records"]  = _int(stdout, "Records extracted:")
            stat["ast_map_chars"]  = _int(stdout, "Character count:")
            stat["ast_map_tokens"] = _int(stdout, "Estimated tokens:")

        if not errors:
            rc, stdout, stderr, _ = run([
                sys.executable, os.path.join(SCRIPTS, "compact_map.py"),
                "--in", ast_out, "--out", compact_out,
            ])
            if rc != 0:
                errors.append(f"compact_map rc={rc}: {stderr.strip()[:300]}")
            else:
                for line in stdout.splitlines():
                    if line.startswith("Output:"):
                        parts = line.split()
                        try:
                            stat["compact_map_chars"] = int(parts[1].replace(",", ""))
                            if parts[3] == "~":
                                stat["compact_map_tokens"] = int(parts[4].replace(",", ""))
                            else:
                                stat["compact_map_tokens"] = int(parts[3].lstrip("~").replace(",", ""))
                        except (IndexError, ValueError):
                            pass
                stat["compact_reduction_pct"] = _float(stdout, "Reduction:")

        status_tag = "FAILED" if errors else "OK"
        warn_tag = f", {n_warnings} unparseable files" if n_warnings else ""
        print(f"[{enum_i+1:>2}/{total}] {repo} issue={issue_idx} — {status_tag} in {dt:.1f}s"
              f"{warn_tag}")
        for e in errors:
            print(f"  ERROR: {e}")

        if not errors:
            updates[(repo, issue_idx)] = stat

    if args.dry_run:
        return

    # ── merge into map_generation_stats.csv ──────────────────────────────────
    rows = []
    with open(STATS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            key = (r["repo"], int(r["issue_idx"]))
            if key in updates:
                r.update({k: v for k, v in updates[key].items() if v is not None})
            rows.append(r)

    with open(STATS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=STATS_COLS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nUpdated {len(updates)} rows in {STATS_CSV}")


if __name__ == "__main__":
    main()
