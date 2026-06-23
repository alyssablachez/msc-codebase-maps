"""
Compare an AST map and a ctags map, reporting coverage differences.

Usage:
    python3 scripts/compare_maps.py \
        --ast  repo_maps/requests/task_0/ast_map.json \
        --ctags repo_maps/requests/task_0/ctags_map.json
"""
import argparse
import json
import os
from collections import defaultdict


def load_ndjson(path):
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def file_key(path_str):
    """Normalise to bare filename so AST and ctags paths are comparable."""
    return os.path.basename(path_str)


def main():
    parser = argparse.ArgumentParser(description="Compare AST and ctags maps")
    parser.add_argument("--ast", required=True, help="AST NDJSON map file")
    parser.add_argument("--ctags", required=True, help="ctags NDJSON map file")
    args = parser.parse_args()

    ast_records = load_ndjson(args.ast)
    ctags_records = load_ndjson(args.ctags)

    ast_by_file = defaultdict(list)
    for r in ast_records:
        ast_by_file[file_key(r["file"])].append(r)

    ctags_by_file = defaultdict(list)
    for r in ctags_records:
        ctags_by_file[file_key(r["path"])].append(r)

    ast_files = set(ast_by_file)
    ctags_files = set(ctags_by_file)

    only_in_ast = sorted(ast_files - ctags_files)
    only_in_ctags = sorted(ctags_files - ast_files)
    in_both = sorted(ast_files & ctags_files)

    print(f"AST map:   {len(ast_records):>5} records  {len(ast_files)} files  ({args.ast})")
    print(f"ctags map: {len(ctags_records):>5} records  {len(ctags_files)} files  ({args.ctags})")
    print()

    if only_in_ast:
        print(f"Files only in AST ({len(only_in_ast)}):")
        for f in only_in_ast:
            print(f"  {f}  ({len(ast_by_file[f])} records)")
    else:
        print("Files only in AST:   none")

    if only_in_ctags:
        print(f"\nFiles only in ctags ({len(only_in_ctags)}):")
        for f in only_in_ctags:
            print(f"  {f}  ({len(ctags_by_file[f])} records)")
    else:
        print("Files only in ctags: none")

    print(f"\nFiles in both: {len(in_both)}")
    discrepancies = []
    for fname in in_both:
        a = len(ast_by_file[fname])
        c = len(ctags_by_file[fname])
        if max(a, c) == 0:
            continue
        pct_diff = abs(a - c) / max(a, c) * 100
        if pct_diff > 5:
            discrepancies.append((fname, a, c, pct_diff))

    if discrepancies:
        print(f"\nDiscrepancies >5% record count difference ({len(discrepancies)} files):")
        print(f"  {'file':<30} {'ast':>6} {'ctags':>6} {'diff%':>7}")
        print(f"  {'-' * 52}")
        for fname, a, c, pct in sorted(discrepancies, key=lambda x: -x[3]):
            print(f"  {fname:<30} {a:>6} {c:>6} {pct:>6.1f}%")
    else:
        print("\nNo discrepancies >5%. Maps agree closely.")


if __name__ == "__main__":
    main()
