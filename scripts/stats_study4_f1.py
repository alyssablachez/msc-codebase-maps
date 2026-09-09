"""
Study 4 -- F1 comparison, condition vs. baseline, for every (issue,
model) cell in the expanded-replication program. Unpaired, same
rationale as scripts/stats_study4_success_fishers.py.

For issues with a single non-baseline condition, Mann-Whitney U is used
directly (the 2-group case Kruskal-Wallis reduces to). For issues with 3+
conditions, a Kruskal-Wallis omnibus is run first (does F1 differ across
baseline + all conditions at all), then pairwise Mann-Whitney U vs.
baseline with Holm correction as the post-hoc -- the nonparametric
equivalent of Kruskal-Wallis + Dunn's test, using only tools already in
this project's dependency set (no scikit-posthocs needed).

F1 in this data is tie-heavy (each issue only has a handful of achievable
F1 values -- e.g. scikit-learn/45 is only ever 0 or .667), which matters
because scipy's mannwhitneyu(method="auto") silently falls back to the
asymptotic normal approximation whenever ties are present. Confirmed by a
direct reproduction (scikit-learn/45 Ministral, freq vs. none):
method="auto" gives p=.00325, identical to method="asymptotic", while
method="exact" gives p=.0295 -- an order of magnitude larger, large
enough to flip a Holm-corrected significance call. So the pairwise tests
below use method="exact" explicitly instead of trusting the default.

Each pairwise comparison also gets an independent permutation-test
cross-check (mean-difference statistic, Monte Carlo resampled) -- exact
w.r.t. ties by construction since it resamples the actual observed
values, and it tests a distinct (location-shift) null rather than merely
repeating Mann-Whitney's rank-based one. The Kruskal-Wallis omnibus (no
native exact/permutation mode in scipy) gets the same kind of
permutation cross-check on its H statistic.

Usage:
    python3 scripts/stats_study4_f1.py
"""
import os

import numpy as np
import pandas as pd
from scipy.stats import kruskal, mannwhitneyu, permutation_test
from statsmodels.stats.multitest import multipletests

from stats_study4_config import ISSUES, MODEL_LABELS

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study4")
OUT_CSV_OMNIBUS = os.path.join(OUT_DIR, "study4_f1_kruskal_omnibus.csv")
OUT_CSV_POSTHOC = os.path.join(OUT_DIR, "study4_f1_posthoc_vs_baseline.csv")

RNG = np.random.default_rng(20260825)
N_RESAMPLES = 9999


def _kruskal_stat(*groups):
    return kruskal(*groups).statistic


def _mean_diff(x, y):
    return np.mean(x) - np.mean(y)


def get_f1(df, repo, issue_idx, model, condition):
    sub = df[(df["repo"] == repo) & (df["issue_idx"] == issue_idx) &
            (df["model"] == model) & (df["map_condition_raw"] == condition)]
    return sub["f1"].dropna().values


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_pickle(DATA_PKL)

    omnibus_rows = []
    posthoc_rows = []

    for (repo, issue_idx), cfg in ISSUES.items():
        for model in cfg["models"]:
            base_vals = get_f1(df, repo, issue_idx, model, cfg["baseline"])
            cond_vals = {c: get_f1(df, repo, issue_idx, model, c) for c in cfg["conditions"]}

            if len(cfg["conditions"]) >= 3:
                groups = [base_vals] + list(cond_vals.values())
                stat, p = kruskal(*groups)
                # kruskal_stat is NaN when every group is a single repeated
                # value (zero variance everywhere, e.g. F1==0 in every
                # trial): the tie-correction divides by zero. NaN never
                # compares >= to anything, so a naive permutation_test call
                # here would silently count zero "as extreme" resamples and
                # report a spurious near-zero p-value instead of "no test
                # possible" -- so skip it explicitly in that case.
                if pd.isna(stat):
                    perm_p = float("nan")
                else:
                    perm_res = permutation_test(
                        groups, _kruskal_stat, permutation_type="independent",
                        alternative="greater", n_resamples=N_RESAMPLES, random_state=RNG,
                    )
                    perm_p = perm_res.pvalue
                omnibus_rows.append({
                    "issue": f"{repo}/{issue_idx}", "model": MODEL_LABELS[model],
                    "n_groups": len(groups), "kruskal_stat": round(stat, 4) if not pd.isna(stat) else stat,
                    "p_value_asymptotic": p, "p_value_permutation": perm_p,
                })

            group_rows = []
            for cond, vals in cond_vals.items():
                if len(vals) == 0 or len(base_vals) == 0:
                    continue
                stat_auto, p_auto = mannwhitneyu(vals, base_vals, alternative="two-sided")
                _, p_exact = mannwhitneyu(vals, base_vals, alternative="two-sided", method="exact")
                perm_res = permutation_test(
                    (vals, base_vals), _mean_diff, permutation_type="independent",
                    alternative="two-sided", n_resamples=N_RESAMPLES, random_state=RNG,
                )
                group_rows.append({
                    "issue": f"{repo}/{issue_idx}", "model": MODEL_LABELS[model],
                    "condition": cond, "baseline": cfg["baseline"],
                    "n_condition": len(vals), "n_baseline": len(base_vals),
                    "median_condition": round(pd.Series(vals).median(), 4),
                    "median_baseline": round(pd.Series(base_vals).median(), 4),
                    "mannwhitney_u": stat_auto,
                    "p_mwu_exact": p_exact, "p_mwu_asymptotic_auto": p_auto,
                    "p_permutation": perm_res.pvalue,
                })
            group_df = pd.DataFrame(group_rows)
            if len(group_df) > 1:
                group_df["p_holm"] = multipletests(group_df["p_mwu_exact"], method="holm")[1]
            elif len(group_df) == 1:
                group_df["p_holm"] = group_df["p_mwu_exact"]
            if len(group_df):
                posthoc_rows.append(group_df)

    omnibus_df = pd.DataFrame(omnibus_rows)
    posthoc_df = pd.concat(posthoc_rows, ignore_index=True)

    print("=== Kruskal-Wallis omnibus (issues with 3+ conditions), with permutation cross-check ===")
    print(omnibus_df.to_string(index=False))
    print("\n=== Pairwise Mann-Whitney U (exact) vs. baseline, Holm-corrected within issue+model, "
          "with permutation cross-check ===")
    print(posthoc_df.to_string(index=False))

    omnibus_df.to_csv(OUT_CSV_OMNIBUS, index=False)
    posthoc_df.to_csv(OUT_CSV_POSTHOC, index=False)
    print(f"\nSaved: {OUT_CSV_OMNIBUS}")
    print(f"Saved: {OUT_CSV_POSTHOC}")


if __name__ == "__main__":
    main()
