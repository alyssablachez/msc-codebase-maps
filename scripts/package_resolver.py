import os


def find_package_dir(repo, package_name):
    """Return the first existing candidate directory for the named package.

    Tries src/<package_name> (modern src-layout) then <package_name> at the
    repo root (legacy flat layout). Returns None if neither exists.
    """
    candidates = [
        os.path.join(repo, "src", package_name),
        os.path.join(repo, package_name),
    ]
    for c in candidates:
        if os.path.isdir(c):
            return c
    return None
