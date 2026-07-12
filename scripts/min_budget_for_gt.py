"""
For every selected issue, compute the minimum token budget (using the same
frequency-based, most-edited-first pruning as generate_pruned_maps.py) that
would keep at least one ground-truth file in the pruned compact map.

Since pruning always keeps a prefix of the files ordered by descending edit
frequency, the minimum budget to retain >=1 ground-truth file is simply the
cumulative token size of the map up to and including the *first* (most
frequently edited) ground-truth file in that ordering.

Writes data/min_budget_for_gt.csv.

Usage:
    python3 scripts/min_budget_for_gt.py
"""
import ast
import json
import os

import pandas as pd

import compact_map_nodoc as nodoc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")
OUT_CSV = os.path.join(_ROOT, "data", "min_budget_for_gt.csv")


def parse_freq_order(freq_path):
    order = []
    with open(freq_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            order.append(line.split("  [", 1)[0])
    return order


def main():
    issues = pd.read_csv(SEL_CSV)
    total = len(issues)
    rows = []

    for _, row in issues.iterrows():
        repo, tier, issue_idx, role = row["repo"], row["tier"], int(row["issue_idx"]), row["role"]
        gt_files = ast.literal_eval(row["ground_truth"])

        issue_dir = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx))
        ast_in    = os.path.join(issue_dir, "ast_map.json")
        freq_in   = os.path.join(issue_dir, "freq_map.txt")

        records = []
        with open(ast_in, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        by_file = nodoc.group_by_file(records)
        files_in_map = set(by_file)

        freq_order = parse_freq_order(freq_in)
        freq_rank = {fp: i for i, fp in enumerate(freq_order)}

        present_ordered = sorted(
            files_in_map,
            key=lambda fp: freq_rank.get(fp, len(freq_order)),
        )

        gt_in_map = [f for f in gt_files if f in files_in_map]
        gt_missing_from_map = [f for f in gt_files if f not in files_in_map]

        if not gt_in_map:
            rows.append({
                "repo": repo, "tier": tier, "issue_idx": issue_idx, "role": role,
                "n_gt_files": len(gt_files),
                "gt_in_map": 0,
                "gt_missing_from_map": ";".join(gt_missing_from_map),
                "first_gt_file_reached": None,
                "rank_of_first_gt_file": None,
                "min_tokens_for_one_gt": None,
                "min_files_kept_for_one_gt": None,
                "nodoc_tokens_full_map": None,
            })
            print(f"{repo:<15} issue={issue_idx:>3} ({role}) — "
                  f"NO ground-truth file present in the map at all "
                  f"({len(gt_missing_from_map)} missing)")
            continue

        # Walk the frequency-descending order, accumulating cumulative token
        # size, and stop at the first ground-truth file encountered.
        kept_lines = []
        cumulative_tokens = None
        n_kept = None
        first_gt = None
        for i, fp in enumerate(present_ordered):
            block = nodoc.render_file_block(fp, by_file[fp])
            kept_lines = kept_lines + ([""] if kept_lines else []) + block
            if fp in gt_in_map:
                cumulative_tokens = (len("\n".join(kept_lines)) + 1) // 4
                n_kept = i + 1
                first_gt = fp
                break

        full_content = nodoc.render(records, files=sorted(files_in_map))
        full_tokens = len(full_content) // 4

        rows.append({
            "repo": repo, "tier": tier, "issue_idx": issue_idx, "role": role,
            "n_gt_files": len(gt_files),
            "gt_in_map": len(gt_in_map),
            "gt_missing_from_map": ";".join(gt_missing_from_map),
            "first_gt_file_reached": first_gt,
            "rank_of_first_gt_file": n_kept,
            "min_tokens_for_one_gt": cumulative_tokens,
            "min_files_kept_for_one_gt": n_kept,
            "nodoc_tokens_full_map": full_tokens,
        })

        print(f"{repo:<15} issue={issue_idx:>3} ({role}) — "
              f"need {cumulative_tokens:>7} tok / {n_kept:>4} files "
              f"(full map = {full_tokens:>7} tok) to reach '{first_gt}'")

    out = pd.DataFrame(rows)
    out.to_csv(OUT_CSV, index=False)

    print(f"\nSaved -> {OUT_CSV}")
    print(f"\nMax min_tokens_for_one_gt across all {total} issues: "
          f"{out['min_tokens_for_one_gt'].max():,.0f}")
    print(out.sort_values('min_tokens_for_one_gt', ascending=False)
             [['repo','issue_idx','role','min_tokens_for_one_gt','nodoc_tokens_full_map']]
             .head(10).to_string(index=False))


if __name__ == "__main__":
    main()
