import os

EXCLUDE_DIRS = {
    "tests", "test", "docs", "doc", "scripts", "examples",
    "benchmarks", "build", "dist", ".git", "__pycache__",
    "setup", "conf", "venv", ".venv", "env", "site-packages",
}


def resolve_package_dir(repo_dir, package_name=None):
    """Return the absolute path to the source package directory.

    If package_name is given, tries src/<package_name> then <package_name> at
    the repo root. Raises ValueError if neither exists.

    If package_name is None, auto-detects by finding top-level directories
    (at the repo root or under src/) that contain __init__.py, excluding dirs
    listed in EXCLUDE_DIRS. Raises ValueError if none or ambiguous.
    """
    if package_name is not None:
        candidates = [
            os.path.join(repo_dir, "src", package_name),
            os.path.join(repo_dir, package_name),
        ]
        for c in candidates:
            if os.path.isdir(c):
                return c
        print(
            f"WARNING: No package directory found in {repo_dir} — "
            f"falling back to repo root. This typically means the "
            f"repository had a flat structure at this commit with no "
            f"package directory."
        )
        return repo_dir

    found = []

    def _scan(base):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            return
        for name in names:
            if name in EXCLUDE_DIRS or name.startswith("."):
                continue
            path = os.path.join(base, name)
            if os.path.isdir(path) and os.path.isfile(os.path.join(path, "__init__.py")):
                found.append(path)

    _scan(repo_dir)
    src_dir = os.path.join(repo_dir, "src")
    if os.path.isdir(src_dir):
        _scan(src_dir)

    if not found:
        print(
            f"WARNING: No package directory found in {repo_dir} — "
            f"falling back to repo root. This typically means the "
            f"repository had a flat structure at this commit with no "
            f"package directory."
        )
        return repo_dir

    # Prefer shorter paths (repo root over src/), then alphabetical
    found.sort(key=lambda p: (len(p.split(os.sep)), p))
    return found[0]


def find_package_dir(repo, package_name):
    """Legacy wrapper — returns None on failure instead of raising."""
    try:
        return resolve_package_dir(repo, package_name)
    except ValueError:
        return None
