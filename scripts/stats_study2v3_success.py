"""
Study 2 vs. Study 3 direct comparison, success side -- the nonparametric
robustness check alongside scripts/stats_study2v3_r_glmm.R's GLMM.
McNemar's test on matched (model, issue, rep, map_condition) units,
comparing required vs. voluntary submission_mode. Reported pooled, per
map condition, and per model -- same structure as
scripts/stats_study2v3_f1.py.

Usage:
    python3 scripts/stats_study2v3_success.py
"""
import os

import pandas as pd
from statsmodels.stats.multitest import multipletests

from stats_common import matched_wide, mcnemar_row

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
    df = df.dropna(subset=["success"])
    df["success_int"] = df["success"].astype(int)
    df["model_short"] = df["model"].map(MODEL_SHORT)
    return df


def _wide(df):
    return matched_wide(df, MODE_ORDER, "success_int", index_cols=("model_short", "issue_id", "rep", "map_condition"),
                        pivot_col="submission_mode")


def run_mcnemar_pooled(df):
    print(f"\n{'='*70}\nMcNemar's test, success, required vs. voluntary (pooled)\n{'='*70}")
    wide = _wide(df)
    row = mcnemar_row(wide, "required", "voluntary")
    result = pd.DataFrame([row])
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_map_condition(df):
    print(f"\n{'='*70}\nMcNemar's test, success, required vs. voluntary, per map condition\n{'='*70}")
    rows = []
    for cond in MAP_CONDITIONS:
        wide = _wide(df[df["map_condition"] == cond])
        rows.append(dict(mcnemar_row(wide, "required", "voluntary"), map_condition=cond))
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_model(df):
    print(f"\n{'='*70}\nMcNemar's test, success, required vs. voluntary, per model\n{'='*70}")
    rows = []
    for model_short in sorted(df["model_short"].unique()):
        wide = _wide(df[df["model_short"] == model_short])
        rows.append(dict(mcnemar_row(wide, "required", "voluntary"), model_short=model_short))
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_2v3_data()
    print(f"Study 2 vs 3 sample: {len(df)} trials, success rate = {df['success_int'].mean():.3f}")

    pooled = run_mcnemar_pooled(df)
    per_map = run_mcnemar_per_map_condition(df)
    per_model = run_mcnemar_per_model(df)

    pooled.to_csv(os.path.join(OUT_DIR, "study2v3_success_mcnemar_pooled.csv"), index=False)
    per_map.to_csv(os.path.join(OUT_DIR, "study2v3_success_mcnemar_per_map_condition.csv"), index=False)
    per_model.to_csv(os.path.join(OUT_DIR, "study2v3_success_mcnemar_per_model.csv"), index=False)
    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
