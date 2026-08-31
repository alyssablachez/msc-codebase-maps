"""
Study 2 vs. Study 3 direct comparison -- nonparametric robustness checks
alongside the primary GLMMs. Continuous metrics (tokens, cost, wall-time,
turns) get Wilcoxon signed-rank (pooled, per map condition, per model),
matched on (model, issue, rep, map_condition), comparing required vs.
voluntary submission_mode -- same structure as
scripts/stats_study2v3_f1.py. The one binary metric, hit_turn_cap, gets
McNemar instead (no Cochran's Q -- only 2 submission_mode levels, so
there's no omnibus test to run first), matching
scripts/stats_study2v3_success.py.

Usage:
    python3 scripts/stats_study2v3_secondary_nonparametric.py
"""
import os

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from stats_common import matched_wide, mcnemar_row, wilcoxon_effect_size

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

METRICS = {
    "tokens":    "total_input_tokens",
    "cost":      "total_cost",
    "wall_time": "wall_time_seconds",
    "turns":     "turns_used",
}


def load_2v3_data():
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["rep"] <= 3) & (df["study"].isin([2, 3]))].copy()
    df["model_short"] = df["model"].map(MODEL_SHORT)
    df["hit_turn_cap_int"] = df["hit_turn_cap"].astype(int)
    return df


def _wide(df, col):
    return matched_wide(df, MODE_ORDER, col, index_cols=("model_short", "issue_id", "rep", "map_condition"),
                        pivot_col="submission_mode")


def run_wilcoxon_pooled(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank, required vs. voluntary (pooled)\n{'='*70}")
    rows = []
    for metric, col in METRICS.items():
        wide = _wide(df, col)
        diff = wide["required"] - wide["voluntary"]
        w_stat, p_raw = stats.wilcoxon(wide["required"], wide["voluntary"])
        rows.append({
            "metric": metric, "n": len(wide), "n_nonzero_diff": int((diff != 0).sum()),
            "median_diff": diff.median(), "wilcoxon_stat": w_stat, "p_raw": p_raw,
            "effect_size_r": wilcoxon_effect_size(diff.values),
        })
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_wilcoxon_per_map_condition(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank, required vs. voluntary, per map condition\n{'='*70}")
    all_rows = []
    for metric, col in METRICS.items():
        rows = []
        for cond in MAP_CONDITIONS:
            wide = _wide(df[df["map_condition"] == cond], col)
            diff = wide["required"] - wide["voluntary"]
            try:
                w_stat, p_raw = stats.wilcoxon(wide["required"], wide["voluntary"])
            except ValueError:
                w_stat, p_raw = np.nan, np.nan
            rows.append({
                "metric": metric, "map_condition": cond, "n": len(wide), "median_diff": diff.median(),
                "wilcoxon_stat": w_stat, "p_raw": p_raw, "effect_size_r": wilcoxon_effect_size(diff.values),
            })
        metric_df = pd.DataFrame(rows)
        valid = metric_df["p_raw"].notna()
        metric_df.loc[valid, "p_holm"] = multipletests(metric_df.loc[valid, "p_raw"], method="holm")[1]
        all_rows.append(metric_df)
    result = pd.concat(all_rows, ignore_index=True)
    print(result.to_string(index=False))
    return result


def run_wilcoxon_per_model(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank, required vs. voluntary, per model\n{'='*70}")
    all_rows = []
    for metric, col in METRICS.items():
        rows = []
        for model_short in sorted(df["model_short"].unique()):
            wide = _wide(df[df["model_short"] == model_short], col)
            diff = wide["required"] - wide["voluntary"]
            try:
                w_stat, p_raw = stats.wilcoxon(wide["required"], wide["voluntary"])
            except ValueError:
                w_stat, p_raw = np.nan, np.nan
            rows.append({
                "metric": metric, "model_short": model_short, "n": len(wide), "median_diff": diff.median(),
                "wilcoxon_stat": w_stat, "p_raw": p_raw, "effect_size_r": wilcoxon_effect_size(diff.values),
            })
        metric_df = pd.DataFrame(rows)
        valid = metric_df["p_raw"].notna()
        metric_df.loc[valid, "p_holm"] = multipletests(metric_df.loc[valid, "p_raw"], method="holm")[1]
        all_rows.append(metric_df)
    result = pd.concat(all_rows, ignore_index=True)
    print(result.to_string(index=False))
    return result


# ── hit_turn_cap: McNemar (binary, matches success side) ─────────────────

def run_mcnemar_pooled_turncap(df):
    print(f"\n{'='*70}\nMcNemar's test, hit_turn_cap, required vs. voluntary (pooled)\n{'='*70}")
    wide = _wide(df, "hit_turn_cap_int")
    row = mcnemar_row(wide, "required", "voluntary")
    result = pd.DataFrame([row])
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_map_condition_turncap(df):
    print(f"\n{'='*70}\nMcNemar's test, hit_turn_cap, required vs. voluntary, per map condition\n{'='*70}")
    rows = []
    for cond in MAP_CONDITIONS:
        wide = _wide(df[df["map_condition"] == cond], "hit_turn_cap_int")
        rows.append(dict(mcnemar_row(wide, "required", "voluntary"), map_condition=cond))
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_model_turncap(df):
    print(f"\n{'='*70}\nMcNemar's test, hit_turn_cap, required vs. voluntary, per model\n{'='*70}")
    rows = []
    for model_short in sorted(df["model_short"].unique()):
        wide = _wide(df[df["model_short"] == model_short], "hit_turn_cap_int")
        rows.append(dict(mcnemar_row(wide, "required", "voluntary"), model_short=model_short))
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
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

    pooled.to_csv(os.path.join(OUT_DIR, "study2v3_secondary_wilcoxon_pooled.csv"), index=False)
    per_map.to_csv(os.path.join(OUT_DIR, "study2v3_secondary_wilcoxon_per_map_condition.csv"), index=False)
    per_model.to_csv(os.path.join(OUT_DIR, "study2v3_secondary_wilcoxon_per_model.csv"), index=False)

    mcnemar_pooled = run_mcnemar_pooled_turncap(df)
    mcnemar_per_map = run_mcnemar_per_map_condition_turncap(df)
    mcnemar_per_model = run_mcnemar_per_model_turncap(df)

    mcnemar_pooled.to_csv(os.path.join(OUT_DIR, "study2v3_turncap_mcnemar_pooled.csv"), index=False)
    mcnemar_per_map.to_csv(os.path.join(OUT_DIR, "study2v3_turncap_mcnemar_per_map_condition.csv"), index=False)
    mcnemar_per_model.to_csv(os.path.join(OUT_DIR, "study2v3_turncap_mcnemar_per_model.csv"), index=False)
    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
