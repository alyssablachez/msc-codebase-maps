"""
Study 3 -- nonparametric robustness checks for the secondary/process/cost
metrics, alongside the R GLMMs in scripts/stats_study3_r_secondary.R
(turns, turn-cap) and scripts/stats_study3_r_tokens_cost_walltime.R
(tokens, cost, wall-time). Continuous metrics (tokens, cost, wall-time,
turns) get Friedman omnibus + Holm-corrected Wilcoxon signed-rank vs.
baseline, pooled then per model. The one binary metric, hit_turn_cap,
gets Cochran's Q + McNemar instead, matching the success side
(scripts/stats_study3_success.py) -- same structure as Studies 1/2's
versions of this script.

Study 3 has no baseline condition of its own -- study==1's "baseline" is
the shared cross-study control; see scripts/stats_study3_f1.py's docstring.

Primary sample only: rep<=3.

Usage:
    python3 scripts/stats_study3_secondary_nonparametric.py
"""
import os

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.contingency_tables import cochrans_q
from statsmodels.stats.multitest import multipletests

from stats_common import matched_wide, mcnemar_row, wilcoxon_effect_size

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

METRICS = {
    "tokens":    "total_input_tokens",
    "cost":      "total_cost",
    "wall_time": "wall_time_seconds",
    "turns":     "turns_used",
}


def load_study3_data():
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["rep"] <= 3) & ((df["study"] == 3) |
                                ((df["study"] == 1) & (df["map_condition"] == "baseline")))].copy()
    df["model_short"] = df["model"].map(MODEL_SHORT)
    df["hit_turn_cap_int"] = df["hit_turn_cap"].astype(int)
    return df


def run_friedman(df):
    print(f"\n{'='*70}\nFriedman omnibus tests, tokens/cost/wall-time\n{'='*70}")
    rows = []
    for metric, col in METRICS.items():
        wide = matched_wide(df, MAP_CONDITIONS_ORDER, col)
        stat, p = stats.friedmanchisquare(*[wide[c] for c in MAP_CONDITIONS_ORDER])
        print(f"  {metric:10s} n={len(wide):4d}  Friedman chi2={stat:8.3f}  df={len(MAP_CONDITIONS_ORDER)-1}  p={p:.4f}")
        rows.append({"metric": metric, "n": len(wide), "friedman_stat": stat, "p_value": p})
    return pd.DataFrame(rows)


