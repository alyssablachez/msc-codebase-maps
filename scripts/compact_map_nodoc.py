"""
Convert an AST map NDJSON file into a compact, token-efficient text format —
identical to scripts/compact_map.py except that docstrings are excluded.

Exposes group_by_file() / render_file_block() / render() so other scripts
(e.g. the frequency-based pruning step) can reuse the same per-file blocks.

Usage:
    python3 scripts/compact_map_nodoc.py \
        --in repo_maps/requests/12/ast_map.json \
        --out repo_maps/requests/12/compact_map_nodoc.txt
"""
import argparse
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from compact_map import _class_header, _fn_line


def group_by_file(records):
    """Group AST records by file: {filepath: {classes, methods, functions}}."""
    by_file = defaultdict(lambda: {
        "classes": {},                  # name → record
        "methods": defaultdict(list),   # class_name → [records]
        "functions": [],                # module-level
    })
    for rec in records:
        f = rec["file"]
        if rec["type"] == "class":
            by_file[f]["classes"][rec["name"]] = rec
        elif rec["type"] == "function":
            cls = rec.get("class")
            if cls:
                by_file[f]["methods"][cls].append(rec)
            else:
                by_file[f]["functions"].append(rec)
    return by_file


def render_file_block(filepath, entry):
    """Render the lines for a single file's block, no docstrings."""
    lines = [filepath]

    classes = sorted(entry["classes"].values(), key=lambda r: r["line"])
    fns     = sorted(entry["functions"],         key=lambda r: r["line"])

    first_block = True

    for cls in classes:
        if not first_block:
            lines.append("")
        first_block = False

        lines.append(_class_header(cls))

        methods = sorted(entry["methods"].get(cls["name"], []), key=lambda r: r["line"])
        for m in methods:
            lines.append(_fn_line(m, "  "))

    if fns:
        if not first_block:
            lines.append("")
        for fn in fns:
            lines.append(_fn_line(fn))

    return lines


def render(records, files=None):
    """
    Render records into compact text format, no docstrings.

    files: optional ordered iterable of filepaths to include (and in what
    order). Defaults to all files present in records, sorted alphabetically.
    """
    by_file = group_by_file(records)
    filepaths = list(files) if files is not None else sorted(by_file)

    lines = []
    first_file = True
    for filepath in filepaths:
        entry = by_file[filepath]
        if not first_file:
            lines.append("")
        first_file = False
        lines.extend(render_file_block(filepath, entry))

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Convert AST NDJSON map to compact text format, no docstrings"
    )
    parser.add_argument("--in",  dest="input", required=True, help="Input NDJSON AST map file")
    parser.add_argument("--out", required=True,               help="Output compact text file")
    args = parser.parse_args()

    records = []
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    content = render(records)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(content)

    in_chars  = os.path.getsize(args.input)
    out_chars = len(content)
    reduction = (1 - out_chars / in_chars) * 100

    print(f"Input:     {in_chars:>9,} chars  ~{in_chars // 4:>6,} tokens")
    print(f"Output:    {out_chars:>9,} chars  ~{out_chars // 4:>6,} tokens")
    print(f"Reduction: {reduction:.1f}%")


if __name__ == "__main__":
    main()
