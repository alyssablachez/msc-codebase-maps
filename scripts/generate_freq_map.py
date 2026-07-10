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


def _get_all_file_stats(repo_dir, base_commit, source_files):
    """Get edit counts and last edit dates for all files in one git call."""
    result = git(repo_dir, [
        "log", "--format=COMMIT %H %ci", "--name-only", base_commit
    ])

    counts = {p: 0 for p in source_files}
    last_dates = {p: "unknown" for p in source_files}
    source_set = set(source_files)

    current_date = None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("COMMIT "):
            parts = line.split(" ", 2)
            current_date = parts[2].split()[0] if len(parts) > 2 else "unknown"
        elif line in source_set:
            counts[line] += 1
            if last_dates[line] == "unknown":
                last_dates[line] = current_date

    return counts, last_dates


def main():
    parser = argparse.ArgumentParser(
        description="Generate edit-frequency map for a Python package"
    )
    parser.add_argument("--repo", required=True, help="Path to the git repository")
    parser.add_argument("--commit", required=True, help="Base commit SHA (history up to this)")
    parser.add_argument("--out", required=True, help="Output text file path")
    parser.add_argument("--package-name", default=None,
                        help="Package name (auto-detected if omitted)")
    parser.add_argument("--skip-dirs", nargs="+", default=[],
                        help="Subdirectory names to skip while recursing (default: none).")
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

        skip = set(args.skip_dirs)
        source_files = []
        for dirpath, dirs, filenames in os.walk(pkg_dir):
            dirs[:] = [d for d in dirs if d not in skip]
            for fname in sorted(filenames):
                if fname.endswith(".py"):
                    filepath = os.path.join(dirpath, fname)
                    rel_path = os.path.relpath(filepath, args.repo)
                    source_files.append(rel_path)

        print(f"Found {len(source_files)} source files; querying git history...")
        counts, last_dates = _get_all_file_stats(args.repo, args.commit, source_files)

        file_stats = [
            (rel_path, counts[rel_path], last_dates[rel_path])
            for rel_path in source_files
        ]
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
