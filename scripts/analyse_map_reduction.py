"""
Analyse two approaches to uniformly reducing compact map token count:

  A. Skip-dirs  — exclude standard test/docs/examples directories
  B. Freq filter — only include files with >= N edits in git history

Uses existing generated maps; no re-generation needed.
Prints a report and saves repo_maps/map_reduction_analysis.csv.
"""
import ast as pyast
import json
import os
import re
import sys
from collections import defaultdict

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── config ────────────────────────────────────────────────────────────────────

SKIP_DIRS = {
    "tests", "test", "testing",
    "docs", "doc", "documentation",
    "examples", "example",
    "benchmarks", "benchmark",
    "build", "dist",
}

FREQ_THRESHOLDS = [1, 2, 5, 10, 20]

# ── helpers ───────────────────────────────────────────────────────────────────

def load_ast_files(issue_dir):
    """Return list of unique file paths from ast_map.json."""
    path = os.path.join(issue_dir, "ast_map.json")
    if not os.path.exists(path):
        return []
    files = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                files.add(json.loads(line)["file"])
    return sorted(files)


def parse_compact_sections(issue_dir, known_files):
    """
    Parse compact_map.txt into {file_path: char_count}.
    Uses known_files (from ast_map) to identify section boundaries reliably.
    """
    path = os.path.join(issue_dir, "compact_map.txt")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    file_set = set(known_files)
    sections = {}
    current = None
    chars = 0

    for line in lines:
        stripped = line.strip()
        if stripped in file_set:
            if current is not None:
                sections[current] = chars
            current = stripped
            chars = len(line)
        else:
            chars += len(line)

    if current is not None:
        sections[current] = chars

    return sections


def parse_freq_map(issue_dir):
    """Return {rel_path: edit_count} from freq_map.txt."""
    path = os.path.join(issue_dir, "freq_map.txt")
    if not os.path.exists(path):
        return {}
    pattern = re.compile(r'^(.+?)\s+\[(\d+) edits')
    result = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = pattern.match(line.strip())
            if m:
                result[m.group(1)] = int(m.group(2))
    return result


def in_skip_dir(file_path):
    parts = file_path.replace("\\", "/").split("/")
    return any(p.lower() in SKIP_DIRS for p in parts)


