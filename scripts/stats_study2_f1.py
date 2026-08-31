"""
Study 2 (on-demand/voluntary map tools vs. baseline), F1 side of the
combined-chapter stats battery -- the nonparametric tests (2-4 in the
original numbering), same structure as Study 1's
scripts/stats_study1_f1.py, run against Study 2's own conditions:
  2. Friedman test on F1 -- nonparametric omnibus across the 5 matched
     conditions (baseline/structural/temporal_frequency/temporal_cochange/
     all_tools).
  3. Wilcoxon signed-rank, F1 -- each map type vs. baseline, Holm-corrected.
  4. Wilcoxon signed-rank, per model.

The primary GLMM test (1 in the original numbering) now lives in
scripts/stats_study2_r_glmm.R -- see stats_study1_f1.py's docstring for
why the Python GEE/marginal-LRT version of that test was dropped rather
than kept alongside the R fit.

Study 2 has no baseline condition of its own -- study==1's "baseline" is
the shared cross-study control (user-confirmed design decision; see
scripts/collate_studies_1_2_3.py), so the sample here is Study 2's 4
conditions (2160 trials) plus Study 1's baseline (540 trials) = 2700.

Primary sample only: rep<=3 (reps 4-15 are the expanded-replication
trials, excluded here -- see scripts/collate_studies_1_2_3.py).

Usage:
    python3 scripts/stats_study2_f1.py
"""
import os

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from stats_common import matched_wide, wilcoxon_effect_size

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study2")

REF_MAP_CONDITION = "baseline"
MAP_CONDITIONS_ORDER = ["baseline", "structural", "temporal_frequency", "temporal_cochange", "all_tools"]

MODEL_SHORT = {
    "mistral/ministral-3b-latest":                          "ministral-3b",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b":  "gpt-oss-120b",
    "deepseek/deepseek-v4-flash":                            "deepseek-flash",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B":   "nemotron-super",
}


def load_study2_data():
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["rep"] <= 3) & ((df["study"] == 2) |
                                ((df["study"] == 1) & (df["map_condition"] == "baseline")))].copy()
    df = df.dropna(subset=["f1"])
    df["log_codebase_size"] = np.log(df["codebase_size"])
    df["model_short"] = df["model"].map(MODEL_SHORT)
    return df


# ── 2/3/4. Friedman + Wilcoxon on matched trials ─────────────────────────

def run_friedman(df):
    print(f"\n{'='*70}\n2. Friedman omnibus test, F1\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "f1")
    stat, p = stats.friedmanchisquare(*[wide[c] for c in MAP_CONDITIONS_ORDER])
    print(f"n = {len(wide)} matched (model, issue, rep) units")
    print(f"Friedman chi2 = {stat:.3f}, df = {len(MAP_CONDITIONS_ORDER)-1}, p = {p:.4f}")
    return pd.DataFrame([{"n": len(wide), "friedman_stat": stat, "p_value": p}])


def run_wilcoxon_pooled(df):
    print(f"\n{'='*70}\n3. Wilcoxon signed-rank, F1 vs. baseline (pooled across models)\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "f1")
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
        wide = matched_wide(sub, MAP_CONDITIONS_ORDER, "f1")
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
    df = load_study2_data()
    print(f"Study 2 (+ shared baseline) sample: {len(df)} trials, {df['model_short'].nunique()} models, "
          f"{df['issue_id'].nunique()} issues, conditions: {sorted(df['map_condition'].unique())}")

    friedman_result = run_friedman(df)
    wilcoxon_pooled = run_wilcoxon_pooled(df)
    wilcoxon_per_model = run_wilcoxon_per_model(df)

    friedman_result.to_csv(os.path.join(OUT_DIR, "study2_f1_friedman.csv"), index=False)
    wilcoxon_pooled.to_csv(os.path.join(OUT_DIR, "study2_f1_wilcoxon_pooled.csv"), index=False)
    wilcoxon_per_model.to_csv(os.path.join(OUT_DIR, "study2_f1_wilcoxon_per_model.csv"), index=False)
    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
