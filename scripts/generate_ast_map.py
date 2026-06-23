import ast
import json
import os

SRC_DIR = "repos/requests_full/src/requests"
OUT_FILE = "repo_maps/requests/requests_ast_map.json"


def first_docstring_line(node):
    """Return the first non-empty line of a node's docstring, or None."""
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
        if isinstance(node, (ast.ClassDef,)):
            bases = []
            for base in node.bases:
                if isinstance(base, ast.Name):
                    bases.append(base.id)
                elif isinstance(base, ast.Attribute):
                    bases.append(f"{ast.unparse(base)}")

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
                "class": None,  # filled in below via a second pass
            })

    # Second pass: assign class membership using parent tracking
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
    all_records = []

    for fname in sorted(os.listdir(SRC_DIR)):
        if not fname.endswith(".py"):
            continue
        filepath = os.path.join(SRC_DIR, fname)
        rel_path = os.path.join("src/requests", fname)
        all_records.extend(extract_file(filepath, rel_path))

    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        for record in all_records:
            f.write(json.dumps(record) + "\n")

    char_count = sum(len(json.dumps(r)) + 1 for r in all_records)
    token_estimate = char_count // 4

    print(f"Wrote {len(all_records)} records to {OUT_FILE}")
    print(f"Character count: {char_count:,}")
    print(f"Estimated tokens: {token_estimate:,}")


if __name__ == "__main__":
    main()
