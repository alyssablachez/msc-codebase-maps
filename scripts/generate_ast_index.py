"""
Generate a path-indexed, FULL-detail AST index for a Python package at a
given git commit -- the tool-based-lookup counterpart to generate_ast_map.py.

generate_ast_map.py exists to feed the wholesale-injection pipeline under a
fixed token budget, and truncates every docstring to its first non-empty
line at extraction time (see first_docstring_line() there). That truncation
only makes sense when the whole map is being paid for in context regardless
of which files a model actually looks at -- it doesn't apply here, since a
tool-based lookup only costs tokens for files actually queried. This script
reuses generate_ast_map.py's parsing/signature helpers unmodified and keeps
the FULL docstring per class/function instead.

Output is JSON keyed by file path (not NDJSON), one entry per .py file
walked -- including files with no classes/functions (empty lists), so a
lookup for any known file path returns a hit rather than a silent miss:
    {
      "homeassistant/core.py": {
        "classes": [{"name": ..., "line": ..., "docstring": ..., "bases": [...]}],
        "functions": [{"name": ..., "line": ..., "signature": ..., "docstring": ..., "class": ...}]
      },
      ...
    }

Usage:
    python3 scripts/generate_ast_index.py \
        --repo repos/requests_full \
        --commit abc1234 \
        --out repo_maps/requests/7/ast_index_full.json \
        --package-name requests
"""
import argparse
import ast
import io
import json
import os
import subprocess
import sys
import tarfile

sys.path.insert(0, os.path.dirname(__file__))
from generate_ast_map import _parse_source, build_signature, pkg_tree_path


def extract_records_full(source, rel_path):
    """Same walk as generate_ast_map.extract_records(), but keeps the FULL
    docstring (ast.get_docstring's default cleandoc'd text) instead of
    truncating to the first non-empty line."""
    tree = _parse_source(source, rel_path)
    if tree is None:
        return [], []

    classes, functions = [], []
    func_by_line = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(ast.unparse(base))
            classes.append({
                "name": node.name,
                "line": node.lineno,
                "docstring": ast.get_docstring(node),
                "bases": bases,
            })
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rec = {
                "name": node.name,
                "line": node.lineno,
                "signature": build_signature(node),
                "docstring": ast.get_docstring(node),
                "class": None,
            }
            functions.append(rec)
            func_by_line[node.lineno] = rec

    class ParentVisitor(ast.NodeVisitor):
        def __init__(self):
            self.class_stack = []

        def visit_ClassDef(self, node):
            self.class_stack.append(node.name)
            self.generic_visit(node)
            self.class_stack.pop()

        def visit_FunctionDef(self, node):
            if node.lineno in func_by_line:
                func_by_line[node.lineno]["class"] = (
                    self.class_stack[-1] if self.class_stack else None
                )
            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef

    ParentVisitor().visit(tree)
    return classes, functions


def main():
    parser = argparse.ArgumentParser(
        description="Generate a full, path-indexed AST index for a Python package at a given commit")
    parser.add_argument("--repo", required=True, help="Path to the git repository")
    parser.add_argument("--commit", required=True, help="Commit SHA")
    parser.add_argument("--out", required=True, help="Output JSON file path")
    parser.add_argument("--package-name", required=True,
                        help="Package directory name. Tries src/<name> then <name> "
                             "at the repo root via `git ls-tree` (no checkout needed).")
    parser.add_argument("--skip-dirs", nargs="+", default=[],
                        help="Subdirectory names to skip while recursing (default: none).")
    args = parser.parse_args()

    pkg_dir = pkg_tree_path(args.repo, args.commit, args.package_name)
    if pkg_dir is None:
        print(f"ERROR: no package directory found for '{args.package_name}' "
              f"at {args.commit[:8]} (tried src/{args.package_name}/ and "
              f"{args.package_name}/)", file=sys.stderr)
        sys.exit(1)

    archive = subprocess.run(
        ["git", "-C", args.repo, "archive", args.commit, pkg_dir + "/"],
        capture_output=True,
    )
    if archive.returncode != 0:
        print(f"ERROR: git archive failed: {archive.stderr.decode(errors='replace')}",
              file=sys.stderr)
        sys.exit(1)

    skip = set(args.skip_dirs)
    files_walked = 0
    index = {}

    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        py_members = sorted(
            (m for m in tar.getmembers() if m.isfile() and m.name.endswith(".py")),
            key=lambda m: m.name,
        )
        for member in py_members:
            dir_parts = member.name.split("/")[:-1]
            if skip & set(dir_parts):
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            source = f.read().decode("utf-8", errors="replace")
            files_walked += 1
            classes, functions = extract_records_full(source, member.name)
            index[member.name] = {"classes": classes, "functions": functions}

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)

    n_records = sum(len(v["classes"]) + len(v["functions"]) for v in index.values())
    char_count = os.path.getsize(args.out)
    print(f"Package dir:       {pkg_dir}")
    print(f"Files walked:      {files_walked}")
    print(f"Files indexed:     {len(index)}")
    print(f"Records extracted: {n_records}")
    print(f"Character count:   {char_count:,}")
    print(f"Estimated tokens:  {char_count // 4:,}")


if __name__ == "__main__":
    main()
