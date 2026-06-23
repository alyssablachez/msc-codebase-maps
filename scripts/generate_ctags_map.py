"""
Generate a ctags-based codebase map for a Python package at a given git commit.

Resolves the package directory the same way generate_ast_map.py does (via
package_resolver.find_package_dir) and points ctags directly at that directory.
Subdirectories named in --skip-dirs (default: packages) are excluded so vendored
third-party code is not indexed.

Usage:
    python3 scripts/generate_ctags_map.py \
        --repo repos/requests_full \
        --commit abc1234 \
        --out repo_maps/requests/task_0/ctags_map.json \
        --package-name requests
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))
from git_utils import checkout, current_head, restore
from package_resolver import find_package_dir


def main():
    parser = argparse.ArgumentParser(description="Generate ctags map for a Python package at a given commit")
    parser.add_argument("--repo", required=True, help="Path to the git repository")
    parser.add_argument("--commit", required=True, help="Commit SHA to check out")
    parser.add_argument("--out", required=True, help="Output NDJSON file path")
    parser.add_argument("--package-name", default="requests",
                        help="Package directory name to scan (default: requests). "
                             "Tries src/<name> then <name> at the repo root.")
    parser.add_argument("--skip-dirs", nargs="+", default=["packages"],
                        help="Subdirectory names to exclude from ctags (default: packages).")
    args = parser.parse_args()

    original_head = current_head(args.repo)
    print(f"Checking out {args.commit[:8]} (was {original_head[:8]})")
    checkout(args.repo, args.commit)

    try:
        pkg_dir = find_package_dir(args.repo, args.package_name)
        if pkg_dir is None:
            print(
                f"ERROR: could not find {args.package_name}/ or src/{args.package_name}/ "
                f"in {args.repo}",
                file=sys.stderr,
            )
            sys.exit(1)

        exclude_flags = [f"--exclude={d}" for d in args.skip_dirs]
        cmd = (
            ["ctags", "--recurse", "-f", "-",
             "--languages=Python", "--python-kinds=cfm",
             "--fields=+S", "--output-format=json"]
            + exclude_flags
            + [pkg_dir]
        )
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"WARNING: ctags exited {result.returncode}: {result.stderr.strip()}", file=sys.stderr)

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

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")

        char_count = sum(len(l) + 1 for l in lines)
        token_estimate = char_count // 4
        print(f"Wrote {len(lines)} records to {args.out}")
        print(f"Character count:  {char_count:,}")
        print(f"Estimated tokens: {token_estimate:,}")
    finally:
        print(f"Restoring {original_head[:8]}")
        restore(args.repo, original_head)


if __name__ == "__main__":
    main()
