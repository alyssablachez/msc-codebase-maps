"""
Per-repo LoC and issue-count stats across the full MULocBench benchmark
(46 repos with usable LoC data, not just this study's panel), for
recreating the "Issues vs Codebase Size" scatter from the original
explore_dataset.ipynb MULocBench exploration.

Each repo is classified into exactly one panel-membership category, final
panel taking priority where a repo is in both:
- "Final Panel"    -- one of the 15 repos in the current issue_selection_final.csv
- "Original Panel" -- one of the 15 repos in the pre-2026-07-12-swap panel,
                       but NOT also in the final panel (i.e. just
                       Deep-Live-Cam and open-interpreter)
- "Never Included" -- everything else in MULocBench

LoC: study_0/results/loc_data.json (per-repo total LoC, computed once when
the full MULocBench repo set was first cloned -- same source the original
notebook cells used, not re-derived).
Issue counts: value_counts() over the full MULocBench pickle.

Usage:
    python3 figures/scripts/compute_mulocbench_repo_stats.py
"""
import json
import os
import pickle

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_CSV = os.path.join(_ROOT, "figures", "data", "mulocbench_repo_stats.csv")

FINAL_PANEL = {
    "requests", "thefuck", "flask", "gpt-engineer", "fastapi", "scrapy", "rich",
    "stable-diffusion-webui", "keras", "localstack", "yt-dlp", "pandas",
    "scikit-learn", "transformers", "core",
}
ORIGINAL_PANEL = FINAL_PANEL | {"Deep-Live-Cam", "open-interpreter"}
ORIGINAL_PANEL -= {"transformers", "core"}  # these weren't in the original panel


def classify(repo):
    if repo in FINAL_PANEL:
        return "Final Panel"
    if repo in ORIGINAL_PANEL:
        return "Original Panel"
    return "Never Included"


def main():
    with open(os.path.join(_ROOT, "study_0", "results", "loc_data.json")) as f:
        loc_data = json.load(f)

    with open(os.path.join(_ROOT, "data", "all_issues_with_pr_commit_comment_all_project_0922.pkl"), "rb") as f:
        df = pd.DataFrame(pickle.load(f))
    issue_counts = df["repo_name"].value_counts()

    loc_series = pd.Series(loc_data)
    plot_df = pd.DataFrame({"issues": issue_counts, "loc": loc_series}).dropna()
    plot_df = plot_df[plot_df["loc"] > 0]
    plot_df.index.name = "repo"
    plot_df = plot_df.reset_index()
    plot_df["category"] = plot_df["repo"].apply(classify)

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    plot_df.to_csv(OUT_CSV, index=False)
    print(f"Saved: {OUT_CSV}  ({len(plot_df)} repos)")
    print(plot_df["category"].value_counts())
    print()
    print(plot_df[plot_df["category"] != "Never Included"].sort_values("category").to_string(index=False))


if __name__ == "__main__":
    main()
