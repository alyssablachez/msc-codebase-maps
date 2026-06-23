"""
Estimate token count for one or more map files.

Usage:
    python3 scripts/estimate_tokens.py repo_maps/requests/task_0/ast_map.json
    python3 scripts/estimate_tokens.py repo_maps/requests/task_*/ast_map.json
"""
import argparse
import os
import sys

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


def analyse(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    chars = len(content)
    est = chars // 4
    exact = len(_ENC.encode(content)) if HAS_TIKTOKEN else None
    return chars, est, exact


def main():
    parser = argparse.ArgumentParser(description="Estimate token counts for map files")
    parser.add_argument("files", nargs="+", help="NDJSON map files to analyse")
    args = parser.parse_args()

    rows = []
    for path in args.files:
        chars, est, exact = analyse(path)
        rows.append((path, os.path.basename(path), chars, est, exact))
        print(f"{path}")
        print(f"  Characters:        {chars:>10,}")
        print(f"  Estimated tokens:  {est:>10,}")
        if exact is not None:
            print(f"  Exact tokens:      {exact:>10,}")
        print()

    if len(rows) > 1:
        name_w = min(max(len(r[0]) for r in rows), 55)
        header = f"{'file':<{name_w}} {'chars':>12} {'est tokens':>12}"
        if HAS_TIKTOKEN:
            header += f" {'exact tokens':>12}"
        sep = "-" * len(header)
        print(sep)
        print(header)
        print(sep)
        for path, _name, chars, est, exact in rows:
            label = path if len(path) <= name_w else "..." + path[-(name_w - 3):]
            row = f"{label:<{name_w}} {chars:>12,} {est:>12,}"
            if HAS_TIKTOKEN:
                row += f" {exact:>12,}"
            print(row)
        print(sep)


if __name__ == "__main__":
    main()
