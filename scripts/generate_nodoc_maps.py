"""
Generate the no-docstring compact map (compact_map_nodoc.txt) for every
selected issue, from the existing ast_map.json (no AST re-parsing needed).

Writes repo_maps/compact_nodoc_stats.csv with char/token sizes, alongside
the original (with-docstring) compact map sizes for comparison.

Usage:
    python3 scripts/generate_nodoc_maps.py
    python3 scripts/generate_nodoc_maps.py --dry-run
"""
import argparse
import csv
import json
import os

import pandas as pd

import compact_map_nodoc as nodoc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEL_CSV   = os.path.join(_ROOT, "data", "issue_selection_final.csv")
STATS_CSV = os.path.join(_ROOT, "repo_maps", "map_generation_stats.csv")
OUT_CSV   = os.path.join(_ROOT, "repo_maps", "compact_nodoc_stats.csv")

OUT_COLS = [
    "repo", "tier", "issue_idx", "role",
    "compact_chars", "compact_tokens",
    "nodoc_chars", "nodoc_tokens",
    "reduction_vs_original_pct",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    issues = pd.read_csv(SEL_CSV)
    orig_stats = pd.read_csv(STATS_CSV).set_index(["repo", "issue_idx"])

    total = len(issues)
    print(f"Generating no-docstring compact maps for {total} issues")
    if args.dry_run:
        print()

    rows = []
    for enum_i, (_, row) in enumerate(issues.iterrows()):
        repo, tier, issue_idx, role = row["repo"], row["tier"], int(row["issue_idx"]), row["role"]

        out_dir = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx))
        ast_in  = os.path.join(out_dir, "ast_map.json")
        nodoc_out = os.path.join(out_dir, "compact_map_nodoc.txt")

        if args.dry_run:
            print(f"  {repo:<28} issue={issue_idx:>3}  -> {nodoc_out}")
            continue

        records = []
        with open(ast_in, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        content = nodoc.render(records)
        with open(nodoc_out, "w", encoding="utf-8") as f:
            f.write(content)

        nodoc_chars  = len(content)
        nodoc_tokens = nodoc_chars // 4

        orig = orig_stats.loc[(repo, issue_idx)]
        compact_chars  = int(orig["compact_map_chars"])  if pd.notna(orig["compact_map_chars"])  else None
        compact_tokens = int(orig["compact_map_tokens"]) if pd.notna(orig["compact_map_tokens"]) else None
        reduction = (
            round((1 - nodoc_chars / compact_chars) * 100, 1)
            if compact_chars else None
        )

        rows.append({
            "repo": repo, "tier": tier, "issue_idx": issue_idx, "role": role,
            "compact_chars": compact_chars, "compact_tokens": compact_tokens,
            "nodoc_chars": nodoc_chars, "nodoc_tokens": nodoc_tokens,
            "reduction_vs_original_pct": reduction,
        })

        print(f"[{enum_i+1:>2}/{total}] {repo} issue={issue_idx} ({role}) — "
              f"{compact_tokens:>7} -> {nodoc_tokens:>7} tok ({reduction}% smaller)")

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
