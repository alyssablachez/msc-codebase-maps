"""
Study 0 Goal 3 -- statistical comparison of the three map conditions
(none / ast / ast_compact) on performance (F1, precision, recall) and
efficiency (input/cached/output tokens, wall time, cost) metrics.

Design: all three map conditions were run on the same (model, task_idx,
rep) triples, so this is a matched repeated-measures design, not
independent samples -- every test here is paired/related-samples, which
is what removes model/task/rep variance from the comparison rather than
letting it dilute the map-type signal.

Per metric:
  1. Friedman test (omnibus, 3 related samples) -- is map condition
     associated with the metric at all, before asking which pairwise
     contrast drives it.
  2. Wilcoxon signed-rank test on all three pairwise contrasts (ast vs.
     none, ast_compact vs. none, ast vs. ast_compact) -- not just the one
     contrast you'd expect to matter, so a real ast_compact-vs-none
     difference can't get silently skipped just because ast-vs-none was
     the obvious question. Holm-Bonferroni applied within each metric's
     3 pairwise tests (its own test family), not pooled across unrelated
     metrics -- matches the "Holm-Bonferroni within each test family"
     convention already used for Studies 1-3's stats plan.
  3. A separate, uncorrected per-model direction table (median paired
     difference and its sign, no p-values) -- a pooled test can hide a
     case where a map condition helps half the models and hurts the
     other half; this is a cheap sanity check for that, not a third
     formal test.

Effect size for each Wilcoxon test is the matched-pairs rank-biserial
correlation (sum of positive-difference ranks minus sum of negative-
difference ranks, over their total) -- scipy's wilcoxon() doesn't return
an effect size directly, so it's computed by hand from the same ranks
the test itself uses.

Reads study_0/results_all.csv directly (already collated by
scripts/collate_results.py -- no separate compute step needed here).
Writes:
  study_0/map_comparison_friedman.csv  -- omnibus test, one row per metric
  study_0/map_comparison_wilcoxon.csv  -- pairwise tests, one row per
                                          metric x comparison
  study_0/map_comparison_by_model.csv  -- per-model direction check, one
                                          row per model x metric x
                                          comparison, no p-values

Usage:
    python3 scripts/compute_study0_map_comparison_stats.py
"""
import os

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_CSV = os.path.join(_ROOT, "study_0", "results_all.csv")
OUT_FRIEDMAN = os.path.join(_ROOT, "study_0", "map_comparison_friedman.csv")
OUT_WILCOXON = os.path.join(_ROOT, "study_0", "map_comparison_wilcoxon.csv")
OUT_BY_MODEL = os.path.join(_ROOT, "study_0", "map_comparison_by_model.csv")

MAP_CONDITIONS = ["none", "ast", "ast_compact"]
PAIRWISE_COMPARISONS = [("ast", "none"), ("ast_compact", "none"), ("ast", "ast_compact")]

METRICS = {
    "f1":            "F1",
    "precision":     "Precision",
    "recall":        "Recall",
    "input_tokens":  "Input tokens",
    "cached_tokens": "Cached tokens",
    "output_tokens": "Output tokens",
    "turns":         "Turns",
    "wall_time":     "Wall time (s)",
    "cost_usd":      "Cost (USD)",
}


def wilcoxon_effect_size(diff):
    """Matched-pairs rank-biserial correlation from the same signed ranks
    scipy.stats.wilcoxon uses internally (zero differences excluded, same
    as the test's own default zero_method='wilcox')."""
    diff = diff[diff != 0]
    if len(diff) == 0:
        return np.nan
    ranks = stats.rankdata(np.abs(diff))
    w_pos = ranks[diff > 0].sum()
    w_neg = ranks[diff < 0].sum()
    return (w_pos - w_neg) / (w_pos + w_neg)


def pivot_metric(df, metric):
    """Wide-format (model_short, task_idx, rep) x map_type, one metric.
    Rows missing any of the 3 conditions are dropped -- Friedman/Wilcoxon
    both require complete matched triples."""
    wide = df.pivot_table(index=["model_short", "task_idx", "rep"],
                          columns="map_type", values=metric)
    return wide.dropna(subset=MAP_CONDITIONS)


