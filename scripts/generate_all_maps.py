"""
Generate AST compact, frequency, and co-change maps for all 45 selected issues
across 15 codebases.  Tracks statistics in repo_maps/map_generation_stats.csv.

Usage:
    python3 scripts/generate_all_maps.py
    python3 scripts/generate_all_maps.py --dry-run
"""
import argparse
import csv
import io
import os
import pickle
import subprocess
import sys
import tarfile
import time
from collections import defaultdict

import pandas as pd
import yaml

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(_ROOT, "scripts")

REPO_DIR_MAP = {
    "requests":               "repos/requests_full",
    "thefuck":                "repos/thefuck_full",
    "flask":                  "repos/flask_full",
    "gpt-engineer":           "repos/gpt_engineer_full",
    "fastapi":                "repos/fastapi_full",
    "scrapy":                 "repos/scrapy_full",
    "rich":                   "repos/rich_full",
    "stable-diffusion-webui": "repos/stable_diffusion_webui_full",
    "keras":                  "repos/keras_full",
    "localstack":             "repos/localstack_full",
    "yt-dlp":                 "repos/ytdlp_full",
    "pandas":                 "repos/pandas_full",
    "scikit-learn":           "repos/scikit_learn_full",
    "transformers":           "repos/transformers_full",
    "core":                   "repos/core_full",
}

PACKAGE_MAP = {
    "requests":               "requests",
    "thefuck":                "thefuck",
    "flask":                  "flask",
    "gpt-engineer":           "gpt_engineer",
    "fastapi":                "fastapi",
    "scrapy":                 "scrapy",
    "rich":                   "rich",
    "stable-diffusion-webui": "modules",
    "keras":                  "keras",
    "localstack":             "localstack",
    "yt-dlp":                 "yt_dlp",
    "pandas":                 "pandas",
    "scikit-learn":           "sklearn",
    "transformers":           "transformers",
    "core":                   "homeassistant",
}

STATS_CSV        = os.path.join(_ROOT, "repo_maps", "map_generation_stats.csv")
SKIP_CONFIG_YAML = os.path.join(_ROOT, "data", "repo_skip_config.yaml")
STATS_COLS = [
    "repo", "tier", "issue_idx", "role",
    "base_commit", "commit_date",
    "package_dir", "n_source_files", "n_ast_records",
    "ast_map_chars", "ast_map_tokens",
    "compact_map_chars", "compact_map_tokens", "compact_reduction_pct",
    "freq_map_chars", "freq_map_tokens",
    "cochange_map_chars", "cochange_map_tokens",
    "python_loc", "total_loc",
    "status", "error_message", "duration_seconds",
]


def pkg_tree_path(repo_dir, commit, pkg_name):
    """Return the git tree path for the package (e.g. 'src/flask', 'requests', or '')."""
    for candidate in [f"src/{pkg_name}", pkg_name]:
        r = subprocess.run(
            ["git", "-C", repo_dir, "ls-tree", "--name-only", commit, candidate + "/"],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            return candidate
    return ""


def count_loc(repo_dir, commit, tree_path):
    """Return (python_loc, total_loc) using git archive — no checkout needed."""
    cmd = ["git", "-C", repo_dir, "archive", commit]
    if tree_path:
        cmd.append(tree_path + "/")
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        return None, None
    python_loc = 0
    total_loc  = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(r.stdout)) as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                f = tar.extractfile(member)
                if f is None:
                    continue
                content = f.read()
                if b"\x00" in content[:1024]:
                    continue
                lines = content.count(b"\n")
                total_loc += lines
                if member.name.endswith(".py"):
                    python_loc += lines
    except Exception:
        return None, None
    return python_loc, total_loc


