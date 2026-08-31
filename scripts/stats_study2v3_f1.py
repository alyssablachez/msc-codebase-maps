"""
Study 2 vs. Study 3 direct comparison, F1 side -- the nonparametric
robustness check alongside scripts/stats_study2v3_r_glmm.R's GLMM.
Unlike the per-study F1 scripts (which match trials across map
conditions), here each (model, issue, rep, map_condition) unit is matched
across submission_mode (voluntary vs. required) -- the same trial
configuration, just with tool use optional vs. mandated.

Only a pooled Wilcoxon signed-rank is needed (not Friedman): with exactly
2 levels being compared, there's no omnibus test to run first. Reported
pooled, per map_condition (does "required" matter more for some map
tools than others), and per model.

Usage:
    python3 scripts/stats_study2v3_f1.py
"""
import os

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from stats_common import matched_wide, wilcoxon_effect_size

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study2v3")

MODE_ORDER = ["voluntary", "required"]
MAP_CONDITIONS = ["structural", "temporal_frequency", "temporal_cochange", "all_tools"]

MODEL_SHORT = {
    "mistral/ministral-3b-latest":                          "ministral-3b",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b":  "gpt-oss-120b",
    "deepseek/deepseek-v4-flash":                            "deepseek-flash",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B":   "nemotron-super",
}


def load_2v3_data():
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["rep"] <= 3) & (df["study"].isin([2, 3]))].copy()
    df = df.dropna(subset=["f1"])
    df["model_short"] = df["model"].map(MODEL_SHORT)
    return df


def _wide(df):
    return matched_wide(df, MODE_ORDER, "f1", index_cols=("model_short", "issue_id", "rep", "map_condition"),
                        pivot_col="submission_mode")


def run_wilcoxon_pooled(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank, F1, required vs. voluntary (pooled)\n{'='*70}")
    wide = _wide(df)
    diff = wide["required"] - wide["voluntary"]
    w_stat, p_raw = stats.wilcoxon(wide["required"], wide["voluntary"])
    result = pd.DataFrame([{
        "comparison": "required_vs_voluntary", "n": len(wide),
        "n_nonzero_diff": int((diff != 0).sum()), "median_diff": diff.median(),
        "wilcoxon_stat": w_stat, "p_raw": p_raw, "effect_size_r": wilcoxon_effect_size(diff.values),
    }])
    print(result.to_string(index=False))
    return result


def run_wilcoxon_per_map_condition(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank, F1, required vs. voluntary, per map condition\n{'='*70}")
    rows = []
    for cond in MAP_CONDITIONS:
        wide = _wide(df[df["map_condition"] == cond])
        diff = wide["required"] - wide["voluntary"]
        try:
            w_stat, p_raw = stats.wilcoxon(wide["required"], wide["voluntary"])
        except ValueError:
            w_stat, p_raw = np.nan, np.nan
        rows.append({
            "map_condition": cond, "n": len(wide), "median_diff": diff.median(),
            "wilcoxon_stat": w_stat, "p_raw": p_raw, "effect_size_r": wilcoxon_effect_size(diff.values),
        })
    result = pd.DataFrame(rows)
    valid = result["p_raw"].notna()
    result.loc[valid, "p_holm"] = multipletests(result.loc[valid, "p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_wilcoxon_per_model(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank, F1, required vs. voluntary, per model\n{'='*70}")
    rows = []
    for model_short in sorted(df["model_short"].unique()):
        wide = _wide(df[df["model_short"] == model_short])
        diff = wide["required"] - wide["voluntary"]
        try:
            w_stat, p_raw = stats.wilcoxon(wide["required"], wide["voluntary"])
        except ValueError:
            w_stat, p_raw = np.nan, np.nan
        rows.append({
            "model_short": model_short, "n": len(wide), "median_diff": diff.median(),
            "wilcoxon_stat": w_stat, "p_raw": p_raw, "effect_size_r": wilcoxon_effect_size(diff.values),
        })
    result = pd.DataFrame(rows)
    valid = result["p_raw"].notna()
    result.loc[valid, "p_holm"] = multipletests(result.loc[valid, "p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_2v3_data()
    print(f"Study 2 vs 3 sample: {len(df)} trials, {df['model_short'].nunique()} models, "
          f"{df['issue_id'].nunique()} issues, map conditions: {sorted(df['map_condition'].unique())}")

    pooled = run_wilcoxon_pooled(df)
    per_map = run_wilcoxon_per_map_condition(df)
    per_model = run_wilcoxon_per_model(df)

    pooled.to_csv(os.path.join(OUT_DIR, "study2v3_f1_wilcoxon_pooled.csv"), index=False)
    per_map.to_csv(os.path.join(OUT_DIR, "study2v3_f1_wilcoxon_per_map_condition.csv"), index=False)
    per_model.to_csv(os.path.join(OUT_DIR, "study2v3_f1_wilcoxon_per_model.csv"), index=False)
    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
