"""
Generate an AST-based codebase map for a Python package at a given git commit.

Reads file contents via `git archive` rather than checking out a working
tree -- avoids slow per-file filesystem I/O on this machine (WSL /mnt/c),
where a full checkout of a large repo can take tens of minutes. No working
tree is touched at all.

Files that fail to parse as Python 3 are retried once after a best-effort
patch for common Python 2 syntax (`except X, e:`, `print X` statements,
`123L` long-literal suffixes) rather than being silently dropped -- this
recovers real files (e.g. pandas' own core/frame.py, core/indexing.py at
2013-era commits) that were previously invisible to the compact map with
no warning anywhere in the pipeline.

Usage:
    python3 scripts/generate_ast_map.py \
        --repo repos/requests_full \
        --commit abc1234 \
        --out repo_maps/requests/7/ast_map.json \
        --package-name requests
"""
import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tarfile

# ── Python 2 compatibility patching ─────────────────────────────────────────
# Best-effort fallback only, applied when a file fails to parse as-is.
# Preserves line count/structure so line numbers stay accurate. Not a
# general Python 2->3 translator -- targets exactly the patterns observed
# in this study's older codebases (pandas ~2013, home-assistant ~2017).

_PY2_EXCEPT_COMMA_RE = re.compile(r'^(\s*except\s+)(\(.+?\)|[^,\n(]+?),\s*(\w+)(\s*:)', re.MULTILINE)
_PY2_PRINT_STMT_RE   = re.compile(r'^(\s*)print (?!\()(.+)$', re.MULTILINE)
_PY2_LONG_LITERAL_RE = re.compile(r'\b(\d+)[lL]\b')
_PY2_RAISE_COMMA_RE  = re.compile(r'^(\s*raise\s+)([A-Za-z_][\w.]*)\s*,\s*(.+)$', re.MULTILINE)
_PY2_LEADING_ZERO_RE = re.compile(r'\b0\d+\b')
_PY2_UR_STRING_RE    = re.compile(r'\b[uU]([rR][\'"])')
# `async` became a reserved keyword in Python 3.7 -- home-assistant (~2017)
# had a homeassistant/util/async.py module, used as `from x.async import y`
# / `from .async import y`. Not a Python 2 issue, but the same
# best-effort-rename treatment applies: only affects import paths, so
# renaming doesn't change which classes/functions get extracted.
_ASYNC_KEYWORD_RE    = re.compile(r'\.async\b')


def _strip_leading_zeros(m):
    stripped = m.group(0).lstrip('0')
    return stripped if stripped else '0'


def _py2_compat_patch(source):
    if source.startswith("\ufeff"):
        source = source[1:]
    source = _PY2_EXCEPT_COMMA_RE.sub(r'\1\2 as \3\4', source)
    source = _PY2_PRINT_STMT_RE.sub(lambda m: f'{m.group(1)}print({m.group(2)})', source)
    source = _ASYNC_KEYWORD_RE.sub('.async_', source)
    source = _PY2_RAISE_COMMA_RE.sub(r'\1\2(\3)', source)
    source = _PY2_UR_STRING_RE.sub(r'\1', source)
    source = _PY2_LONG_LITERAL_RE.sub(r'\1', source)
    source = _PY2_LEADING_ZERO_RE.sub(_strip_leading_zeros, source)
    return source


def _parse_source(source, rel_path):
    """Try ast.parse(); on SyntaxError, retry after py2-compat patching.
    Returns the parsed tree, or None (and logs a warning) if both fail."""
    try:
        return ast.parse(source, filename=rel_path)
    except SyntaxError:
        pass
    try:
        return ast.parse(_py2_compat_patch(source), filename=rel_path)
    except SyntaxError as e:
        print(f"WARNING: could not parse {rel_path} even after py2-compat "
              f"patching -- skipped (no records extracted): {e}", file=sys.stderr)
        return None


# ── package dir resolution (git-object based, no checkout) ─────────────────

def pkg_tree_path(repo_dir, commit, pkg_name):
    """Return the git tree path for the package (e.g. 'src/flask', 'requests'),
    or None if neither candidate exists at this commit."""
    for candidate in [f"src/{pkg_name}", pkg_name]:
        r = subprocess.run(
            ["git", "-C", repo_dir, "ls-tree", "--name-only", commit, candidate + "/"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            return candidate
    return None


# ── AST extraction ───────────────────────────────────────────────────────────

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


def extract_records(source, rel_path):
    tree = _parse_source(source, rel_path)
    if tree is None:
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
    parser.add_argument("--commit", required=True, help="Commit SHA")
    parser.add_argument("--out", required=True, help="Output NDJSON file path")
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
    all_records = []

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
            all_records.extend(extract_records(source, member.name))

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record) + "\n")

    char_count = sum(len(json.dumps(r)) + 1 for r in all_records)
    token_estimate = char_count // 4
    print(f"Package dir:       {pkg_dir}")
    print(f"Files walked:      {files_walked}")
    print(f"Records extracted: {len(all_records)}")
    print(f"Character count:   {char_count:,}")
    print(f"Estimated tokens:  {token_estimate:,}")


if __name__ == "__main__":
    main()
