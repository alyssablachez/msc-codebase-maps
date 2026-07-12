"""
Check whether pruning (scripts/generate_pruned_maps.py) dropped any
ground-truth files out of the pruned compact map for each issue.

Reads:
    data/issue_selection_final.csv                  (ground_truth column)
    repo_maps/compact_pruned_stats[_{N}k].csv        (pruned_files column)

Writes:
    data/pruned_ground_truth_check[_{N}k].csv

Usage:
    python3 scripts/check_pruned_ground_truth.py
    python3 scripts/check_pruned_ground_truth.py --token-budget 50000
"""
import argparse
import ast
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")


def io_paths(budget):
    """(pruned_stats_csv, out_csv) for a given token budget, matching the
    naming convention in generate_pruned_maps.py's output_names()."""
    if budget == 30_000:
        pruned_csv = os.path.join(_ROOT, "repo_maps", "compact_pruned_stats.csv")
        out_csv    = os.path.join(_ROOT, "data", "pruned_ground_truth_check.csv")
    else:
        suffix = f"{budget // 1000}k"
        pruned_csv = os.path.join(_ROOT, "repo_maps", f"compact_pruned_stats_{suffix}.csv")
        out_csv    = os.path.join(_ROOT, "data", f"pruned_ground_truth_check_{suffix}.csv")
    return pruned_csv, out_csv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-budget", type=int, default=30_000)
    args = ap.parse_args()

    PRUNED_CSV, OUT_CSV = io_paths(args.token_budget)

    issues = pd.read_csv(SEL_CSV)
    pruned = pd.read_csv(PRUNED_CSV).set_index(["repo", "issue_idx"])

    rows = []
    for _, row in issues.iterrows():
        repo, tier, issue_idx, role = row["repo"], row["tier"], int(row["issue_idx"]), row["role"]
        gt_files = ast.literal_eval(row["ground_truth"])

        p = pruned.loc[(repo, issue_idx)]
        pruned_files = set(p["pruned_files"].split(";")) if pd.notna(p["pruned_files"]) and p["pruned_files"] else set()

        gt_pruned = [f for f in gt_files if f in pruned_files]

        rows.append({
            "repo": repo, "tier": tier, "issue_idx": issue_idx, "role": role,
            "n_gt_files": len(gt_files),
            "ground_truth": ";".join(gt_files),
            "n_gt_files_pruned": len(gt_pruned),
            "gt_files_pruned": ";".join(gt_pruned),
            "any_gt_pruned": bool(gt_pruned),
            "n_files_pruned_total": int(p["n_files_pruned"]),
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)

    affected = out[out["any_gt_pruned"]]
    n_pruned_issues = (out["n_files_pruned_total"] > 0).sum()

    print(f"Issues with any pruning applied: {n_pruned_issues}/{len(out)}")
    print(f"Issues where a ground-truth file was pruned away: {len(affected)}/{len(out)}\n")

    if len(affected):
        print(f"{'repo':<15} {'issue_idx':>9}  {'role':<10}  gt_files_pruned")
        print("-" * 70)
        for _, r in affected.iterrows():
            print(f"{r['repo']:<15} {r['issue_idx']:>9}  {r['role']:<10}  {r['gt_files_pruned']}")

    print(f"\nSaved -> {OUT_CSV}")


if __name__ == "__main__":
    main()
