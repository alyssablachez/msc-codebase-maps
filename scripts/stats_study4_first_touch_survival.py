"""
Study 4 -- time-to-first-touch of the ground-truth file, condition vs.
baseline, for every (issue, model) cell. Uses the Kaplan-Meier estimator
+ log-rank test (lifelines) rather than Mann-Whitney/Kruskal-Wallis,
because "never touched" is not a missing value -- it's right-censoring
(we know the event didn't happen within that specific trial's own
turns_used, not that its timing is unknown). Dropping those trials would
throw away exactly the cases where a map's effect is largest (if a map
cuts the never-found rate in half, that's the headline effect); treating
"never touched" as a huge/arbitrary turn number would fabricate a false
tail. Log-rank is the standard nonparametric test for this shape, the
direct survival-analysis analog of what Mann-Whitney does for
uncensored data -- consistent with this project's nonparametric-first
approach throughout the rest of the stats battery.

See scripts/stats_study4_touch_timing_common.py for exactly how
"duration" and "event_observed" (explored) are built per trial.

Usage:
    python3 scripts/stats_study4_first_touch_survival.py
"""
import os

import pandas as pd
from lifelines.statistics import logrank_test
from statsmodels.stats.multitest import multipletests

from stats_study4_config import ISSUES, MODEL_LABELS
from stats_study4_touch_timing_common import load_per_trial_touch_data

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_ROOT, "data", "stats_study4")
OUT_CSV = os.path.join(OUT_DIR, "study4_first_touch_logrank.csv")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_per_trial_touch_data()

    rows = []
    for (repo, issue_idx), cfg in ISSUES.items():
        for model in cfg["models"]:
            sub = df[(df["repo"] == repo) & (df["issue_idx"] == issue_idx) & (df["model"] == model)]
            base = sub[sub["map_condition_raw"] == cfg["baseline"]]
            if base.empty:
                continue

            group_rows = []
            for cond in cfg["conditions"]:
                condg = sub[sub["map_condition_raw"] == cond]
                if condg.empty:
                    continue
                res = logrank_test(
                    condg["duration"], base["duration"],
                    event_observed_A=condg["explored"], event_observed_B=base["explored"],
                )
                group_rows.append({
                    "issue": f"{repo}/{issue_idx}", "model": MODEL_LABELS[model],
                    "condition": cond, "baseline": cfg["baseline"],
                    "n_condition": len(condg), "n_baseline": len(base),
                    "median_first_touch_condition": condg.loc[condg["explored"], "duration"].median(),
                    "median_first_touch_baseline": base.loc[base["explored"], "duration"].median(),
                    "explored_rate_condition": round(condg["explored"].mean(), 3),
                    "explored_rate_baseline": round(base["explored"].mean(), 3),
                    "logrank_stat": round(res.test_statistic, 4),
                    "p_raw": res.p_value,
                })
            group_df = pd.DataFrame(group_rows)
            if len(group_df) > 1:
                group_df["p_holm"] = multipletests(group_df["p_raw"], method="holm")[1]
            elif len(group_df) == 1:
                group_df["p_holm"] = group_df["p_raw"]
            if len(group_df):
                rows.append(group_df)

    result = pd.concat(rows, ignore_index=True)
    print(result.to_string(index=False))
    result.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")


if __name__ == "__main__":
    main()
