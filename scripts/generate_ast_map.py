"""
Generate an AST-based codebase map for a Python package at a given git commit.

Usage:
    python3 scripts/generate_ast_map.py \
        --repo repos/requests_full \
        --commit abc1234 \
        --out repo_maps/requests/task_0/ast_map.json \
        --package-name requests
"""
import argparse
import ast
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from git_utils import checkout, current_head, restore
from package_resolver import resolve_package_dir


def build_signature(node):
    """Return a readable signature string like '(self, url, params=None, **kwargs)'."""
    args = node.args
    parts = []

    # Positional-only and regular positional args share a single defaults list,
    # aligned to the right: defaults[0] belongs to args[len(args)-len(defaults)].
    all_pos = args.posonlyargs + args.args
    offset = len(all_pos) - len(args.defaults)
    for i, arg in enumerate(all_pos):
        di = i - offset
        if di >= 0:
            parts.append(f"{arg.arg}={ast.unparse(args.defaults[di])}")
        else:
            parts.append(arg.arg)
        # Insert "/" sentinel after positional-only args
        if args.posonlyargs and i == len(args.posonlyargs) - 1:
            parts.append("/")

    # *args (or bare * when there are keyword-only args but no *args)
    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    # Keyword-only args (kw_defaults may be None for args with no default)
    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        if default is not None:
            parts.append(f"{arg.arg}={ast.unparse(default)}")
        else:
            parts.append(arg.arg)

    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

    return "(" + ", ".join(parts) + ")"


def first_docstring_line(node):
    docstring = ast.get_docstring(node)
    if not docstring:
        return None
    for line in docstring.splitlines():
        line = line.strip()
        if line:
            return line
    return None


def extract_file(filepath, rel_path):
    with open(filepath, encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    records = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(ast.unparse(base))
            records.append({
                "type": "class",
                "file": rel_path,
                "name": node.name,
                "line": node.lineno,
                "docstring": first_docstring_line(node),
                "bases": bases,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            records.append({
                "type": "function",
                "file": rel_path,
                "name": node.name,
                "line": node.lineno,
                "signature": build_signature(node),
                "docstring": first_docstring_line(node),
                "class": None,
            })

    records_by_line = {r["line"]: r for r in records if r["type"] == "function"}

    class ParentVisitor(ast.NodeVisitor):
        def __init__(self):
            self.class_stack = []

        def visit_ClassDef(self, node):
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node):
            if node.lineno in records_by_line:
                records_by_line[node.lineno]["class"] = (
                    self.class_stack[-1] if self.class_stack else None
                )
            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef

    ParentVisitor().visit(tree)
    return records


def main():
    parser = argparse.ArgumentParser(description="Generate AST map for a Python package at a given commit")
    parser.add_argument("--repo", required=True, help="Path to the git repository")
    parser.add_argument("--commit", required=True, help="Commit SHA to check out")
    parser.add_argument("--out", required=True, help="Output NDJSON file path")
    parser.add_argument("--package-name", default=None,
                        help="Package directory name to walk. "
                             "Tries src/<name> then <name> at the repo root. "
                             "Auto-detected from top-level __init__.py dirs if omitted.")
    parser.add_argument("--skip-dirs", nargs="+", default=["packages"],
                        help="Subdirectory names to skip while recursing (default: packages).")
    args = parser.parse_args()

    original_head = current_head(args.repo)
    print(f"Checking out {args.commit[:8]} (was {original_head[:8]})")
    checkout(args.repo, args.commit)

    try:
        try:
            pkg_dir = resolve_package_dir(args.repo, args.package_name)
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

        skip = set(args.skip_dirs)
        all_records = []
        for dirpath, dirs, filenames in os.walk(pkg_dir):
            dirs[:] = [d for d in dirs if d not in skip]
            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue
                filepath = os.path.join(dirpath, fname)
                rel_path = os.path.relpath(filepath, args.repo)
                all_records.extend(extract_file(filepath, rel_path))

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for record in all_records:
                f.write(json.dumps(record) + "\n")

        char_count = sum(len(json.dumps(r)) + 1 for r in all_records)
        token_estimate = char_count // 4
        print(f"Wrote {len(all_records)} records to {args.out}")
        print(f"Character count:  {char_count:,}")
        print(f"Estimated tokens: {token_estimate:,}")
    finally:
        print(f"Restoring {original_head[:8]}")
        restore(args.repo, original_head)


if __name__ == "__main__":
    main()
