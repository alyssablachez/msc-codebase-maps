"""
For each map type (structural / frequency / co-change) and each truncation
cap (no cap, 30k, 50k, 55k), compute the % of the 45 issues where at least
one scorable ground-truth file is actually present in that map at that cap.

Two things this deliberately does NOT reuse from existing CSVs:
- data/pruned_ground_truth_check*.csv only flags files *removed by pruning*
  -- a file the AST walker never emitted a record for in the first place
  (e.g. fastapi/20's background.py, a zero-def re-export file, invisible to
  the structural map at ANY budget including uncapped) never shows up as
  "pruned" there, so it would be silently miscounted as passing. This script
  checks actual file-list membership instead, which catches that case.
- ground_truth_scoring_check.csv's ground_truth_scored_against column still
  includes files later marked scored_but_unreachable_via_maps (out of
  package scope, e.g. fastapi/9's docs_src/... file) -- those are subtracted
  here to get the real scorable set the harness actually scores against.

Requires repo_maps/pruned_aux_maps_stats.csv (30k) and _50k.csv to exist --
generate via:
    python3 scripts/generate_pruned_aux_maps.py --token-budget 30000
    python3 scripts/generate_pruned_aux_maps.py --token-budget 50000
(55k and the structural 30k/50k/55k stats already existed.)

Usage:
    python3 figures/scripts/compute_gt_coverage_by_cap.py
"""
import json
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MAPS_ROOT = os.path.join(_ROOT, "repo_maps")
OUT_CSV = os.path.join(_ROOT, "figures", "data", "gt_coverage_by_cap.csv")

CAPS = ["no_cap", "30k", "50k", "55k"]
MAP_TYPES = ["structural", "frequency", "cochange"]

COMPACT_PRUNED_STATS = {
    "30k": "compact_pruned_stats.csv",
    "50k": "compact_pruned_stats_50k.csv",
    "55k": "compact_pruned_stats_55k.csv",
}
AUX_PRUNED_STATS = {
    "30k": "pruned_aux_maps_stats.csv",
    "50k": "pruned_aux_maps_stats_50k.csv",
    "55k": "pruned_aux_maps_stats_55k.csv",
}


def split_semicolon(val):
    if pd.isna(val) or not str(val).strip():
        return set()
    return set(str(val).split(";"))


def load_scorable_gt():
    """issue key (repo, issue_idx) -> set of scorable ground-truth files."""
    df = pd.read_csv(os.path.join(_ROOT, "data", "ground_truth_scoring_check.csv"))
    out = {}
    for _, row in df.iterrows():
        scored = split_semicolon(row["ground_truth_scored_against"])
        unreachable = split_semicolon(row["scored_but_unreachable_via_maps"])
        out[(row["repo"], row["issue_idx"])] = scored - unreachable
    return out


def ast_file_set(repo, issue_idx):
    path = os.path.join(MAPS_ROOT, repo, str(issue_idx), "ast_map.json")
    files = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            files.add(json.loads(line)["file"])
    return files


def freq_file_set(repo, issue_idx):
    path = os.path.join(MAPS_ROOT, repo, str(issue_idx), "freq_map.txt")
    files = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            files.add(line.split("  [")[0])
    return files


def cochange_file_set(repo, issue_idx):
    path = os.path.join(MAPS_ROOT, repo, str(issue_idx), "cochange_map.txt")
    files = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.startswith("→"):
                continue
            files.add(line)
    return files


def main():
    scorable_gt = load_scorable_gt()
    issues = sorted(scorable_gt.keys())

    compact_stats = {cap: pd.read_csv(os.path.join(MAPS_ROOT, fname)).set_index(["repo", "issue_idx"])
                      for cap, fname in COMPACT_PRUNED_STATS.items()}
    aux_stats = {cap: pd.read_csv(os.path.join(MAPS_ROOT, fname)).set_index(["repo", "issue_idx"])
                 for cap, fname in AUX_PRUNED_STATS.items()}

    rows = []
    for repo, issue_idx in issues:
        gt = scorable_gt[(repo, issue_idx)]
        if not gt:
            continue  # shouldn't happen for the 45 selected issues, but skip defensively

        ast_full = ast_file_set(repo, issue_idx)
        freq_full = freq_file_set(repo, issue_idx)
        cochange_full = cochange_file_set(repo, issue_idx)

        file_sets = {
            ("structural", "no_cap"): ast_full,
            ("frequency", "no_cap"): freq_full,
            ("cochange", "no_cap"): cochange_full,
        }
        for cap in ["30k", "50k", "55k"]:
            pruned = split_semicolon(compact_stats[cap].loc[(repo, issue_idx), "pruned_files"])
            file_sets[("structural", cap)] = ast_full - pruned

            aux_row = aux_stats[cap].loc[(repo, issue_idx)]
            freq_pruned = split_semicolon(aux_row["freq_pruned_files"])
            cochange_pruned = split_semicolon(aux_row["cochange_pruned_files"])
            file_sets[("frequency", cap)] = freq_full - freq_pruned
            file_sets[("cochange", cap)] = cochange_full - cochange_pruned

        for (map_type, cap), files in file_sets.items():
            passed = bool(gt & files)
            rows.append({
                "repo": repo, "issue_idx": issue_idx,
                "map_type": map_type, "cap": cap, "passed": passed,
            })

    df = pd.DataFrame(rows)
    summary = (
        df.groupby(["map_type", "cap"])["passed"]
        .agg(["sum", "count"])
        .reset_index()
        .rename(columns={"sum": "n_pass", "count": "n_total"})
    )
    summary["pct_pass"] = (summary["n_pass"] / summary["n_total"] * 100).round(1)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV.replace(".csv", "_detail.csv"), index=False)
    summary.to_csv(OUT_CSV, index=False)
    print(f"Saved: {OUT_CSV}")
    print(summary.to_string(index=False))

    fails = df[~df["passed"]]
    if len(fails):
        print("\nFailing (repo, issue, map_type, cap):")
        print(fails[["repo", "issue_idx", "map_type", "cap"]].to_string(index=False))


if __name__ == "__main__":
    main()
