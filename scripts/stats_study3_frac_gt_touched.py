"""
Study 3 -- does map condition move frac_gt_touched (data/gt_files_touched_
fraction.csv), the fraction of an issue's ground-truth files a trial ever
touches during exploration? Scoped to the 17 multi-file issues that
metric is defined for (see scripts/gt_files_touched_fraction.py) -- a
finer-grained companion to the "explored" binary, which can't distinguish
"touched 1 of 7" from "touched 7 of 7" and so is uninformative here.

Continuous, bounded [0,1] outcome -- same shape as F1 itself, so tested
the same way the rest of this project tests F1 (Friedman omnibus +
Holm-corrected Wilcoxon signed-rank vs. baseline, pooled then per model),
matched on (model, issue, rep) exactly like
scripts/stats_study3_secondary_nonparametric.py.

Usage:
    python3 scripts/stats_study3_frac_gt_touched.py
"""
import os

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.stats.multitest import multipletests

from stats_common import matched_wide, wilcoxon_effect_size
from stats_study3_secondary_nonparametric import load_study3_data, MAP_CONDITIONS_ORDER, REF_MAP_CONDITION

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRAC_CSV = os.path.join(_ROOT, "data", "gt_files_touched_fraction.csv")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study3")


def load_data():
    df = load_study3_data()
    frac = pd.read_csv(FRAC_CSV)
    merged = df.merge(
        frac[["repo", "issue_idx", "model", "map_condition_raw", "rep", "frac_gt_touched"]],
        on=["repo", "issue_idx", "model", "map_condition_raw", "rep"], how="inner",
    )
    return merged


def run_friedman(df):
    print(f"\n{'='*70}\nFriedman omnibus, frac_gt_touched\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "frac_gt_touched")
    stat, p = stats.friedmanchisquare(*[wide[c] for c in MAP_CONDITIONS_ORDER])
    print(f"n = {len(wide)} matched units, {df.groupby(['repo','issue_idx']).ngroups} issues")
    print(f"Friedman chi2 = {stat:.3f}, df = {len(MAP_CONDITIONS_ORDER)-1}, p = {p:.4f}")
    return pd.DataFrame([{"n": len(wide), "friedman_stat": stat, "p_value": p}])


def run_wilcoxon_pooled(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank vs. baseline, pooled across models\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "frac_gt_touched")
    rows = []
    for cond in MAP_CONDITIONS_ORDER:
        if cond == REF_MAP_CONDITION:
            continue
        diff = wide[cond] - wide[REF_MAP_CONDITION]
        w_stat, p_raw = stats.wilcoxon(wide[cond], wide[REF_MAP_CONDITION])
        rows.append({
            "comparison": f"{cond}_vs_{REF_MAP_CONDITION}", "n": len(wide),
            "n_nonzero_diff": int((diff != 0).sum()), "median_diff": diff.median(),
            "wilcoxon_stat": w_stat, "p_raw": p_raw,
            "effect_size_r": wilcoxon_effect_size(diff.values),
        })
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_wilcoxon_per_model(df):
    print(f"\n{'='*70}\nWilcoxon signed-rank vs. baseline, per model\n{'='*70}")
    all_rows = []
    for model_short in sorted(df["model_short"].unique()):
        sub = df[df["model_short"] == model_short]
        wide = matched_wide(sub, MAP_CONDITIONS_ORDER, "frac_gt_touched")
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
    df = load_data()
    print(f"Study 3, multi-file-issue subset: {len(df)} trials, "
         f"{df.groupby(['repo','issue_idx']).ngroups} issues")

    friedman_result = run_friedman(df)
    wilcoxon_pooled = run_wilcoxon_pooled(df)
    wilcoxon_per_model = run_wilcoxon_per_model(df)

    friedman_result.to_csv(os.path.join(OUT_DIR, "study3_frac_gt_touched_friedman.csv"), index=False)
    wilcoxon_pooled.to_csv(os.path.join(OUT_DIR, "study3_frac_gt_touched_wilcoxon_pooled.csv"), index=False)
    wilcoxon_per_model.to_csv(os.path.join(OUT_DIR, "study3_frac_gt_touched_wilcoxon_per_model.csv"), index=False)
    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
