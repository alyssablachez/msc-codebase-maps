"""
Study 4 -- Fisher's exact test on "explored" (did the trial ever touch
at least one ground-truth file, per stats_study4_touch_timing_common.py),
condition vs. baseline, for every (issue, model) cell in the expanded-
replication program. Same design as stats_study4_success_fishers.py
(Holm correction within issue+model), different outcome and a different
source table (data/gt_file_touch_timing.csv rather than
compiled_results_combined.pkl's f1/success columns).

Motivated directly by the keras/5 investigation this session: Nemotron
touches the ground-truth file in 100% of trials regardless of condition
there, so its whole map effect turned out to be about submission
reliability, not discovery -- "explored" makes that distinction visible
as a first-class metric instead of something that has to be checked by
hand per issue.

Usage:
    python3 scripts/stats_study4_explored_fishers.py
"""
import os

import pandas as pd
from scipy.stats import fisher_exact
from statsmodels.stats.multitest import multipletests

from stats_study4_config import ISSUES, MODEL_LABELS
from stats_study4_touch_timing_common import load_per_trial_touch_data

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_ROOT, "data", "stats_study4")
OUT_CSV = os.path.join(OUT_DIR, "study4_explored_fishers_exact.csv")


def contingency(df, repo, issue_idx, model, condition, ref_condition):
    sub = df[(df["repo"] == repo) & (df["issue_idx"] == issue_idx) & (df["model"] == model)]
    a = sub[sub["map_condition_raw"] == condition]["explored"]
    b = sub[sub["map_condition_raw"] == ref_condition]["explored"]
    table = [
        [int((a == True).sum()), int((a == False).sum())],
        [int((b == True).sum()), int((b == False).sum())],
    ]
    return table, len(a), len(b)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_per_trial_touch_data()

    rows = []
    for (repo, issue_idx), cfg in ISSUES.items():
        for model in cfg["models"]:
            group_rows = []
            for cond in cfg["conditions"]:
                table, n_cond, n_base = contingency(df, repo, issue_idx, model, cond, cfg["baseline"])
                odds_ratio, p = fisher_exact(table)
                group_rows.append({
                    "issue": f"{repo}/{issue_idx}", "model": MODEL_LABELS[model],
                    "condition": cond, "baseline": cfg["baseline"],
                    "n_condition": n_cond, "n_baseline": n_base,
                    "condition_explored": table[0][0], "baseline_explored": table[1][0],
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
