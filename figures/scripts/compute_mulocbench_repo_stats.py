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

LoC: study_0/results/loc_by_language.json's '.py' entry per repo -- NOT
loc_data.json, which this script used originally. loc_data.json's
provenance turned out to be unrecoverable (the notebook cell that computed
it no longer exists anywhere in history), and cross-checking its values
against loc_by_language.json showed at least one repo (screenshot-to-code)
off by 3x in a way that lines up almost exactly with that repo's %Python
-- strong evidence loc_data.json was silently Python-only despite being
used as if it were whole-repo LoC. loc_by_language.json's method is known
and reproducible (count_loc_by_language() in explore_dataset.ipynb:
non-blank lines, walked on-disk, per extension), so its '.py' value is
used here as Python LoC specifically, consistent with what every other
LoC figure in this project actually means by "LoC" (Python source only).
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
    with open(os.path.join(_ROOT, "study_0", "results", "loc_by_language.json")) as f:
        loc_by_language = json.load(f)
    loc_data = {repo: langs.get(".py", 0) for repo, langs in loc_by_language.items()}

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