def compute_friedman(df):
    rows = []
    for metric, label in METRICS.items():
        wide = pivot_metric(df, metric)
        stat, p = stats.friedmanchisquare(wide["none"], wide["ast"], wide["ast_compact"])
        rows.append({"metric": metric, "label": label, "n_triples": len(wide),
                     "friedman_stat": stat, "p_value": p})
    return pd.DataFrame(rows)


def compute_wilcoxon(df):
    rows = []
    for metric, label in METRICS.items():
        wide = pivot_metric(df, metric)
        metric_rows = []
        for a, b in PAIRWISE_COMPARISONS:
            diff = wide[a] - wide[b]
            n_nonzero = int((diff != 0).sum())
            try:
                w_stat, p_raw = stats.wilcoxon(wide[a], wide[b])
            except ValueError:
                # All paired differences are zero -- e.g. a metric that's
                # identical across map conditions for every matched triple.
                w_stat, p_raw = np.nan, np.nan
            metric_rows.append({
                "metric": metric, "label": label, "comparison": f"{a}_vs_{b}",
                "n_triples": len(wide), "n_nonzero_diff": n_nonzero,
                "median_diff": diff.median(), "wilcoxon_stat": w_stat,
                "p_raw": p_raw, "effect_size_r": wilcoxon_effect_size(diff.values),
            })
        # Holm-Bonferroni within this metric's 3 pairwise tests only.
        pvals = [r["p_raw"] for r in metric_rows]
        valid = [i for i, p in enumerate(pvals) if pd.notna(p)]
        p_holm = [np.nan] * len(pvals)
        if valid:
            _, corrected, _, _ = multipletests([pvals[i] for i in valid], method="holm")
            for i, c in zip(valid, corrected):
                p_holm[i] = c
        for r, ph in zip(metric_rows, p_holm):
            r["p_holm"] = ph
        rows.extend(metric_rows)
    return pd.DataFrame(rows)


def compute_by_model(df):
    rows = []
    for metric, label in METRICS.items():
        wide = pivot_metric(df, metric)
        for model_short, sub in wide.groupby(level="model_short"):
            for a, b in PAIRWISE_COMPARISONS:
                diff = sub[a] - sub[b]
                median_diff = diff.median()
                sign = "zero" if median_diff == 0 else ("positive" if median_diff > 0 else "negative")
                rows.append({
                    "model_short": model_short, "metric": metric, "label": label,
                    "comparison": f"{a}_vs_{b}", "n_triples": len(sub),
                    "median_diff": median_diff, "sign": sign,
                })
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(RESULTS_CSV)
    df = df[df["map_type"].isin(MAP_CONDITIONS)]

    friedman_df = compute_friedman(df)
    wilcoxon_df = compute_wilcoxon(df)
    by_model_df = compute_by_model(df)

    for c in ["friedman_stat", "p_value"]:
        friedman_df[c] = friedman_df[c].round(6)
    for c in ["median_diff", "wilcoxon_stat", "p_raw", "p_holm", "effect_size_r"]:
        wilcoxon_df[c] = wilcoxon_df[c].round(6)
    by_model_df["median_diff"] = by_model_df["median_diff"].round(6)

    friedman_df.to_csv(OUT_FRIEDMAN, index=False)
    wilcoxon_df.to_csv(OUT_WILCOXON, index=False)
    by_model_df.to_csv(OUT_BY_MODEL, index=False)

    print(f"Saved: {OUT_FRIEDMAN}")
    print(f"Saved: {OUT_WILCOXON}")
    print(f"Saved: {OUT_BY_MODEL}")

    print("\nFriedman omnibus (map condition effect, per metric):")
    print(friedman_df.to_string(index=False))

    print("\nWilcoxon pairwise (Holm-corrected within each metric):")
    print(wilcoxon_df.to_string(index=False))


if __name__ == "__main__":
    main()
