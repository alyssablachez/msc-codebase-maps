"""
Generate a path-indexed, FULL co-change index for a Python package at a
given commit -- the tool-based-lookup counterpart to generate_cochange_map.py.

generate_cochange_map.py truncates each file's co-change partner list to
--top-n (default 3) at generation time -- partners beyond that are never
even stored. That cut only makes sense to keep the wholesale-injected map
small; a tool-based lookup pays only for what's queried, so this script
reuses the same commit/file co-occurrence computation unmodified (a true
sum over every commit in history, never sampled) and keeps every partner,
sorted by co-change count descending.

File *enumeration*, however, is changed from the original script: rather
than `git checkout` + `os.walk()` (proven slow on this machine's WSL
/mnt/c mount for large repos -- e.g. ~729s for core/20's 758 files, see
DEVLOG 2026-07-14), this uses `git ls-tree -r` to list files directly from
git's object database, matching the checkout-free approach already used
by generate_ast_map.py/generate_ast_index.py. No working tree is touched.

Output:
    {
      "homeassistant/core.py": [
        {"file": "homeassistant/const.py", "count": 87},
        {"file": "homeassistant/config.py", "count": 42},
        ...
      ],
      ...
    }

Usage:
    python3 scripts/generate_cochange_index.py \
        --repo repos/requests_full \
        --commit abc1234 \
        --out repo_maps/requests/7/cochange_index_full.json \
        --package-name requests
"""
import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from generate_ast_map import pkg_tree_path
from generate_cochange_map import _get_all_commits_and_files


def list_source_files(repo_dir, commit, pkg_dir, skip_dirs):
    """List .py files under pkg_dir at commit via `git ls-tree` (no checkout)."""
    r = subprocess.run(
        ["git", "-C", repo_dir, "ls-tree", "-r", "--name-only", commit, "--", pkg_dir + "/"],
        capture_output=True, text=True, check=True,
    )
    skip = set(skip_dirs)
    files = set()
    for rel_path in r.stdout.splitlines():
        if not rel_path.endswith(".py"):
            continue
        dir_parts = rel_path.split("/")[:-1]
        if skip & set(dir_parts):
            continue
        files.add(rel_path)
    return files


def main():
    parser = argparse.ArgumentParser(
        description="Generate a path-indexed, full co-change index for a Python package")
    parser.add_argument("--repo", required=True, help="Path to the git repository")
    parser.add_argument("--commit", required=True, help="Base commit SHA (history up to this)")
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
    print(f"Package dir: {pkg_dir}")

    source_files = list_source_files(args.repo, args.commit, pkg_dir, args.skip_dirs)
    print(f"Found {len(source_files)} source files; querying git history...")
    file_to_commits, commit_to_files = _get_all_commits_and_files(
        args.repo, args.commit, source_files
    )

    index = {}
    for rel_path in source_files:
        co_counts = defaultdict(int)
        for c in file_to_commits.get(rel_path, []):
            for other in commit_to_files[c]:
                if other != rel_path:
                    co_counts[other] += 1
        partners = sorted(co_counts.items(), key=lambda x: (-x[1], x[0]))
        index[rel_path] = [{"file": f, "count": n} for f, n in partners]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1)

    print(f"Wrote {len(index)} entries to {args.out}")


if __name__ == "__main__":
    main()
