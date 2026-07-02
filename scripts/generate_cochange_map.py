"""
Generate a co-change map for a Python package at a given commit.

For each source file, reports which other source files most frequently appear
in the same commit (up to and including base_commit).

Usage:
    python3 scripts/generate_cochange_map.py \
        --repo repos/requests_full \
        --commit abc1234 \
        --out repo_maps/requests/task_0/cochange_map.txt \
        --package-name requests \
        --top-n 3
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from git_utils import checkout, current_head, git, restore
from package_resolver import resolve_package_dir


def _get_commits_for_file(repo_dir, base_commit, rel_path):
    result = git(repo_dir, ["log", "--format=%H", base_commit, "--", rel_path])
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(
        description="Generate co-change map for a Python package"
    )
    parser.add_argument("--repo", required=True, help="Path to the git repository")
    parser.add_argument("--commit", required=True, help="Base commit SHA (history up to this)")
    parser.add_argument("--out", required=True, help="Output text file path")
    parser.add_argument("--package-name", default=None,
                        help="Package name (auto-detected if omitted)")
    parser.add_argument("--top-n", type=int, default=3,
                        help="Number of top co-change partners to show per file (default: 3)")
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

        print(f"Package dir: {pkg_dir}")

        source_files = set()
        for dirpath, dirs, filenames in os.walk(pkg_dir):
            for fname in sorted(filenames):
                if fname.endswith(".py"):
                    filepath = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(filepath, args.repo)
                    source_files.add(rel_path)

        print(f"Found {len(source_files)} source files; querying git history...")

        # Build commit → {source files changed} by querying each file's history.
        # Because we query every source file, commit_to_files will be complete:
        # if commit C touched source files A and B, both queries will register C.
        file_to_commits = {}
        commit_to_files = defaultdict(set)

        for rel_path in sorted(source_files):
            commits = _get_commits_for_file(args.repo, args.commit, rel_path)
            file_to_commits[rel_path] = commits
            for c in commits:
                commit_to_files[c].add(rel_path)

        # Compute co-change counts per file
        co_changes = {}
        for rel_path in source_files:
            co_counts = defaultdict(int)
            for c in file_to_commits[rel_path]:
                for other in commit_to_files[c]:
                    if other != rel_path:
                        co_counts[other] += 1
            co_changes[rel_path] = sorted(co_counts.items(), key=lambda x: -x[1])[: args.top_n]

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for rel_path in sorted(source_files):
                f.write(f"{rel_path}\n")
                for co_file, count in co_changes[rel_path]:
                    f.write(f"→ {co_file} ({count}x)\n")

        print(f"Wrote {len(source_files)} entries to {args.out}")
    finally:
        print(f"Restoring {original_head[:8]}")
        restore(args.repo, original_head)


if __name__ == "__main__":
    main()
