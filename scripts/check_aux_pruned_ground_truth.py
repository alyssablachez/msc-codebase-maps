"""
Check whether pruning (scripts/generate_pruned_aux_maps.py) dropped any
ground-truth files out of the pruned frequency map and/or co-change map,
for each issue.

Reads:
    data/issue_selection_final.csv               (ground_truth column)
    repo_maps/pruned_aux_maps_stats[_{N}k].csv    (freq/cochange pruned_files columns)

Writes:
    data/aux_pruned_ground_truth_check[_{N}k].csv

Usage:
    python3 scripts/check_aux_pruned_ground_truth.py --token-budget 55000
"""
import argparse
import ast
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")
DEFAULT_BUDGET = 30_000


def io_paths(budget):
    if budget == DEFAULT_BUDGET:
        stats_csv = os.path.join(_ROOT, "repo_maps", "pruned_aux_maps_stats.csv")
        out_csv   = os.path.join(_ROOT, "data", "aux_pruned_ground_truth_check.csv")
    else:
        suffix = f"_{budget // 1000}k"
        stats_csv = os.path.join(_ROOT, "repo_maps", f"pruned_aux_maps_stats{suffix}.csv")
        out_csv   = os.path.join(_ROOT, "data", f"aux_pruned_ground_truth_check{suffix}.csv")
    return stats_csv, out_csv


def split_files(cell):
    return set(cell.split(";")) if isinstance(cell, str) and cell else set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-budget", type=int, default=DEFAULT_BUDGET)
    args = ap.parse_args()

    STATS_CSV, OUT_CSV = io_paths(args.token_budget)

    issues = pd.read_csv(SEL_CSV)
    aux = pd.read_csv(STATS_CSV).set_index(["repo", "issue_idx"])

    rows = []
    for _, row in issues.iterrows():
        repo, tier, issue_idx, role = row["repo"], row["tier"], int(row["issue_idx"]), row["role"]
        gt_files = ast.literal_eval(row["ground_truth"])

        a = aux.loc[(repo, issue_idx)]
        freq_pruned = split_files(a["freq_pruned_files"])
        cochange_pruned = split_files(a["cochange_pruned_files"])

        gt_pruned_freq = [f for f in gt_files if f in freq_pruned]
        gt_pruned_cochange = [f for f in gt_files if f in cochange_pruned]

        rows.append({
            "repo": repo, "tier": tier, "issue_idx": issue_idx, "role": role,
            "n_gt_files": len(gt_files),
            "ground_truth": ";".join(gt_files),
            "n_gt_pruned_freq": len(gt_pruned_freq),
            "gt_pruned_freq": ";".join(gt_pruned_freq),
            "any_gt_pruned_freq": bool(gt_pruned_freq),
            "n_gt_pruned_cochange": len(gt_pruned_cochange),
            "gt_pruned_cochange": ";".join(gt_pruned_cochange),
            "any_gt_pruned_cochange": bool(gt_pruned_cochange),
        })

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)

    freq_affected = out[out["any_gt_pruned_freq"]]
    cochange_affected = out[out["any_gt_pruned_cochange"]]

    print(f"Issues where a ground-truth file was pruned from the freq map: "
          f"{len(freq_affected)}/{len(out)}")
    if len(freq_affected):
        for _, r in freq_affected.iterrows():
            print(f"  {r['repo']:<15} issue={r['issue_idx']:>3}  {r['role']:<10}  "
                  f"{r['gt_pruned_freq']}")

    print(f"\nIssues where a ground-truth file was pruned from the cochange map: "
          f"{len(cochange_affected)}/{len(out)}")
    if len(cochange_affected):
        for _, r in cochange_affected.iterrows():
            print(f"  {r['repo']:<15} issue={r['issue_idx']:>3}  {r['role']:<10}  "
                  f"{r['gt_pruned_cochange']}")

    print(f"\nSaved -> {OUT_CSV}")


if __name__ == "__main__":
    main()
