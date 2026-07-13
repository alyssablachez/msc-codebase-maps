"""
Shared filters for reducing a raw file list (ground truth or predictions)
to the subset that's actually scorable — i.e. discoverable via this
study's maps and tools.

Single canonical copy, used both at pool-construction time (build_issue_pool_*.py)
and at scoring time (harness/run_trial.py), per the methodology in DEVLOG.md:
ground_truth in issue_selection_final.csv stores the full raw file list; these
filters are applied consistently wherever files need to be reduced to the
subset that maps/tools can actually surface.

Two filters, composed by scorable_files():
- source_files_only(): path-pattern based (tests/benchmarks/docs/config)
  — repo-agnostic, no per-issue context needed.
- known_package_files() / scorable_files(): per-issue package-directory
  scope — catches non-Python files and real .py files that sit outside the
  resolved package directory (e.g. a repo-root utils/ or a sibling
  examples-style directory), neither of which source_files_only() alone
  can catch since scope differs per repo/commit. Uses each issue's
  freq_map.txt as the reference file list, since that already walks every
  .py file within the resolved package directory at map-generation time,
  regardless of AST-parseability.

No side effects at import time — pure functions only (except the file
read in known_package_files(), which only happens when called).
"""

import os

_SOURCE_EXCLUDE = [
    "test_", "_test.", "/tests/", "/test/",
    "benchmark", "bench_",
    "/examples/", "/docs/",
    ".snapshot.", ".validation.",
    "setup.py", "setup.cfg",
    ".cfg", ".toml", ".ini", ".json", ".yml", ".yaml",
    ".pyx", ".pxd", ".pxi", ".in",
    "conftest.py", "mockserver.py",
]


def source_files_only(files):
    """Return only files whose paths contain no test/docs/config indicators.

    Patterns like "/tests/" are matched against the path with a leading "/"
    prepended, so a file sitting directly at the top of a tests/ directory
    (e.g. "tests/caching_ai.py", no directory prefix before "tests/") is
    still caught — a plain substring check on the unmodified path would miss
    it, since "/tests/" never occurs without a preceding path component.
    """
    result = []
    for f in files:
        norm = "/" + f.replace("\\", "/")
        if not any(pat in norm for pat in _SOURCE_EXCLUDE):
            result.append(f)
    return result


def known_package_files(repo, issue_idx, maps_root):
    """Return the set of .py files within the resolved package directory
    for this issue, per its freq_map.txt (walked at map-generation time,
    covers every .py file in scope regardless of AST-parseability)."""
    freq_path = os.path.join(maps_root, repo, str(issue_idx), "freq_map.txt")
    with open(freq_path, encoding="utf-8") as f:
        return {line.split("  [", 1)[0] for line in f if line.strip()}


def scorable_files(files, repo, issue_idx, maps_root):
    """Reduce files to the subset that's both a legitimate source file
    (source_files_only) and within the resolved package directory for
    this issue — i.e. actually discoverable via the maps/tools in scope.
    Catches non-Python files and out-of-package-scope .py files that
    source_files_only() alone can't, since scope differs per repo/issue."""
    known = known_package_files(repo, issue_idx, maps_root)
    return [f for f in source_files_only(files) if f in known]
