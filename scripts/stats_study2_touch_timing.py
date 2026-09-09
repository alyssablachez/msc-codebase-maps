"""
Study 2 -- same two new process metrics as scripts/stats_study1_touch_timing.py
("explored" via Cochran's Q + McNemar, first-touch timing via a stratified
Cox model), applied to Study 2's data. See that script's docstring for the
full rationale (in particular why first-touch timing isn't run as a plain
Wilcoxon: "never touched" is right-censored, not missing).

Study 2 has no baseline condition of its own -- study==1's "baseline" is
the shared cross-study control, same as scripts/stats_study2_f1.py and
scripts/stats_study2_secondary_nonparametric.py.

Usage:
    python3 scripts/stats_study2_touch_timing.py
"""
import os

import pandas as pd
from lifelines import CoxPHFitter
from statsmodels.stats.contingency_tables import cochrans_q
from statsmodels.stats.multitest import multipletests

from stats_common import matched_wide, mcnemar_row
from stats_study2_secondary_nonparametric import load_study2_data, MAP_CONDITIONS_ORDER, REF_MAP_CONDITION
from touch_timing_common import attach_touch_timing

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_ROOT, "data", "stats_study2")


def load_data():
    df = load_study2_data()
    df = attach_touch_timing(df)
    df["explored_int"] = df["explored"].astype(int)
    return df


def run_cochrans_q_explored(df):
    print(f"\n{'='*70}\nCochran's Q, explored\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "explored_int")
    result = cochrans_q(wide.astype(int).values)
    print(f"n = {len(wide)} matched (model, issue, rep) units")
    print(f"Cochran's Q = {result.statistic:.3f}, df = {len(MAP_CONDITIONS_ORDER)-1}, p = {result.pvalue:.4f}")
    return pd.DataFrame([{"n": len(wide), "q_stat": result.statistic, "p_value": result.pvalue}])


def run_mcnemar_pooled_explored(df):
    print(f"\n{'='*70}\nMcNemar's test, explored vs. baseline (pooled across models)\n{'='*70}")
    wide = matched_wide(df, MAP_CONDITIONS_ORDER, "explored_int")
    rows = [mcnemar_row(wide, cond, REF_MAP_CONDITION) for cond in MAP_CONDITIONS_ORDER if cond != REF_MAP_CONDITION]
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_model_explored(df):
    print(f"\n{'='*70}\nMcNemar's test, explored vs. baseline, per model\n{'='*70}")
    all_rows = []
    for model_short in sorted(df["model_short"].unique()):
        wide = matched_wide(df[df["model_short"] == model_short], MAP_CONDITIONS_ORDER, "explored_int")
        rows = [dict(mcnemar_row(wide, cond, REF_MAP_CONDITION), model_short=model_short)
               for cond in MAP_CONDITIONS_ORDER if cond != REF_MAP_CONDITION]
        model_df = pd.DataFrame(rows)
        model_df["p_holm"] = multipletests(model_df["p_raw"], method="holm")[1]
        all_rows.append(model_df)
    result = pd.concat(all_rows, ignore_index=True)
    cols = ["model_short", "comparison", "n", "n_discordant_pairs", "statistic", "p_raw", "p_holm"]
    print(result[cols].to_string(index=False))
    return result


FORMULA = 'C(map_condition, Treatment(reference="baseline"))'


def _fit_cox(df, strata):
    cph = CoxPHFitter()
    cph.fit(df[["duration", "explored", "map_condition"] + strata], duration_col="duration",
           event_col="explored", strata=strata, formula=FORMULA)
    return cph


def run_cox_omnibus(df):
    print(f"\n{'='*70}\nStratified Cox model (strata = model x issue), omnibus LLR test\n{'='*70}")
    cph = _fit_cox(df, ["model_short", "issue_id"])
    llr = cph.log_likelihood_ratio_test()
    print(f"n = {len(df)} trials, {df.groupby(['model_short','issue_id']).ngroups} strata")
    print(f"LLR stat = {llr.test_statistic:.3f}, df = {len(MAP_CONDITIONS_ORDER)-1}, p = {llr.p_value:.4f}")
    return pd.DataFrame([{"n": len(df), "n_strata": df.groupby(["model_short", "issue_id"]).ngroups,
                         "llr_stat": llr.test_statistic, "p_value": llr.p_value}])


def run_cox_pairwise_pooled(df):
    print(f"\n{'='*70}\nStratified Cox model, per-condition hazard ratio vs. baseline (pooled)\n{'='*70}")
    cph = _fit_cox(df, ["model_short", "issue_id"])
    summ = cph.summary.reset_index().rename(columns={"covariate": "term"})
    summ["condition"] = summ["term"].str.extract(r"\[T\.(.+)\]$")
    summ["p_holm"] = multipletests(summ["p"], method="holm")[1]
    cols = ["condition", "coef", "exp(coef)", "se(coef)", "p", "p_holm"]
    print(summ[cols].to_string(index=False))
    return summ[cols]


def run_cox_pairwise_per_model(df):
    print(f"\n{'='*70}\nStratified Cox model, per-condition hazard ratio vs. baseline, per model\n{'='*70}")
    all_rows = []
    for model_short in sorted(df["model_short"].unique()):
        sub = df[df["model_short"] == model_short]
        cph = _fit_cox(sub, ["issue_id"])
        summ = cph.summary.reset_index().rename(columns={"covariate": "term"})
        summ["condition"] = summ["term"].str.extract(r"\[T\.(.+)\]$")
        summ["model_short"] = model_short
        summ["p_holm"] = multipletests(summ["p"], method="holm")[1]
        all_rows.append(summ)
    result = pd.concat(all_rows, ignore_index=True)
    cols = ["model_short", "condition", "coef", "exp(coef)", "se(coef)", "p", "p_holm"]
    print(result[cols].to_string(index=False))
    return result[cols]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_data()
    print(f"Study 2 (+ shared baseline) sample: {len(df)} trials, explored rate = {df['explored'].mean():.3f}")

    q_result = run_cochrans_q_explored(df)
    mcnemar_pooled = run_mcnemar_pooled_explored(df)
    mcnemar_per_model = run_mcnemar_per_model_explored(df)
    q_result.to_csv(os.path.join(OUT_DIR, "study2_explored_cochrans_q.csv"), index=False)
    mcnemar_pooled.to_csv(os.path.join(OUT_DIR, "study2_explored_mcnemar_pooled.csv"), index=False)
    mcnemar_per_model.to_csv(os.path.join(OUT_DIR, "study2_explored_mcnemar_per_model.csv"), index=False)

    cox_omnibus = run_cox_omnibus(df)
    cox_pooled = run_cox_pairwise_pooled(df)
    cox_per_model = run_cox_pairwise_per_model(df)
    cox_omnibus.to_csv(os.path.join(OUT_DIR, "study2_first_touch_cox_omnibus.csv"), index=False)
    cox_pooled.to_csv(os.path.join(OUT_DIR, "study2_first_touch_cox_pairwise_pooled.csv"), index=False)
    cox_per_model.to_csv(os.path.join(OUT_DIR, "study2_first_touch_cox_pairwise_per_model.csv"), index=False)

    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
