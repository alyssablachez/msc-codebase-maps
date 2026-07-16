"""
Size/spread statistics for the full, path-indexed maps
(ast_index_full.json / freq_index_full.json / cochange_index_full.json,
see generate_all_indexes.py) across all 45 selected issues -- one row per
map type in repo_maps/index_size_stats.csv, plus a per-issue companion
detail CSV (repo_maps/index_size_stats_per_issue.csv) for drilling into
specific outliers.

Token counts use chars // 4, the same estimation convention as
generate_ast_map.py / compact_map.py elsewhere in this project (no
tokenizer dependency).

"Per-file" here means: if an agent looked up a single file's record
through a future retrieval tool, how many tokens would that one response
cost -- the distribution that actually matters for tool/budget design, as
opposed to the whole-index total (which is never loaded in full at trial
time).

Usage:
    python3 scripts/index_size_stats.py
    python3 scripts/index_size_stats.py --out repo_maps/index_size_stats.csv
"""
import argparse
import json
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_MAPS = os.path.join(_ROOT, "repo_maps")
SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")
OLD_STATS_CSV = os.path.join(REPO_MAPS, "map_generation_stats.csv")

MAP_TYPES = ["ast", "freq", "cochange"]
FNAME = {
    "ast": "ast_index_full.json",
    "freq": "freq_index_full.json",
    "cochange": "cochange_index_full.json",
}
# Old budget-capped map this full index replaces, for the blow-up comparison
# -- "ast" here maps to the *compact* (post-pruning) token count, since
# that's what was actually injected into a trial's context, not the raw
# pre-compaction ast_map.
OLD_TOKEN_COL = {
    "ast": "compact_map_tokens",
    "freq": "freq_map_tokens",
    "cochange": "cochange_map_tokens",
}

DEFAULT_OUT = os.path.join(REPO_MAPS, "index_size_stats.csv")
PERCENTILES = [0.5, 0.75, 0.9, 0.95, 0.99]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    issues = pd.read_csv(SEL_CSV)
    issue_keys = list(zip(issues["repo"], issues["issue_idx"].astype(int)))
    old_stats = pd.read_csv(OLD_STATS_CSV).set_index(["repo", "issue_idx"])

    per_issue_rows = []
    per_file_records = {mt: [] for mt in MAP_TYPES}  # mt -> list of (repo, issue_idx, file, tokens)

    for repo, issue_idx in issue_keys:
        for mt in MAP_TYPES:
            path = os.path.join(REPO_MAPS, repo, str(issue_idx), FNAME[mt])
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            total_tokens = os.path.getsize(path) // 4
            per_issue_rows.append({
                "repo": repo, "issue_idx": issue_idx, "map_type": mt,
                "n_files": len(d), "whole_index_tokens": total_tokens,
            })
            for fpath, record in d.items():
                rec_tokens = len(json.dumps(record)) // 4
                per_file_records[mt].append((repo, issue_idx, fpath, rec_tokens))

    df_issue = pd.DataFrame(per_issue_rows)
    df_issue.to_csv(args.out.replace(".csv", "_per_issue.csv"), index=False)

    summary_rows = []
    for mt in MAP_TYPES:
        idx_sub = df_issue[df_issue["map_type"] == mt]
        file_sub = pd.DataFrame(per_file_records[mt], columns=["repo", "issue_idx", "file", "tokens"])

        worst_issue = idx_sub.loc[idx_sub["whole_index_tokens"].idxmax()]
        worst_file = file_sub.loc[file_sub["tokens"].idxmax()]

        pctl = file_sub["tokens"].quantile(PERCENTILES)

        old_col = OLD_TOKEN_COL[mt]
        old_mean = old_stats[old_col].mean() if old_col in old_stats.columns else None
        new_mean = idx_sub["whole_index_tokens"].mean()

        row = {
            "map_type": mt,
            "n_issues": len(idx_sub),
            "n_files_total": len(file_sub),
            # whole-index size (all files in one issue's map, summed/aggregated
            # across the 45 issues) -- context, not what a trial ever loads whole
            "whole_index_total_tokens": int(idx_sub["whole_index_tokens"].sum()),
            "whole_index_mean_tokens": round(new_mean, 1),
            "whole_index_median_tokens": idx_sub["whole_index_tokens"].median(),
            "whole_index_max_tokens": int(worst_issue["whole_index_tokens"]),
            "whole_index_max_issue": f"{worst_issue['repo']}/{worst_issue['issue_idx']}",
            # per-file (per-query) response size -- the distribution that
            # matters for a tool-based lookup's per-call budget
            "per_file_mean_tokens": round(file_sub["tokens"].mean(), 1),
            "per_file_median_tokens": round(pctl[0.5], 1),
            "per_file_std_tokens": round(file_sub["tokens"].std(), 1),
            "per_file_p75_tokens": round(pctl[0.75], 1),
            "per_file_p90_tokens": round(pctl[0.9], 1),
            "per_file_p95_tokens": round(pctl[0.95], 1),
            "per_file_p99_tokens": round(pctl[0.99], 1),
            "per_file_max_tokens": int(worst_file["tokens"]),
            "per_file_max_record": f"{worst_file['repo']}/{worst_file['issue_idx']}:{worst_file['file']}",
            # blow-up vs. the old 55k-token-budgeted map this replaces
            "old_budget_capped_mean_tokens": round(old_mean, 1) if old_mean is not None else None,
            "mean_blowup_vs_old_budget": round(new_mean / old_mean, 1) if old_mean else None,
            "max_blowup_vs_old_budget": (
                round(int(worst_issue["whole_index_tokens"]) /
                      old_stats.loc[(worst_issue["repo"], worst_issue["issue_idx"]), old_col], 1)
                if old_col in old_stats.columns else None
            ),
        }
        summary_rows.append(row)

    df_summary = pd.DataFrame(summary_rows)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    df_summary.to_csv(args.out, index=False)

    print(df_summary.to_string(index=False))
    print(f"\nSaved summary -> {args.out}")
    print(f"Saved per-issue detail -> {args.out.replace('.csv', '_per_issue.csv')}")


if __name__ == "__main__":
    main()
