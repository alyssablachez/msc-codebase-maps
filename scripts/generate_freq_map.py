"""
Generate a historical edit-frequency map for a Python package at a given commit.

For each source file in the resolved package directory, counts how many commits
in history (up to and including base_commit) touched that file, and reports the
date of the most recent such commit.

Usage:
    python3 scripts/generate_freq_map.py \
        --repo repos/requests_full \
        --commit abc1234 \
        --out repo_maps/requests/task_0/freq_map.txt \
        --package-name requests
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from git_utils import checkout, current_head, git, restore
from package_resolver import resolve_package_dir


def _count_edits(repo_dir, base_commit, rel_path):
    result = git(repo_dir, ["log", "--oneline", base_commit, "--", rel_path])
    return sum(1 for line in result.stdout.splitlines() if line.strip())


def _last_edit_date(repo_dir, base_commit, rel_path):
    result = git(repo_dir, ["log", "-1", base_commit, "--format=%ci", "--", rel_path])
    date_str = result.stdout.strip()
    return date_str.split()[0] if date_str else "unknown"


def main():
    parser = argparse.ArgumentParser(
        description="Generate edit-frequency map for a Python package"
    )
    parser.add_argument("--repo", required=True, help="Path to the git repository")
    parser.add_argument("--commit", required=True, help="Base commit SHA (history up to this)")
    parser.add_argument("--out", required=True, help="Output text file path")
    parser.add_argument("--package-name", default=None,
                        help="Package name (auto-detected if omitted)")
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

        source_files = []
        for dirpath, dirs, filenames in os.walk(pkg_dir):
            for fname in sorted(filenames):
                if fname.endswith(".py"):
                    filepath = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(filepath, args.repo)
                    source_files.append(rel_path)

        print(f"Found {len(source_files)} source files; querying git history...")

        file_stats = []
        for rel_path in source_files:
            n = _count_edits(args.repo, args.commit, rel_path)
            date = _last_edit_date(args.repo, args.commit, rel_path)
            file_stats.append((rel_path, n, date))

        file_stats.sort(key=lambda x: -x[1])

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            for rel_path, n, date in file_stats:
                f.write(f"{rel_path}  [{n} edits, last: {date}]\n")

        print(f"Wrote {len(file_stats)} entries to {args.out}")
    finally:
        print(f"Restoring {original_head[:8]}")
        restore(args.repo, original_head)


if __name__ == "__main__":
    main()
