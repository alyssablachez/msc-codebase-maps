"""
Shared filter for reducing a ground-truth file list to "scorable" Python
source files — excludes tests, benchmarks, docs/examples, config/data
files, snapshots, Cython, and known non-source helper files.

Single canonical copy, used both at pool-construction time (build_issue_pool_*.py)
and at scoring time (harness/run_trial.py), per the methodology in DEVLOG.md:
ground_truth in issue_selection_final.csv stores the full raw file list; this
filter is applied consistently wherever files need to be reduced to the
Python-source subset that maps/tools can actually surface.

No side effects at import time — pure functions only.
"""

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
