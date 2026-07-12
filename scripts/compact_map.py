"""
Convert an AST map NDJSON file into a compact, token-efficient text format
suitable for inclusion in LLM prompts.

Usage:
    python3 scripts/compact_map.py \
        --in repo_maps/requests/task_0/ast_map.json \
        --out repo_maps/requests/task_0/compact_map.txt
"""
import argparse
import json
import os
import re
from collections import defaultdict

MAX_DOC = 200  # safety cap for run-on sentences
INDENT = "  "

# Sentence boundary: punctuation followed by whitespace or end of string.
_SENT_END = re.compile(r'[.!?](?:\s|$)')
# Abbreviations whose trailing period is NOT a sentence end.
_ABBREV = re.compile(
    r'\b(?:e\.g|i\.e|vs|etc|dr|mr|mrs|ms|prof|cf|fig|no|approx)\.$',
    re.IGNORECASE,
)


def _first_sentence(doc):
    """Return the first full sentence, or the full string if none found."""
    for m in _SENT_END.finditer(doc):
        candidate = doc[:m.start() + 1]  # include the punctuation
        if _ABBREV.search(candidate):
            continue
        return candidate
    return doc


def _truncate(doc):
    if not doc:
        return None
    doc = doc.strip()
    sentence = _first_sentence(doc)
    return sentence if len(sentence) <= MAX_DOC else sentence[:MAX_DOC] + "..."


def _class_header(rec):
    bases = rec.get("bases") or []
    if bases:
        return f"class {rec['name']}({', '.join(bases)}) L{rec['line']}"
    return f"class {rec['name']} L{rec['line']}"


def _fn_line(rec, indent=""):
    sig = rec.get("signature") or "()"
    return f"{indent}{rec['name']}{sig} L{rec['line']}"


def _doc_line(rec, indent=""):
    doc = _truncate(rec.get("docstring"))
    if doc is None:
        return None
    return f'{indent}"{doc}"'


def render(records):
    # Group by file
    by_file = defaultdict(lambda: {
        "classes": {},           # name → record
        "methods": defaultdict(list),  # class_name → [records]
        "functions": [],         # module-level
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

    lines = []
    first_file = True

    for filepath in sorted(by_file):
        entry = by_file[filepath]

        if not first_file:
            lines.append("")
        first_file = False

        lines.append(filepath)

        classes = sorted(entry["classes"].values(), key=lambda r: r["line"])
        fns     = sorted(entry["functions"],         key=lambda r: r["line"])

        first_block = True

        for cls in classes:
            if not first_block:
                lines.append("")
            first_block = False

            lines.append(_class_header(cls))
            doc = _doc_line(cls, INDENT)
            if doc:
                lines.append(doc)

            methods = sorted(entry["methods"].get(cls["name"], []), key=lambda r: r["line"])
            for m in methods:
                lines.append(_fn_line(m, INDENT))
                doc = _doc_line(m, INDENT)
                if doc:
                    lines.append(doc)

        if fns:
            if not first_block:
                lines.append("")
            for fn in fns:
                lines.append(_fn_line(fn))
                doc = _doc_line(fn)
                if doc:
                    lines.append(doc)

    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Convert AST NDJSON map to compact text format for LLM prompts"
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