def parse_ground_truth(gt_str):
    try:
        val = pyast.literal_eval(str(gt_str))
        return val if isinstance(val, list) else [str(val)]
    except Exception:
        return []


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    sel_csv = os.path.join(_ROOT, "data", "issue_selection_random.csv")
    issues  = pd.read_csv(sel_csv)

    rows = []

    for _, issue_row in issues.iterrows():
        repo      = issue_row["repo"]
        issue_idx = int(issue_row["issue_idx"])
        role      = issue_row["role"]
        tier      = issue_row["tier"]
        gt_files  = parse_ground_truth(issue_row["ground_truth"])

        issue_dir = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx))

        known_files  = load_ast_files(issue_dir)
        sections     = parse_compact_sections(issue_dir, known_files)
        freq         = parse_freq_map(issue_dir)

        if not sections:
            continue  # failed issue (gpt-engineer/32)

        total_chars = sum(sections.values())

        # ── A. Skip-dirs ──────────────────────────────────────────────────────
        skip_chars  = sum(c for f, c in sections.items() if in_skip_dir(f))
        kept_chars_skip = total_chars - skip_chars
        skip_pct    = skip_chars / total_chars * 100 if total_chars else 0

        # Which top-level dirs are being skipped?
        skip_dirs_hit = set()
        for f in sections:
            parts = f.replace("\\", "/").split("/")
            for p in parts:
                if p.lower() in SKIP_DIRS:
                    skip_dirs_hit.add(p)
                    break

        # ── B. Frequency filter ───────────────────────────────────────────────
        # For each threshold: chars retained, and whether GT files are covered
        freq_kept_chars   = {}
        freq_gt_coverage  = {}

        for n in FREQ_THRESHOLDS:
            kept = {f: c for f, c in sections.items()
                    if freq.get(f, 0) >= n}
            freq_kept_chars[n] = sum(kept.values())

            # GT coverage: fraction of GT files with edit_count >= n
            if gt_files:
                covered = sum(1 for gt in gt_files if freq.get(gt, 0) >= n)
                freq_gt_coverage[n] = covered / len(gt_files) * 100
            else:
                freq_gt_coverage[n] = None

        # ── Combined (skip-dirs THEN freq filter) ─────────────────────────────
        combined = {}
        for n in FREQ_THRESHOLDS:
            kept = {f: c for f, c in sections.items()
                    if not in_skip_dir(f) and freq.get(f, 0) >= n}
            combined[n] = sum(kept.values())

        row = {
            "repo": repo, "tier": tier, "issue_idx": issue_idx, "role": role,
            "total_tokens":     total_chars // 4,
            "skip_tokens_removed": skip_chars // 4,
            "skip_tokens_kept":    kept_chars_skip // 4,
            "skip_pct_removed":    round(skip_pct, 1),
            "skip_dirs_hit":       ",".join(sorted(skip_dirs_hit)) or "none",
        }
        for n in FREQ_THRESHOLDS:
            row[f"freq{n}_tokens_kept"]   = freq_kept_chars[n] // 4
            row[f"freq{n}_pct_kept"]      = round(freq_kept_chars[n] / total_chars * 100, 1) if total_chars else None
            row[f"freq{n}_gt_coverage"]   = round(freq_gt_coverage[n], 1) if freq_gt_coverage[n] is not None else None
            row[f"combined{n}_tokens_kept"] = combined[n] // 4

        rows.append(row)

    df = pd.DataFrame(rows)

    # ── Save CSV ──────────────────────────────────────────────────────────────
    out_csv = os.path.join(_ROOT, "repo_maps", "map_reduction_analysis.csv")
    df.to_csv(out_csv, index=False)

    # ── Print report ──────────────────────────────────────────────────────────
    W = 80
    print("=" * W)
    print("COMPACT MAP REDUCTION ANALYSIS")
    print("=" * W)

    # ── Section A ─────────────────────────────────────────────────────────────
    print("\n── A. SKIP-DIRS  (tests/docs/examples/benchmarks/build) ─────────────────\n")
    print(f"{'repo':<28} {'total_tok':>9}  {'removed':>7}  {'kept':>7}  "
          f"{'pct_removed':>11}  skip_dirs")
    print("-" * W)
    for _, r in df.sort_values("repo").iterrows():
        print(f"{r['repo']:<28} {r['total_tokens']:>9,}  "
              f"{r['skip_tokens_removed']:>7,}  "
              f"{r['skip_tokens_kept']:>7,}  "
              f"{r['skip_pct_removed']:>10.1f}%  "
              f"{r['skip_dirs_hit']}")

    mean_skip = df["skip_pct_removed"].mean()
    mean_kept_tok = df["skip_tokens_kept"].mean()
    print("-" * W)
    print(f"{'MEAN':<28} {df['total_tokens'].mean():>9,.0f}  "
          f"{df['skip_tokens_removed'].mean():>7,.0f}  "
          f"{mean_kept_tok:>7,.0f}  "
          f"{mean_skip:>10.1f}%")

    # ── Section B ─────────────────────────────────────────────────────────────
    print("\n\n── B. FREQUENCY FILTER  (per-threshold summary across all issues) ────────\n")

    hdr = f"{'threshold':>9}  {'mean_pct_kept':>13}  {'mean_tok_kept':>13}  {'gt_coverage_100%':>16}  {'gt_coverage_>=90%':>17}"
    print(hdr)
    print("-" * len(hdr))
    for n in FREQ_THRESHOLDS:
        pct_col   = f"freq{n}_pct_kept"
        tok_col   = f"freq{n}_tokens_kept"
        cov_col   = f"freq{n}_gt_coverage"
        mean_pct  = df[pct_col].mean()
        mean_tok  = df[tok_col].mean()
        cov100    = (df[cov_col] == 100).sum()
        cov90     = (df[cov_col] >= 90).sum()
        print(f"{'>='+str(n)+' edits':>9}  {mean_pct:>12.1f}%  "
              f"{mean_tok:>13,.0f}  "
              f"{cov100:>12d}/{len(df)}  "
              f"{cov90:>13d}/{len(df)}")

    # ── Section C: GT coverage detail for best threshold ──────────────────────
    print("\n\n── C. GT COVERAGE BY REPO  (freq filter thresholds) ─────────────────────\n")
    print(f"{'repo':<28}" + "".join(f"  {'>= '+str(n)+' ed':>8}" for n in FREQ_THRESHOLDS))
    print("-" * (28 + 11 * len(FREQ_THRESHOLDS)))
    for repo in sorted(df["repo"].unique()):
        sub = df[df["repo"] == repo]
        line = f"{repo:<28}"
        for n in FREQ_THRESHOLDS:
            vals = sub[f"freq{n}_gt_coverage"].dropna()
            mean_cov = vals.mean() if len(vals) else float("nan")
            line += f"  {mean_cov:>7.1f}%"
        print(line)

    # ── Section D: Combined approach ──────────────────────────────────────────
    print("\n\n── D. COMBINED: skip-dirs + freq filter  (mean tokens kept) ─────────────\n")
    print(f"{'repo':<28}  {'baseline':>8}" + "".join(f"  {'f>='+str(n):>8}" for n in FREQ_THRESHOLDS))
    print("-" * (28 + 10 + 11 * len(FREQ_THRESHOLDS)))
    for repo in sorted(df["repo"].unique()):
        sub = df[df["repo"] == repo]
        baseline = sub["total_tokens"].mean()
        line = f"{repo:<28}  {baseline:>8,.0f}"
        for n in FREQ_THRESHOLDS:
            mean_c = sub[f"combined{n}_tokens_kept"].mean()
            line += f"  {mean_c:>8,.0f}"
        print(line)
    print("-" * (28 + 10 + 11 * len(FREQ_THRESHOLDS)))
    baseline_mean = df["total_tokens"].mean()
    line = f"{'MEAN':<28}  {baseline_mean:>8,.0f}"
    for n in FREQ_THRESHOLDS:
        m = df[f"combined{n}_tokens_kept"].mean()
        pct = (1 - m / baseline_mean) * 100
        line += f"  {m:>8,.0f}"
    print(line)
    print()
    line = f"{'% reduction from baseline':<28}  {'':>8}"
    for n in FREQ_THRESHOLDS:
        m = df[f"combined{n}_tokens_kept"].mean()
        pct = (1 - m / baseline_mean) * 100
        line += f"  {pct:>7.1f}%"
    print(line)

    print(f"\nDetailed results → {out_csv}")


if __name__ == "__main__":
    main()
