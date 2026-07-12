"""
Generate a 3rd, size-capped compact map (compact_map_pruned.txt) for every
selected issue, built from the no-docstring map (compact_map_nodoc.txt /
compact_map_nodoc.render).

Files are removed one at a time, least-frequently-edited first (per
freq_map.txt for that issue), until the map is under TOKEN_BUDGET tokens.
Equivalently: files are kept in descending edit-frequency order, taking the
largest prefix that fits under budget (at least one file is always kept,
even if it alone exceeds budget).

Kept files are rendered in the pruned map sorted alphabetically, matching
the format of the other map versions.

Writes repo_maps/compact_pruned_stats.csv with before/after sizes and the
list of pruned files per issue.

Usage:
    python3 scripts/generate_pruned_maps.py
    python3 scripts/generate_pruned_maps.py --dry-run
    python3 scripts/generate_pruned_maps.py --token-budget 30000
"""
import argparse
import csv
import json
import os

import pandas as pd

import compact_map_nodoc as nodoc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")

TOKEN_BUDGET = 30_000


def output_names(budget):
    """(pruned_txt_filename, stats_csv_path) for a given token budget.

    30k keeps the original unsuffixed names for backward compatibility;
    other budgets get a `_{N}k` suffix so multiple budgets can coexist.
    """
    if budget == 30_000:
        txt_name = "compact_map_pruned.txt"
        csv_path = os.path.join(_ROOT, "repo_maps", "compact_pruned_stats.csv")
    else:
        suffix = f"{budget // 1000}k"
        txt_name = f"compact_map_pruned_{suffix}.txt"
        csv_path = os.path.join(_ROOT, "repo_maps", f"compact_pruned_stats_{suffix}.csv")
    return txt_name, csv_path

OUT_COLS = [
    "repo", "tier", "issue_idx", "role",
    "n_files_total", "n_files_kept", "n_files_pruned",
    "nodoc_tokens", "pruned_tokens",
    "still_over_budget",
    "pruned_files",
]


def parse_freq_order(freq_path):
    """Return freq_map.txt file order as a list of filepaths, most-edited first."""
    order = []
    with open(freq_path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            # "path/to/file.py  [N edits, last: DATE]"
            filepath = line.split("  [", 1)[0]
            order.append(filepath)
    return order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--token-budget", type=int, default=TOKEN_BUDGET)
    args = ap.parse_args()

    issues = pd.read_csv(SEL_CSV)
    total = len(issues)
    budget = args.token_budget
    pruned_txt_name, OUT_CSV = output_names(budget)

    print(f"Generating pruned (<{budget:,} tok) compact maps for {total} issues")
    if args.dry_run:
        print()

    rows = []
    for enum_i, (_, row) in enumerate(issues.iterrows()):
        repo, tier, issue_idx, role = row["repo"], row["tier"], int(row["issue_idx"]), row["role"]

        issue_dir  = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx))
        ast_in     = os.path.join(issue_dir, "ast_map.json")
        freq_in    = os.path.join(issue_dir, "freq_map.txt")
        pruned_out = os.path.join(issue_dir, pruned_txt_name)

        if args.dry_run:
            print(f"  {repo:<28} issue={issue_idx:>3}  -> {pruned_out}")
            continue

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

        # Files present in the compact map, ordered most-edited -> least-edited
        # (freq_order is already sorted descending by edit count; files with
        # no history entry, if any, fall back to the end).
        present_ordered = sorted(
            files_in_map,
            key=lambda fp: freq_rank.get(fp, len(freq_order)),
        )

        # Greedily keep files in that order while under budget; always keep
        # at least the first (most-edited) file.
        kept_lines = []
        kept_files = []
        for i, fp in enumerate(present_ordered):
            block = nodoc.render_file_block(fp, by_file[fp])
            tentative_lines = kept_lines + ([""] if kept_lines else []) + block
            tentative_tokens = (len("\n".join(tentative_lines)) + 1) // 4
            if tentative_tokens <= budget or i == 0:
                kept_lines = tentative_lines
                kept_files.append(fp)
            else:
                break

        pruned_files = [fp for fp in files_in_map if fp not in set(kept_files)]

        content = nodoc.render(records, files=sorted(kept_files))
        with open(pruned_out, "w", encoding="utf-8") as f:
            f.write(content)

        pruned_tokens = len(content) // 4
        nodoc_content = nodoc.render(records, files=sorted(files_in_map))
        nodoc_tokens = len(nodoc_content) // 4

        rows.append({
            "repo": repo, "tier": tier, "issue_idx": issue_idx, "role": role,
            "n_files_total": len(files_in_map),
            "n_files_kept": len(kept_files),
            "n_files_pruned": len(pruned_files),
            "nodoc_tokens": nodoc_tokens,
            "pruned_tokens": pruned_tokens,
            "still_over_budget": pruned_tokens > budget,
            "pruned_files": ";".join(sorted(pruned_files)),
        })

        flag = "  [STILL OVER BUDGET]" if pruned_tokens > budget else ""
        print(f"[{enum_i+1:>2}/{total}] {repo} issue={issue_idx} ({role}) — "
              f"{nodoc_tokens:>7} -> {pruned_tokens:>7} tok, "
              f"kept {len(kept_files)}/{len(files_in_map)} files{flag}")

    if args.dry_run:
        return

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_COLS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nStats saved -> {OUT_CSV}")


if __name__ == "__main__":
    main()
