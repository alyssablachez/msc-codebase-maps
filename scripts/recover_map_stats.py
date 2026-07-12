"""
One-off recovery: compute map_generation_stats.csv rows for issues whose
map files already exist on disk (ast_map.json, compact_map.txt,
freq_map.txt, cochange_map.txt), without re-running the expensive
checkout-based generation pipeline.

Used when generate_all_maps.py succeeded at generating maps but crashed
before writing the stats CSV (e.g. the CSV was locked by another program).
n_source_files and LOC are recomputed via `git archive` (fast — reads git
objects directly, no slow working-tree checkout needed on this filesystem).

Usage:
    python3 scripts/recover_map_stats.py core:20 pandas:26
"""
import io
import os
import sys
import tarfile

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from generate_all_maps import (
    REPO_DIR_MAP, PACKAGE_MAP, STATS_CSV, STATS_COLS,
    pkg_tree_path, count_loc, load_skip_dirs, commit_date, file_chars,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def count_source_files(repo_dir, commit, tree_path, skip_dirs):
    """Count .py files under tree_path via git archive, applying the same
    by-name directory skip logic as generate_ast_map.py's os.walk."""
    import subprocess
    cmd = ["git", "-C", repo_dir, "archive", commit]
    if tree_path:
        cmd.append(tree_path + "/")
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        return None
    skip = set(skip_dirs)
    n = 0
    with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith(".py"):
                continue
            parts = member.name.split("/")[:-1]
            if skip & set(parts):
                continue
            n += 1
    return n


def main():
    specs = sys.argv[1:]
    if not specs:
        print("Usage: python3 scripts/recover_map_stats.py repo:idx [repo:idx ...]")
        sys.exit(1)

    sel = pd.read_csv(os.path.join(_ROOT, "data", "issue_selection_final.csv"))
    all_selected_keys = set(zip(sel["repo"], sel["issue_idx"].astype(int)))

    rows = []
    for spec in specs:
        repo, idx_s = spec.rsplit(":", 1)
        issue_idx = int(idx_s)
        sel_row = sel[(sel.repo == repo) & (sel.issue_idx == issue_idx)].iloc[0]
        tier, role = sel_row["tier"], sel_row["role"]
        base_commit, c_date = sel_row["base_commit"], sel_row["commit_date"]

        repo_dir = os.path.join(_ROOT, REPO_DIR_MAP[repo])
        pkg_name = PACKAGE_MAP[repo]
        issue_dir = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx))

        ast_path      = os.path.join(issue_dir, "ast_map.json")
        compact_path  = os.path.join(issue_dir, "compact_map.txt")
        freq_path     = os.path.join(issue_dir, "freq_map.txt")
        cochange_path = os.path.join(issue_dir, "cochange_map.txt")

        with open(ast_path, encoding="utf-8") as f:
            n_ast_records = sum(1 for line in f if line.strip())

        ast_chars     = file_chars(ast_path)
        compact_chars = file_chars(compact_path)
        freq_chars    = file_chars(freq_path)
        cochange_chars = file_chars(cochange_path)

        skip_dirs = load_skip_dirs(repo, issue_idx)
        tree_path = pkg_tree_path(repo_dir, base_commit, pkg_name)
        n_source_files = count_source_files(repo_dir, base_commit, tree_path, skip_dirs)
        python_loc, total_loc = count_loc(repo_dir, base_commit, tree_path)

        stat = {c: None for c in STATS_COLS}
        stat.update({
            "repo": repo, "tier": tier, "issue_idx": issue_idx, "role": role,
            "base_commit": base_commit[:8], "commit_date": c_date,
            "package_dir": os.path.join(repo_dir, tree_path) if tree_path else repo_dir,
            "n_source_files": n_source_files,
            "n_ast_records": n_ast_records,
            "ast_map_chars": ast_chars, "ast_map_tokens": ast_chars // 4,
            "compact_map_chars": compact_chars, "compact_map_tokens": compact_chars // 4,
            "compact_reduction_pct": round((1 - compact_chars / ast_chars) * 100, 1),
            "freq_map_chars": freq_chars, "freq_map_tokens": freq_chars // 4,
            "cochange_map_chars": cochange_chars, "cochange_map_tokens": cochange_chars // 4,
            "python_loc": python_loc, "total_loc": total_loc,
            "status": "success", "error_message": "", "duration_seconds": None,
        })
        rows.append(stat)
        print(f"{repo} issue={issue_idx} ({role}) — recovered stats: "
              f"{n_source_files} files, compact {stat['compact_map_tokens']} tok, "
              f"freq {stat['freq_map_tokens']} tok, cochange {stat['cochange_map_tokens']} tok")

    # Merge into existing stats CSV, same rule as generate_all_maps.py:
    # drop stale rows for issues no longer selected, replace/add these rows.
    new_keys = {(s["repo"], s["issue_idx"]) for s in rows}
    kept_old = []
    if os.path.exists(STATS_CSV):
        import csv
        with open(STATS_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                key = (r["repo"], int(r["issue_idx"]))
                if key in all_selected_keys and key not in new_keys:
                    kept_old.append(r)

    merged = kept_old + rows
    merged.sort(key=lambda r: (r["repo"], int(r["issue_idx"])))

    import csv
    with open(STATS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=STATS_COLS)
        writer.writeheader()
        writer.writerows(merged)

    print(f"\nStats saved -> {STATS_CSV} ({len(merged)} rows)")


if __name__ == "__main__":
    main()
