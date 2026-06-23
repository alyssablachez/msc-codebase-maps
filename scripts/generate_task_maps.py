import ast
import json
import os
import pickle
import subprocess
import sys

import pandas as pd

REPO_DIR = "repos/requests_full"
MAPS_DIR = "repo_maps/requests"

# Both layouts used across commits
SRC_CANDIDATES = [
    os.path.join(REPO_DIR, "src/requests"),  # modern layout
    os.path.join(REPO_DIR, "requests"),       # legacy layout
]
PKL_FILE = "data/all_issues_with_pr_commit_comment_all_project_0922.pkl"
TASK_INDICES = [0, 4, 12, 14, 15]

CTAGS_EXCLUDE = ["tests", "docs"]
CTAGS_FLAGS = [
    "--languages=Python",
    "--python-kinds=cfm",
    "--fields=+S",
    "--output-format=json",
]


# ── AST extraction ────────────────────────────────────────────────────────────

def first_docstring_line(node):
    docstring = ast.get_docstring(node)
    if not docstring:
        return None
    for line in docstring.splitlines():
        line = line.strip()
        if line:
            return line
    return None


def extract_ast_file(filepath, rel_path):
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


def generate_ast_map(out_path):
    src_dir = next((d for d in SRC_CANDIDATES if os.path.isdir(d)), None)
    if src_dir is None:
        print(f"  WARNING: no requests package dir found at this commit, skipping AST map")
        return 0
    rel_base = os.path.relpath(src_dir, REPO_DIR)  # e.g. "requests" or "src/requests"

    all_records = []
    for fname in sorted(os.listdir(src_dir)):
        if not fname.endswith(".py"):
            continue
        filepath = os.path.join(src_dir, fname)
        rel_path = os.path.join(rel_base, fname)
        all_records.extend(extract_ast_file(filepath, rel_path))

    with open(out_path, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record) + "\n")

    char_count = sum(len(json.dumps(r)) + 1 for r in all_records)
    return char_count


# ── ctags ─────────────────────────────────────────────────────────────────────

def generate_ctags_map(out_path):
    exclude_flags = [f"--exclude={d}" for d in CTAGS_EXCLUDE]
    cmd = (
        ["ctags", "--recurse", "-f", "-"]
        + CTAGS_FLAGS
        + exclude_flags
        + [REPO_DIR]
    )
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  WARNING: ctags exited {result.returncode}: {result.stderr.strip()}")

    # ctags --output-format=json emits one JSON object per line; filter parse errors
    lines = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            json.loads(line)
            lines.append(line)
        except json.JSONDecodeError:
            pass

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        if lines:
            f.write("\n")

    return sum(len(l) + 1 for l in lines)


# ── git helpers ───────────────────────────────────────────────────────────────

def git(args, check=True):
    return subprocess.run(
        ["git", "-C", REPO_DIR] + args,
        capture_output=True, text=True, check=check
    )


def current_head():
    return git(["rev-parse", "HEAD"]).stdout.strip()


def checkout(commit):
    git(["checkout", "--detach", commit])


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    with open(PKL_FILE, "rb") as f:
        data = pickle.load(f)
    df = pd.DataFrame(data)
    req = df[df["repo_name"] == "requests"].reset_index(drop=True)

    original_head = current_head()
    print(f"Saved HEAD: {original_head[:8]}\n")

    summary = []

    for idx in TASK_INDICES:
        row = req.iloc[idx]
        base_commit = row["base_commit"]
        task_dir = os.path.join(MAPS_DIR, f"task_{idx}")
        os.makedirs(task_dir, exist_ok=True)

        print(f"── task {idx}  commit {base_commit[:8]} ──")
        checkout(base_commit)

        ast_path = os.path.join(task_dir, "ast_map.json")
        ctags_path = os.path.join(task_dir, "ctags_map.json")

        ast_chars = generate_ast_map(ast_path)
        ctags_chars = generate_ctags_map(ctags_path)

        ast_tokens = ast_chars // 4
        ctags_tokens = ctags_chars // 4

        print(f"  AST:   {ast_chars:>7,} chars  ~{ast_tokens:>6,} tokens  → {ast_path}")
        print(f"  ctags: {ctags_chars:>7,} chars  ~{ctags_tokens:>6,} tokens  → {ctags_path}")

        summary.append({
            "idx": idx,
            "commit": base_commit[:8],
            "ast_tokens": ast_tokens,
            "ctags_tokens": ctags_tokens,
        })

    print(f"\nRestoring HEAD to {original_head[:8]}")
    git(["checkout", original_head])

    # Summary table
    col_w = [6, 10, 12, 14]
    header = f"{'idx':<{col_w[0]}}{'commit':<{col_w[1]}}{'ast tokens':>{col_w[2]}}{'ctags tokens':>{col_w[3]}}"
    sep = "-" * sum(col_w)
    print(f"\n{sep}")
    print(header)
    print(sep)
    for row in summary:
        print(
            f"{row['idx']:<{col_w[0]}}"
            f"{row['commit']:<{col_w[1]}}"
            f"{row['ast_tokens']:>{col_w[2]},}"
            f"{row['ctags_tokens']:>{col_w[3]},}"
        )
    print(sep)


if __name__ == "__main__":
    main()
