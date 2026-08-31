"""
Study 1 (map-as-context vs. baseline), success (binary = recall==1.0) side
of the combined-chapter stats battery -- the nonparametric tests (6-7 in
the original numbering):
  6. Cochran's Q -- binary omnibus across the 4 matched conditions, the
     success-outcome analogue of the F1 side's Friedman test.
  7. McNemar's test -- each map type vs. baseline, Holm-corrected, the
     success-outcome analogue of the F1 side's Wilcoxon tests.

The primary GLMM test (5 in the original numbering: logistic GLMM, full
vs. reduced, LRT for the three-way interaction) now lives in
scripts/stats_study1_r_glmm.R -- lme4::glmer with true crossed random
effects and a real MLE-based LRT. This script's Python
BinomialBayesMixedGLM version of that test was dropped: it only
approximates the crossed-random-effects fit via variational Bayes, so
once the R fit was working it was a strictly weaker version of the same
test, not a complementary one -- unlike Cochran's Q/McNemar below, which
are genuinely distribution-free and worth keeping alongside the GLMM.

Primary sample only: study==1, rep<=3. Same data source, same matched-unit
convention as scripts/stats_study1_f1.py -- run that one first for the F1
results this is meant to sit alongside as a robustness check.

Usage:
    python3 scripts/stats_study1_success.py
"""
import os

import numpy as np
import pandas as pd
from statsmodels.stats.contingency_tables import mcnemar, cochrans_q
from statsmodels.stats.multitest import multipletests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study1")

REF_MAP_CONDITION = "baseline"
MAP_CONDITIONS_ORDER = ["baseline", "structural", "temporal_frequency", "temporal_cochange"]

MODEL_SHORT = {
    "mistral/ministral-3b-latest":                          "ministral-3b",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b":  "gpt-oss-120b",
    "deepseek/deepseek-v4-flash":                            "deepseek-flash",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B":   "nemotron-super",
}


def load_study1_data():
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["study"] == 1) & (df["rep"] <= 3)].copy()
    df = df.dropna(subset=["success"])
    df["success_int"] = df["success"].astype(int)
    df["log_codebase_size"] = np.log(df["codebase_size"])
    df["model_short"] = df["model"].map(MODEL_SHORT)
    return df


# ── 6/7. Cochran's Q + McNemar on matched trials ─────────────────────────

def matched_wide(df):
    wide = (df.pivot_table(index=["model_short", "issue_id", "rep"],
                           columns="map_condition", values="success_int", aggfunc="first")
               .dropna())
    return wide[MAP_CONDITIONS_ORDER]


def run_cochrans_q(df):
    print(f"\n{'='*70}\n6. Cochran's Q, success\n{'='*70}")
    wide = matched_wide(df)
    result = cochrans_q(wide.astype(int).values)
    print(f"n = {len(wide)} matched (model, issue, rep) units")
    print(f"Cochran's Q = {result.statistic:.3f}, df = {len(MAP_CONDITIONS_ORDER)-1}, p = {result.pvalue:.4f}")
    return pd.DataFrame([{"n": len(wide), "q_stat": result.statistic, "p_value": result.pvalue}])


def _mcnemar_row(wide, cond, ref):
    a = wide[ref].astype(bool)
    b = wide[cond].astype(bool)
    table = pd.crosstab(a, b).reindex(index=[False, True], columns=[False, True], fill_value=0)
    result = mcnemar(table.values, exact=(table.values.sum() < 25))
    n_disagree = table.iloc[0, 1] + table.iloc[1, 0]
    return {
        "comparison": f"{cond}_vs_{ref}", "n": len(wide), "n_discordant_pairs": int(n_disagree),
        "ref_fail_cond_succeed": int(table.iloc[0, 1]), "ref_succeed_cond_fail": int(table.iloc[1, 0]),
        "statistic": round(float(result.statistic), 3), "p_raw": float(result.pvalue),
    }


def run_mcnemar_pooled(df):
    print(f"\n{'='*70}\n7. McNemar's test, success vs. baseline (pooled across models)\n{'='*70}")
    wide = matched_wide(df)
    rows = [_mcnemar_row(wide, cond, REF_MAP_CONDITION) for cond in MAP_CONDITIONS_ORDER if cond != REF_MAP_CONDITION]
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_model(df):
    print(f"\n{'='*70}\n7b. McNemar's test, success vs. baseline, per model\n{'='*70}")
    all_rows = []
    for model_short in sorted(df["model_short"].unique()):
        wide = matched_wide(df[df["model_short"] == model_short])
        rows = [dict(_mcnemar_row(wide, cond, REF_MAP_CONDITION), model_short=model_short)
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
    df = load_study1_data()
    print(f"Study 1 primary sample: {len(df)} trials, success rate = {df['success_int'].mean():.3f}")

    q_result = run_cochrans_q(df)
    mcnemar_pooled = run_mcnemar_pooled(df)
    mcnemar_per_model = run_mcnemar_per_model(df)

    q_result.to_csv(os.path.join(OUT_DIR, "study1_success_cochrans_q.csv"), index=False)
    mcnemar_pooled.to_csv(os.path.join(OUT_DIR, "study1_success_mcnemar_pooled.csv"), index=False)
    mcnemar_per_model.to_csv(os.path.join(OUT_DIR, "study1_success_mcnemar_per_model.csv"), index=False)
    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
