"""
Study 1 (map-as-context vs. baseline), F1 side of the combined-chapter stats
battery -- the nonparametric tests (2-4 in the original numbering):
  2. Friedman test on F1 -- nonparametric omnibus across the 4 matched
     conditions (none/ast_compact/freq/cochange), same convention as
     Study 0's map-condition comparison.
  3. Wilcoxon signed-rank, F1 -- each map type vs. baseline, Holm-corrected.
  4. Wilcoxon signed-rank, per model -- same 3 contrasts repeated within
     each of the 4 models, to check the pooled result isn't masking
     model-specific heterogeneity.

The primary GLMM test (1 in the original numbering: full vs. reduced,
LRT for the three-way map_condition x log(codebase_size) x model
interaction) now lives in scripts/stats_study1_r_glmm.R -- a true MLE fit
with both crossed random effects (issue_id, repo) simultaneously via
glmmTMB's ordbeta() family. This script's Python GEE/marginal-LRT version
of that test was dropped: GEE only clusters on one grouping variable at a
time and its LRT ignores clustering entirely, so once the R fit was
working it was a strictly weaker version of the same test, not a
complementary one -- unlike the Friedman/Wilcoxon tests below, which are
genuinely distribution-free and worth keeping alongside the GLMM.

Primary sample only: study==1, rep<=3 (reps 4-15 are the expanded-
replication trials, excluded here -- see scripts/collate_studies_1_2_3.py).

Usage:
    python3 scripts/stats_study1_f1.py
"""
import os

import numpy as np
import pandas as pd
from scipy import stats
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
    df = df.dropna(subset=["f1"])
    df["log_codebase_size"] = np.log(df["codebase_size"])
    df["model_short"] = df["model"].map(MODEL_SHORT)
    return df


# ── 2/3/4. Friedman + Wilcoxon on matched trials ─────────────────────────

def matched_wide(df, value_col="f1"):
    wide = (df.pivot_table(index=["model_short", "issue_id", "rep"],
                           columns="map_condition", values=value_col, aggfunc="first")
               .dropna())
    return wide[MAP_CONDITIONS_ORDER]


def wilcoxon_effect_size(diff):
    diff = diff[diff != 0]
    if len(diff) == 0:
        return np.nan
    ranks = stats.rankdata(np.abs(diff))
    w_pos = ranks[diff > 0].sum()
    w_neg = ranks[diff < 0].sum()
    return (w_pos - w_neg) / (w_pos + w_neg)


def run_friedman(df):
    print(f"\n{'='*70}\n2. Friedman omnibus test, F1\n{'='*70}")
    wide = matched_wide(df)
    stat, p = stats.friedmanchisquare(*[wide[c] for c in MAP_CONDITIONS_ORDER])
    print(f"n = {len(wide)} matched (model, issue, rep) units")
    print(f"Friedman chi2 = {stat:.3f}, df = {len(MAP_CONDITIONS_ORDER)-1}, p = {p:.4f}")
    return pd.DataFrame([{"n": len(wide), "friedman_stat": stat, "p_value": p}])


def run_wilcoxon_pooled(df):
    print(f"\n{'='*70}\n3. Wilcoxon signed-rank, F1 vs. baseline (pooled across models)\n{'='*70}")
    wide = matched_wide(df)
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
            "comparison": f"{cond}_vs_{REF_MAP_CONDITION}", "n": len(wide),
            "n_nonzero_diff": int((diff != 0).sum()), "median_diff": diff.median(),
            "wilcoxon_stat": w_stat, "p_raw": p_raw,
            "effect_size_r": wilcoxon_effect_size(diff.values),
        })
    result = pd.DataFrame(rows)
    valid = result["p_raw"].notna()
    result.loc[valid, "p_holm"] = multipletests(result.loc[valid, "p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_wilcoxon_per_model(df):
    print(f"\n{'='*70}\n4. Wilcoxon signed-rank, F1 vs. baseline, per model\n{'='*70}")
    all_rows = []
    for model_short in sorted(df["model_short"].unique()):
        sub = df[df["model_short"] == model_short]
        wide = matched_wide(sub)
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
                "model_short": model_short, "comparison": f"{cond}_vs_{REF_MAP_CONDITION}",
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


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_study1_data()
    print(f"Study 1 primary sample: {len(df)} trials, {df['model_short'].nunique()} models, "
          f"{df['issue_id'].nunique()} issues, conditions: {sorted(df['map_condition'].unique())}")

    friedman_result = run_friedman(df)
    wilcoxon_pooled = run_wilcoxon_pooled(df)
    wilcoxon_per_model = run_wilcoxon_per_model(df)

    friedman_result.to_csv(os.path.join(OUT_DIR, "study1_f1_friedman.csv"), index=False)
    wilcoxon_pooled.to_csv(os.path.join(OUT_DIR, "study1_f1_wilcoxon_pooled.csv"), index=False)
    wilcoxon_per_model.to_csv(os.path.join(OUT_DIR, "study1_f1_wilcoxon_per_model.csv"), index=False)
    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
