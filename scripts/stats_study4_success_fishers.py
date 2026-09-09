"""
Study 4 -- Fisher's exact test on two binary outcomes, condition vs.
baseline, for every (issue, model) cell in the expanded-replication
program: `success` (recall==1.0, the project-wide convention) and
`complete_miss` (F1==0, found none of the ground-truth files). Both are
computed for every issue rather than picking one per issue, because
`success` turns out to be a dead metric for issues with larger
ground-truth file counts -- localstack/19 (7 files) never reaches
recall==1.0 even in its best-ever baseline trial (max F1=0.444), and
scikit-learn/45 (2 files) essentially never does for Ministral-3B either
(F1 caps at 0.667) -- so a `success`-only test would silently return a
meaningless all-zero null for exactly the issues where the real DEVLOG-
documented pattern (a spike in complete misses under one condition) is
otherwise clearly visible in the raw F1 values. `complete_miss` has no
such ceiling problem regardless of ground-truth size, so it's reported
alongside `success` for every issue rather than only the two flagged
ones -- issues with single-file ground truth (flask/18, gpt-engineer/9,
keras/5, localstack/2) are expected to show consistent stories on both.

Unpaired by design (see scripts/stats_study4_config.py's docstring for
why). Uses ALL reps for the targeted cells (rep 1-15, not just the +12
expanded ones), since the whole point of the program is the combined
n=15 sample.

Holm correction applied within each (issue, model, outcome) group --
that's the natural family of comparisons per the DEVLOG's own scoping.

Usage:
    python3 scripts/stats_study4_success_fishers.py
"""
import os

import pandas as pd
from scipy.stats import fisher_exact
from statsmodels.stats.multitest import multipletests

from stats_study4_config import ISSUES, MODEL_LABELS

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study4")
OUT_CSV = os.path.join(OUT_DIR, "study4_success_fishers_exact.csv")

OUTCOMES = ["success", "complete_miss"]


def contingency(df, repo, issue_idx, model, condition, ref_condition, outcome_col):
    sub = df[(df["repo"] == repo) & (df["issue_idx"] == issue_idx) & (df["model"] == model)]
    a = sub[sub["map_condition_raw"] == condition][outcome_col]
    b = sub[sub["map_condition_raw"] == ref_condition][outcome_col]
    table = [
        [int((a == True).sum()), int((a == False).sum())],
        [int((b == True).sum()), int((b == False).sum())],
    ]
    return table, len(a), len(b)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_pickle(DATA_PKL)
    df = df.dropna(subset=["success", "f1"]).copy()
    df["complete_miss"] = df["f1"] == 0.0

    rows = []
    for (repo, issue_idx), cfg in ISSUES.items():
        for model in cfg["models"]:
            for outcome_col in OUTCOMES:
                group_rows = []
                for cond in cfg["conditions"]:
                    table, n_cond, n_base = contingency(df, repo, issue_idx, model, cond, cfg["baseline"], outcome_col)
                    odds_ratio, p = fisher_exact(table)
                    group_rows.append({
                        "issue": f"{repo}/{issue_idx}", "model": MODEL_LABELS[model],
                        "outcome": outcome_col, "condition": cond, "baseline": cfg["baseline"],
                        "n_condition": n_cond, "n_baseline": n_base,
                        "condition_count": table[0][0], "baseline_count": table[1][0],
                        "condition_rate": round(table[0][0] / n_cond, 3) if n_cond else None,
                        "baseline_rate": round(table[1][0] / n_base, 3) if n_base else None,
                        "odds_ratio": round(odds_ratio, 4) if odds_ratio not in (float("inf"),) else odds_ratio,
                        "p_raw": p,
                    })
                group_df = pd.DataFrame(group_rows)
                if len(group_df) > 1:
                    group_df["p_holm"] = multipletests(group_df["p_raw"], method="holm")[1]
                else:
                    group_df["p_holm"] = group_df["p_raw"]
                rows.append(group_df)

    result = pd.concat(rows, ignore_index=True)
    print(result.to_string(index=False))
    result.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")


if __name__ == "__main__":
    main()