def load_skip_dirs(repo, issue_idx):
    """Return the effective list of skip-dir names for a specific issue."""
    with open(SKIP_CONFIG_YAML, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    defaults = cfg.get("defaults", {}).get("skip_dirs", [])
    key = f"{repo}/{issue_idx}"
    extra = cfg.get("issues", {}).get(key, {}).get("extra_skip_dirs", [])
    return defaults + extra


def run(cmd):
    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr, time.time() - start


def _int(text, key):
    for line in text.splitlines():
        if key in line:
            raw = line.split(":", 1)[1].strip().replace(",", "").split()[0]
            try:
                return int(raw)
            except ValueError:
                pass
    return None


def _float(text, key):
    for line in text.splitlines():
        if key in line:
            raw = line.split(":", 1)[1].strip().rstrip("%")
            try:
                return float(raw)
            except ValueError:
                pass
    return None


def _str(text, key):
    for line in text.splitlines():
        if key in line:
            return line.split(":", 1)[1].strip()
    return None


def commit_date(repo_dir, sha):
    r = subprocess.run(
        ["git", "-C", repo_dir, "log", "-1", "--format=%ci", sha],
        capture_output=True, text=True,
    )
    s = r.stdout.strip()
    return s.split()[0] if s else "unknown"


def file_chars(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8", errors="replace") as f:
        return len(f.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Print plan without running anything")
    ap.add_argument("--only", nargs="+", default=None,
                    help="Only (re)generate specific issues, e.g. --only core:20 pandas:26. "
                         "Stats CSV is merged (not overwritten) and stale rows for issues no "
                         "longer in issue_selection_final.csv are dropped.")
    args = ap.parse_args()

    sel_csv  = os.path.join(_ROOT, "data", "issue_selection_final.csv")
    pkl_file = os.path.join(_ROOT, "data",
                            "all_issues_with_pr_commit_comment_all_project_0922.pkl")

    issues = pd.read_csv(sel_csv)
    all_selected_keys = set(zip(issues["repo"], issues["issue_idx"].astype(int)))

    if args.only:
        only_keys = set()
        for spec in args.only:
            repo, idx = spec.rsplit(":", 1)
            only_keys.add((repo, int(idx)))
        missing = only_keys - all_selected_keys
        if missing:
            print(f"ERROR: not in issue_selection_final.csv: {missing}", file=sys.stderr)
            sys.exit(1)
        issues = issues[
            issues.apply(lambda r: (r["repo"], int(r["issue_idx"])) in only_keys, axis=1)
        ].reset_index(drop=True)

    with open(pkl_file, "rb") as f:
        pkl_df = pd.DataFrame(pickle.load(f))

    total = len(issues)
    print(f"Generating maps for {total} issues across {issues['repo'].nunique()} repos")
    if args.dry_run:
        print()
    else:
        print(f"Stats → {STATS_CSV}\n")

    if args.dry_run:
        for _, row in issues.iterrows():
            repo = row["repo"]
            repo_dir = os.path.join(_ROOT, REPO_DIR_MAP[repo])
            subset = pkl_df[pkl_df["repo_name"] == repo].reset_index(drop=True)
            commit = subset.iloc[int(row["issue_idx"])]["base_commit"]
            skip = load_skip_dirs(repo, int(row["issue_idx"]))
            print(f"  {repo:<28} issue={row['issue_idx']:>3}  "
                  f"commit={commit[:8]}  pkg={PACKAGE_MAP[repo]}"
                  f"  skip=[{', '.join(skip[:4])}{'...' if len(skip) > 4 else ''}]")
        return

    os.makedirs(os.path.dirname(STATS_CSV), exist_ok=True)

    all_stats = []
    t0 = time.time()

    for enum_i, (_, row) in enumerate(issues.iterrows()):
        repo      = row["repo"]
        tier      = row["tier"]
        issue_idx = int(row["issue_idx"])
        role      = row["role"]

        repo_dir  = os.path.join(_ROOT, REPO_DIR_MAP[repo])
        pkg_name  = PACKAGE_MAP[repo]

        subset      = pkl_df[pkl_df["repo_name"] == repo].reset_index(drop=True)
        base_commit = subset.iloc[issue_idx]["base_commit"]

        out_dir      = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx))
        ast_out      = os.path.join(out_dir, "ast_map.json")
        compact_out  = os.path.join(out_dir, "compact_map.txt")
        freq_out     = os.path.join(out_dir, "freq_map.txt")
        cochange_out = os.path.join(out_dir, "cochange_map.txt")
        os.makedirs(out_dir, exist_ok=True)

        stat = {c: None for c in STATS_COLS}
        stat.update({"repo": repo, "tier": tier, "issue_idx": issue_idx,
                     "role": role, "base_commit": base_commit[:8]})

        issue_t0 = time.time()
        errors = []

        # Commit date
        stat["commit_date"] = commit_date(repo_dir, base_commit)

        skip_dirs = load_skip_dirs(repo, issue_idx)

        # ── 1. AST map ────────────────────────────────────────────────────────
        ast_ok = False
        cmd_ast = [
            sys.executable, os.path.join(SCRIPTS, "generate_ast_map.py"),
            "--repo", repo_dir, "--commit", base_commit,
            "--out", ast_out, "--package-name", pkg_name,
        ]
        if skip_dirs:
            cmd_ast += ["--skip-dirs"] + skip_dirs
        rc, stdout, stderr, _ = run(cmd_ast)
        if rc != 0:
            errors.append(f"ast_map rc={rc}: {stderr.strip()[:300]}")
        else:
            ast_ok = True
            stat["package_dir"]    = _str(stdout, "Package dir:")
            stat["n_source_files"] = _int(stdout, "Files walked:")
            stat["n_ast_records"]  = _int(stdout, "Records extracted:")
            stat["ast_map_chars"]  = _int(stdout, "Character count:")
            stat["ast_map_tokens"] = _int(stdout, "Estimated tokens:")

        # ── 2. Compact map ────────────────────────────────────────────────────
        if ast_ok:
            rc, stdout, stderr, _ = run([
                sys.executable, os.path.join(SCRIPTS, "compact_map.py"),
                "--in", ast_out, "--out", compact_out,
            ])
            if rc != 0:
                errors.append(f"compact_map rc={rc}: {stderr.strip()[:300]}")
            else:
                for line in stdout.splitlines():
                    if line.startswith("Output:"):
                        parts = line.split()
                        try:
                            stat["compact_map_chars"] = int(parts[1].replace(",", ""))
                            # ~{n:>6,} may produce "~10,000" (joined) or "~ 1,000"
                            # (split into "~" + "1,000") depending on width
                            if parts[3] == "~":
                                stat["compact_map_tokens"] = int(parts[4].replace(",", ""))
                            else:
                                stat["compact_map_tokens"] = int(
                                    parts[3].lstrip("~").replace(",", ""))
                        except (IndexError, ValueError):
                            pass
                stat["compact_reduction_pct"] = _float(stdout, "Reduction:")

        # ── 3. Freq map ───────────────────────────────────────────────────────
        cmd_freq = [
            sys.executable, os.path.join(SCRIPTS, "generate_freq_map.py"),
            "--repo", repo_dir, "--commit", base_commit,
            "--out", freq_out, "--package-name", pkg_name,
        ]
        if skip_dirs:
            cmd_freq += ["--skip-dirs"] + skip_dirs
        rc, stdout, stderr, _ = run(cmd_freq)
        if rc != 0:
            errors.append(f"freq_map rc={rc}: {stderr.strip()[:300]}")
        else:
            chars = file_chars(freq_out)
            stat["freq_map_chars"]  = chars
            stat["freq_map_tokens"] = chars // 4 if chars is not None else None

        # ── 4. Co-change map ──────────────────────────────────────────────────
        cmd_co = [
            sys.executable, os.path.join(SCRIPTS, "generate_cochange_map.py"),
            "--repo", repo_dir, "--commit", base_commit,
            "--out", cochange_out, "--package-name", pkg_name,
        ]
        if skip_dirs:
            cmd_co += ["--skip-dirs"] + skip_dirs
        rc, stdout, stderr, _ = run(cmd_co)
        if rc != 0:
            errors.append(f"cochange_map rc={rc}: {stderr.strip()[:300]}")
        else:
            chars = file_chars(cochange_out)
            stat["cochange_map_chars"]  = chars
            stat["cochange_map_tokens"] = chars // 4 if chars is not None else None

        # ── 5. LOC ────────────────────────────────────────────────────────────
        tree_path = pkg_tree_path(repo_dir, base_commit, pkg_name)
        py_loc, tot_loc = count_loc(repo_dir, base_commit, tree_path)
        stat["python_loc"] = py_loc
        stat["total_loc"]  = tot_loc

        stat["duration_seconds"] = round(time.time() - issue_t0, 1)
        stat["status"]        = "failed" if errors else "success"
        stat["error_message"] = "; ".join(errors) if errors else ""
        all_stats.append(stat)

        status_tag = "FAILED" if errors else "OK"
        print(f"[{enum_i+1:>2}/{total}] {repo} issue={issue_idx} ({role})"
              f" — {status_tag} in {stat['duration_seconds']:.1f}s")
        for e in errors:
            print(f"  WARNING: {e}")

    # ── Write CSV ─────────────────────────────────────────────────────────────
    # Merge into any existing stats CSV: drop rows for issues no longer in
    # issue_selection_final.csv, replace/add rows for issues just (re)run,
    # leave every other existing row untouched (relevant when --only is used).
    new_keys = {(s["repo"], s["issue_idx"]) for s in all_stats}
    kept_old = []
    if os.path.exists(STATS_CSV):
        with open(STATS_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                key = (r["repo"], int(r["issue_idx"]))
                if key in all_selected_keys and key not in new_keys:
                    kept_old.append(r)

    merged = kept_old + all_stats
    merged.sort(key=lambda r: (r["repo"], int(r["issue_idx"])))

    with open(STATS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=STATS_COLS)
        writer.writeheader()
        writer.writerows(merged)

    # ── Summary table ─────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print(f"\n{'='*72}")
    print(f"SUMMARY  {total} issues  {elapsed:.0f}s total")
    print(f"{'='*72}")

    def mean_nn(lst, key):
        vals = [x[key] for x in lst if x.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    hdr = (f"{'repo':<28} {'n':>2}  {'compact_tok':>11}  "
           f"{'freq_tok':>8}  {'cochange_tok':>12}  {'failed':>6}")
    print(hdr)
    print("-" * len(hdr))

    repo_groups = defaultdict(list)
    for s in all_stats:
        repo_groups[s["repo"]].append(s)

    all_mc, all_mf, all_mco = [], [], []
    total_failed = 0

    for repo in sorted(repo_groups):
        rows = repo_groups[repo]
        n_fail = sum(1 for r in rows if r["status"] == "failed")
        total_failed += n_fail
        mc  = mean_nn(rows, "compact_map_tokens")
        mf  = mean_nn(rows, "freq_map_tokens")
        mco = mean_nn(rows, "cochange_map_tokens")
        if mc  is not None: all_mc.append(mc)
        if mf  is not None: all_mf.append(mf)
        if mco is not None: all_mco.append(mco)
        mc_s  = f"{mc:>11.0f}"  if mc  is not None else f"{'n/a':>11}"
        mf_s  = f"{mf:>8.0f}"   if mf  is not None else f"{'n/a':>8}"
        mco_s = f"{mco:>12.0f}" if mco is not None else f"{'n/a':>12}"
        print(f"{repo:<28} {len(rows):>2}  {mc_s}  {mf_s}  {mco_s}  {n_fail:>6}")

    print("-" * len(hdr))
    gmc  = sum(all_mc)  / len(all_mc)  if all_mc  else None
    gmf  = sum(all_mf)  / len(all_mf)  if all_mf  else None
    gmco = sum(all_mco) / len(all_mco) if all_mco else None
    gmc_s  = f"{gmc:>11.0f}"  if gmc  is not None else f"{'n/a':>11}"
    gmf_s  = f"{gmf:>8.0f}"   if gmf  is not None else f"{'n/a':>8}"
    gmco_s = f"{gmco:>12.0f}" if gmco is not None else f"{'n/a':>12}"
    print(f"{'OVERALL (mean of repo means)':<28} {'':>2}  {gmc_s}  {gmf_s}  {gmco_s}  {total_failed:>6}")
    print(f"\nStats saved → {STATS_CSV}")


if __name__ == "__main__":
    main()
