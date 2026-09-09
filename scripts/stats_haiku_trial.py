"""
Stats for the standalone Haiku/transformers-27 caching trial
(haiku_trial/, isolated from the main study tree -- see
harness/run_trial.py's _is_claude_model/_system_message gate). Five
conditions, n=15 each except the placebo (n=14, one rep failed on an
Anthropic credit-balance error and was not re-run): no map, structural,
frequency, co-change (real map injected), co-change placebo (the same
framing/instructions injected, but the <codebase_map> content itself
replaced with a "no co-change history recorded" stub -- see
haiku_trial/maps_placebo/).

Same rationale as scripts/stats_study4_f1.py for method choice: F1 here
is tie-heavy (few achievable values given a 12-file ground truth), so
scipy's mannwhitneyu(method="auto") silently falls back to the
asymptotic normal approximation whenever ties are present -- pairwise
tests here use method="exact" explicitly, and every comparison also
gets an independent permutation-test cross-check (mean-difference
statistic, Monte Carlo resampled), which is exact w.r.t. ties by
construction and tests a distinct (location-shift) null rather than
merely repeating Mann-Whitney's rank-based one.

Unpaired throughout: no shared randomness links "rep N under no map" to
"rep N under cochange" (see stats_study4_config.py's docstring for the
same argument against pairing in this single-issue design).

Usage:
    python3 scripts/stats_haiku_trial.py
"""
import glob
import json
import os

import numpy as np
import pandas as pd
from scipy.stats import kruskal, mannwhitneyu, permutation_test
from statsmodels.stats.multitest import multipletests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(_ROOT, "haiku_trial", "results", "claude-haiku-4-5-20251001", "transformers", "27")
PLACEBO_DIR = os.path.join(_ROOT, "haiku_trial", "results_placebo", "claude-haiku-4-5-20251001", "transformers", "27")
OUT_DIR = os.path.join(_ROOT, "data", "stats_haiku_trial")
OUT_CSV_OMNIBUS = os.path.join(OUT_DIR, "haiku_trial_kruskal_omnibus.csv")
OUT_CSV_PAIRWISE = os.path.join(OUT_DIR, "haiku_trial_pairwise.csv")

CONDITIONS = {
    "no_map": (RESULTS_DIR, "none"),
    "structural": (RESULTS_DIR, "ast_compact"),
    "frequency": (RESULTS_DIR, "freq"),
    "cochange": (RESULTS_DIR, "cochange"),
    "placebo": (PLACEBO_DIR, "cochange"),
}
METRICS = ["precision", "recall", "f1"]

# The comparisons that answer the actual research questions -- not all
# 10 pairs across 5 conditions, which would just dilute Holm correction
# with comparisons nobody is asking about (e.g. structural vs. frequency).
PAIRS = [
    ("no_map", "structural"),
    ("no_map", "frequency"),
    ("no_map", "cochange"),
    ("no_map", "placebo"),
    ("cochange", "placebo"),
]

RNG = np.random.default_rng(20260904)
N_RESAMPLES = 99999


def _kruskal_stat(*groups):
    return kruskal(*groups).statistic


def _mean_diff(x, y):
    return np.mean(x) - np.mean(y)


def load_scores(base_dir, subdir):
    files = sorted(glob.glob(os.path.join(base_dir, subdir, "rep*.json")))
    rows = {m: [] for m in METRICS}
    for f in files:
        d = json.load(open(f))
        for m in METRICS:
            rows[m].append(d["scores"][m])
    return {m: np.array(v) for m, v in rows.items()}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    data = {name: load_scores(base, sub) for name, (base, sub) in CONDITIONS.items()}

    omnibus_rows = []
    pairwise_rows = []

    for metric in METRICS:
        groups = [data[name][metric] for name in CONDITIONS]
        stat, p = kruskal(*groups)
        if pd.isna(stat):
            perm_p = float("nan")
        else:
            perm_res = permutation_test(
                groups, _kruskal_stat, permutation_type="independent",
                alternative="greater", n_resamples=N_RESAMPLES, random_state=RNG,
            )
            perm_p = perm_res.pvalue
        omnibus_rows.append({
            "metric": metric, "n_groups": len(groups),
            "kruskal_stat": round(stat, 4) if not pd.isna(stat) else stat,
            "p_value_asymptotic": p, "p_value_permutation": perm_p,
        })

        metric_pair_rows = []
        for a, b in PAIRS:
            vals_a, vals_b = data[a][metric], data[b][metric]
            stat_auto, p_auto = mannwhitneyu(vals_a, vals_b, alternative="two-sided")
            _, p_exact = mannwhitneyu(vals_a, vals_b, alternative="two-sided", method="exact")
            perm_res = permutation_test(
                (vals_a, vals_b), _mean_diff, permutation_type="independent",
                alternative="two-sided", n_resamples=N_RESAMPLES, random_state=RNG,
            )
            metric_pair_rows.append({
                "metric": metric, "group_a": a, "group_b": b,
                "n_a": len(vals_a), "n_b": len(vals_b),
                "mean_a": round(vals_a.mean(), 4), "mean_b": round(vals_b.mean(), 4),
                "median_a": round(np.median(vals_a), 4), "median_b": round(np.median(vals_b), 4),
                "mean_diff": round(vals_a.mean() - vals_b.mean(), 4),
                "mannwhitney_u": stat_auto,
                "p_mwu_exact": p_exact, "p_mwu_asymptotic_auto": p_auto,
                "p_permutation": perm_res.pvalue,
            })
        pair_df = pd.DataFrame(metric_pair_rows)
        pair_df["p_holm"] = multipletests(pair_df["p_mwu_exact"], method="holm")[1]
        pairwise_rows.append(pair_df)

    omnibus_df = pd.DataFrame(omnibus_rows)
    pairwise_df = pd.concat(pairwise_rows, ignore_index=True)

    omnibus_df.to_csv(OUT_CSV_OMNIBUS, index=False)
    pairwise_df.to_csv(OUT_CSV_PAIRWISE, index=False)

    print("=== Kruskal-Wallis omnibus across all 5 conditions, per metric, with permutation cross-check ===")
    print(omnibus_df.to_string(index=False))
    print("\n=== Pairwise Mann-Whitney U (exact), Holm-corrected within metric, with permutation cross-check ===")
    print(pairwise_df.to_string(index=False))
    print(f"\nSaved -> {OUT_CSV_OMNIBUS}")
    print(f"Saved -> {OUT_CSV_PAIRWISE}")


if __name__ == "__main__":
    main()