def run_wilcoxon_pooled(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank vs. baseline, pooled across models\n{'='*70}")
    all_rows = []
    for metric, col in METRICS.items():
        wide = matched_wide(df, MAP_CONDITIONS_ORDER, col)
        rows = []
        for cond in MAP_CONDITIONS_ORDER:
            if cond == REF_MAP_CONDITION:
                continue
            diff = wide[cond] - wide[REF_MAP_CONDITION]
            try:
                w_stat, p_raw = stats.wilcoxon(wide[cond], wide[REF_MAP_CONDITION])
            except ValueError:
                w_stat, p_raw = np.nan, np.nan
            rows.append({
                "metric": metric, "comparison": f"{cond}_vs_{REF_MAP_CONDITION}", "n": len(wide),
                "n_nonzero_diff": int((diff != 0).sum()), "median_diff": diff.median(),
                "wilcoxon_stat": w_stat, "p_raw": p_raw,
                "effect_size_r": wilcoxon_effect_size(diff.values),
            })
        metric_df = pd.DataFrame(rows)
        valid = metric_df["p_raw"].notna()
        metric_df.loc[valid, "p_holm"] = multipletests(metric_df.loc[valid, "p_raw"], method="holm")[1]
        all_rows.append(metric_df)
    result = pd.concat(all_rows, ignore_index=True)
    print(result.to_string(index=False))
    return result


def run_wilcoxon_per_model(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank vs. baseline, per model\n{'='*70}")
    all_rows = []
    for metric, col in METRICS.items():
        for model_short in sorted(df["model_short"].unique()):
            sub = df[df["model_short"] == model_short]
            wide = matched_wide(sub, MAP_CONDITIONS_ORDER, col)
            rows = []
            for cond in MAP_CONDITIONS_ORDER:
                if cond == REF_MAP_CONDITION:
                    continue
                diff = wide[cond] - wide[REF_MAP_CONDITION]
                try:
                    w_stat, p_raw = stats.wilcoxon(wide[cond], wide[REF_MAP_CONDITION])
                except ValueError:
                    w_stat, p_raw = np.nan, np.nan
                rows.append({
                    "metric": metric, "model_short": model_short, "comparison": f"{cond}_vs_{REF_MAP_CONDITION}",
                    "n": len(wide), "median_diff": diff.median(),
                    "wilcoxon_stat": w_stat, "p_raw": p_raw,
                    "effect_size_r": wilcoxon_effect_size(diff.values),
                })
            model_df = pd.DataFrame(rows)
            valid = model_df["p_raw"].notna()
            model_df.loc[valid, "p_holm"] = multipletests(model_df.loc[valid, "p_raw"], method="holm")[1]
            all_rows.append(model_df)
    result = pd.concat(all_rows, ignore_index=True)
    print(result.to_string(index=False))
    return result


# ── hit_turn_cap: Cochran's Q + McNemar (binary, matches success side) ───

def run_cochrans_q_turncap(df):
    print(f"\n{'='*70}\nCochran's Q, hit_turn_cap\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "hit_turn_cap_int")
    result = cochrans_q(wide.astype(int).values)
    print(f"n = {len(wide)} matched (model, issue, rep) units")
    print(f"Cochran's Q = {result.statistic:.3f}, df = {len(MAP_CONDITIONS_ORDER)-1}, p = {result.pvalue:.4f}")
    return pd.DataFrame([{"n": len(wide), "q_stat": result.statistic, "p_value": result.pvalue}])


def run_mcnemar_pooled_turncap(df):
    print(f"\n{'='*70}\nMcNemar's test, hit_turn_cap vs. baseline (pooled across models)\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "hit_turn_cap_int")
    rows = [mcnemar_row(wide, cond, REF_MAP_CONDITION) for cond in MAP_CONDITIONS_ORDER if cond != REF_MAP_CONDITION]
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_model_turncap(df):
    print(f"\n{'='*70}\nMcNemar's test, hit_turn_cap vs. baseline, per model\n{'='*70}")
    all_rows = []
    for model_short in sorted(df["model_short"].unique()):
        wide = matched_wide(df[df["model_short"] == model_short], MAP_CONDITIONS_ORDER, "hit_turn_cap_int")
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
    print(f"Study 3 (+ shared baseline) sample: {len(df)} trials, {df['model_short'].nunique()} models, "
          f"{df['issue_id'].nunique()} issues, conditions: {sorted(df['map_condition'].unique())}")

    friedman_result = run_friedman(df)
    wilcoxon_pooled = run_wilcoxon_pooled(df)
    wilcoxon_per_model = run_wilcoxon_per_model(df)

    friedman_result.to_csv(os.path.join(OUT_DIR, "study3_secondary_friedman.csv"), index=False)
    wilcoxon_pooled.to_csv(os.path.join(OUT_DIR, "study3_secondary_wilcoxon_pooled.csv"), index=False)
    wilcoxon_per_model.to_csv(os.path.join(OUT_DIR, "study3_secondary_wilcoxon_per_model.csv"), index=False)

    q_result = run_cochrans_q_turncap(df)
    mcnemar_pooled = run_mcnemar_pooled_turncap(df)
    mcnemar_per_model = run_mcnemar_per_model_turncap(df)

    q_result.to_csv(os.path.join(OUT_DIR, "study3_turncap_cochrans_q.csv"), index=False)
    mcnemar_pooled.to_csv(os.path.join(OUT_DIR, "study3_turncap_mcnemar_pooled.csv"), index=False)
    mcnemar_per_model.to_csv(os.path.join(OUT_DIR, "study3_turncap_mcnemar_per_model.csv"), index=False)
    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
