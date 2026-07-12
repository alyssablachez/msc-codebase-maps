"""
Measure Python LOC and total text-file LOC for each of the 15 repos as they
currently exist on disk (no commit checkout).

Reports three scopes per repo:
  repo_py_loc   — all .py files in the entire cloned repo
  repo_tot_loc  — all text files in the entire cloned repo
  src_py_loc    — .py files in the main source package dir only

Usage:
    python3 scripts/audit_repo_sizes_current.py
"""
import os
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REPOS = {
    "requests":               ("repos/requests_full",            "requests"),
    "thefuck":                ("repos/thefuck_full",             "thefuck"),
    "flask":                  ("repos/flask_full",               "flask"),
    "gpt-engineer":           ("repos/gpt_engineer_full",        "gpt_engineer"),
    "Deep-Live-Cam":          ("repos/deep_live_cam_full",       "modules"),
    "scrapy":                 ("repos/scrapy_full",              "scrapy"),
    "rich":                   ("repos/rich_full",                "rich"),
    "fastapi":                ("repos/fastapi_full",             "fastapi"),
    "open-interpreter":       ("repos/open_interpreter_full",    "interpreter"),
    "stable-diffusion-webui": ("repos/stable_diffusion_webui_full", "modules"),
    "yt-dlp":                 ("repos/ytdlp_full",               "yt_dlp"),
    "keras":                  ("repos/keras_full",               "keras"),
    "scikit-learn":           ("repos/scikit_learn_full",        "sklearn"),
    "localstack":             ("repos/localstack_full",          "localstack"),
    "pandas":                 ("repos/pandas_full",              "pandas"),
}

SKIP_DIRS = {
    ".git", "__pycache__", "build", "dist", ".eggs", ".tox",
    "venv", ".venv", "env", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


def count_loc(root):
    """Walk root on disk and return (python_loc, total_loc)."""
    py_loc = tot_loc = 0
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            path = os.path.join(dirpath, fn)
            try:
                with open(path, "rb") as f:
                    content = f.read()
                if b"\x00" in content[:1024]:   # skip binaries
                    continue
                lines = content.count(b"\n")
                tot_loc += lines
                if fn.endswith(".py"):
                    py_loc += lines
            except OSError:
                pass
    return py_loc, tot_loc


def resolve_src_dir(repo_dir, pkg_name):
    """Return the source package directory path on disk."""
    for candidate in [
        os.path.join(repo_dir, "src", pkg_name),
        os.path.join(repo_dir, pkg_name),
    ]:
        if os.path.isdir(candidate):
            return candidate
    return repo_dir   # flat structure fallback


def main():
    sel = pd.read_csv(os.path.join(_ROOT, "data", "issue_selection_random.csv"))
    tiers = sel.drop_duplicates("repo").set_index("repo")["tier"]

    print(f"{'repo':<28} {'tier':<8}  {'repo_py_loc':>12}  {'repo_tot_loc':>13}  {'src_py_loc':>11}  src_dir")
    print("-" * 100)

    rows = []
    for name, (rel_dir, pkg_name) in REPOS.items():
        repo_dir = os.path.join(_ROOT, rel_dir)
        src_dir  = resolve_src_dir(repo_dir, pkg_name)
        src_rel  = os.path.relpath(src_dir, repo_dir) if src_dir != repo_dir else "(root)"

        r_py, r_tot = count_loc(repo_dir)
        s_py, _     = count_loc(src_dir)
        tier = tiers.get(name, "?")

        print(f"{name:<28} {tier:<8}  {r_py:>12,}  {r_tot:>13,}  {s_py:>11,}  {src_rel}")
        rows.append({"repo": name, "tier": tier,
                     "repo_py_loc": r_py, "repo_tot_loc": r_tot, "src_py_loc": s_py,
                     "src_dir": src_rel})

    print()
    # Sort by repo Python LOC so size ordering is clear
    df = pd.DataFrame(rows).sort_values("repo_py_loc")
    print("Sorted by repo_py_loc:")
    print(f"{'repo':<28} {'tier':<8}  {'repo_py_loc':>12}  {'src_py_loc':>11}")
    print("-" * 66)
    for _, r in df.iterrows():
        print(f"{r['repo']:<28} {r['tier']:<8}  {r['repo_py_loc']:>12,}  {r['src_py_loc']:>11,}")


if __name__ == "__main__":
    main()
