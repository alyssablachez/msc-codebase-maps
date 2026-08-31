"""
Study 3 (on-demand/required map tools vs. baseline), success (binary =
recall==1.0) side of the combined-chapter stats battery -- the
nonparametric tests (6-7 in the original numbering), same structure as
scripts/stats_study1_success.py / scripts/stats_study2_success.py, run
against Study 3's own conditions:
  6. Cochran's Q -- binary omnibus across the 5 matched conditions.
  7. McNemar's test -- each map type vs. baseline, Holm-corrected.

The primary GLMM test (5 in the original numbering) now lives in
scripts/stats_study3_r_glmm.R -- see stats_study1_success.py's docstring
for why the Python BinomialBayesMixedGLM version of that test was dropped
rather than kept alongside the R fit.

Study 3 has no baseline condition of its own -- study==1's "baseline" is
the shared cross-study control; see scripts/stats_study3_f1.py's docstring
and scripts/collate_studies_1_2_3.py for the design rationale.

Primary sample only: rep<=3. Same data source, same matched-unit
convention as scripts/stats_study3_f1.py -- run that one first for the F1
results this is meant to sit alongside as a robustness check.

Usage:
    python3 scripts/stats_study3_success.py
"""
import os

import numpy as np
import pandas as pd
from statsmodels.stats.contingency_tables import cochrans_q
from statsmodels.stats.multitest import multipletests

from stats_common import matched_wide, mcnemar_row

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study3")

REF_MAP_CONDITION = "baseline"
MAP_CONDITIONS_ORDER = ["baseline", "structural", "temporal_frequency", "temporal_cochange", "all_tools"]

MODEL_SHORT = {
    "mistral/ministral-3b-latest":                          "ministral-3b",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b":  "gpt-oss-120b",
    "deepseek/deepseek-v4-flash":                            "deepseek-flash",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B":   "nemotron-super",
}


def load_study3_data():
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["rep"] <= 3) & ((df["study"] == 3) |
                                ((df["study"] == 1) & (df["map_condition"] == "baseline")))].copy()
    df = df.dropna(subset=["success"])
    df["success_int"] = df["success"].astype(int)
    df["log_codebase_size"] = np.log(df["codebase_size"])
    df["model_short"] = df["model"].map(MODEL_SHORT)
    return df


# ── 6/7. Cochran's Q + McNemar on matched trials ─────────────────────────

def run_cochrans_q(df):
    print(f"\n{'='*70}\n6. Cochran's Q, success\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "success_int")
    result = cochrans_q(wide.astype(int).values)
    print(f"n = {len(wide)} matched (model, issue, rep) units")
    print(f"Cochran's Q = {result.statistic:.3f}, df = {len(MAP_CONDITIONS_ORDER)-1}, p = {result.pvalue:.4f}")
    return pd.DataFrame([{"n": len(wide), "q_stat": result.statistic, "p_value": result.pvalue}])


def run_mcnemar_pooled(df):
    print(f"\n{'='*70}\n7. McNemar's test, success vs. baseline (pooled across models)\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "success_int")
    rows = [mcnemar_row(wide, cond, REF_MAP_CONDITION) for cond in MAP_CONDITIONS_ORDER if cond != REF_MAP_CONDITION]
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_model(df):
    print(f"\n{'='*70}\n7b. McNemar's test, success vs. baseline, per model\n{'='*70}")
    all_rows = []
    for model_short in sorted(df["model_short"].unique()):
        wide = matched_wide(df[df["model_short"] == model_short], MAP_CONDITIONS_ORDER, "success_int")
        rows = [dict(mcnemar_row(wide, cond, REF_MAP_CONDITION), model_short=model_short)
               for cond in MAP_CONDITIONS_ORDER if cond != REF_MAP_CONDITION]
        model_df = pd.DataFrame(rows)
        model_df["p_holm"] = multipletests(model_df["p_raw"], method="holm")[1]
        all_rows.append(model_df)
    result = pd.concat(all_rows, ignore_index=True)
    cols = ["model_short", "comparison", "n", "n_discordant_pairs", "statistic", "p_raw", "p_holm"]
    print(result[cols].to_string(index=False))
    return result


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_study3_data()
    print(f"Study 3 (+ shared baseline) sample: {len(df)} trials, success rate = {df['success_int'].mean():.3f}")

    q_result = run_cochrans_q(df)
    mcnemar_pooled = run_mcnemar_pooled(df)
    mcnemar_per_model = run_mcnemar_per_model(df)

    q_result.to_csv(os.path.join(OUT_DIR, "study3_success_cochrans_q.csv"), index=False)
    mcnemar_pooled.to_csv(os.path.join(OUT_DIR, "study3_success_mcnemar_pooled.csv"), index=False)
    mcnemar_per_model.to_csv(os.path.join(OUT_DIR, "study3_success_mcnemar_per_model.csv"), index=False)
    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
