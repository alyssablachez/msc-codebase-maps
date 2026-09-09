"""
Study 2 vs. Study 3 -- same two new process metrics as
scripts/stats_study1_touch_timing.py ("explored" via McNemar, first-touch
timing via a stratified Cox model), comparing required vs. voluntary
submission_mode directly, matched on (model, issue, rep, map_condition)
-- same design as scripts/stats_study2v3_secondary_nonparametric.py.
No Cochran's Q / omnibus LLR test needed: only 2 submission_mode levels.

Usage:
    python3 scripts/stats_study2v3_touch_timing.py
"""
import os

import pandas as pd
from lifelines import CoxPHFitter
from statsmodels.stats.multitest import multipletests

from stats_common import matched_wide, mcnemar_row
from stats_study2v3_secondary_nonparametric import load_2v3_data, MODE_ORDER, MAP_CONDITIONS
from touch_timing_common import attach_touch_timing

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_ROOT, "data", "stats_study2v3")


def load_data():
    df = load_2v3_data()
    df = attach_touch_timing(df)
    df["explored_int"] = df["explored"].astype(int)
    return df


def _wide(df, col):
    return matched_wide(df, MODE_ORDER, col, index_cols=("model_short", "issue_id", "rep", "map_condition"),
                        pivot_col="submission_mode")


def run_mcnemar_pooled_explored(df):
    print(f"\n{'='*70}\nMcNemar's test, explored, required vs. voluntary (pooled)\n{'='*70}")
    wide = _wide(df, "explored_int")
    row = mcnemar_row(wide, "required", "voluntary")
    result = pd.DataFrame([row])
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_map_condition_explored(df):
    print(f"\n{'='*70}\nMcNemar's test, explored, required vs. voluntary, per map condition\n{'='*70}")
    rows = []
    for cond in MAP_CONDITIONS:
        wide = _wide(df[df["map_condition"] == cond], "explored_int")
        rows.append(dict(mcnemar_row(wide, "required", "voluntary"), map_condition=cond))
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_mcnemar_per_model_explored(df):
    print(f"\n{'='*70}\nMcNemar's test, explored, required vs. voluntary, per model\n{'='*70}")
    rows = []
    for model_short in sorted(df["model_short"].unique()):
        wide = _wide(df[df["model_short"] == model_short], "explored_int")
        rows.append(dict(mcnemar_row(wide, "required", "voluntary"), model_short=model_short))
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p_raw"], method="holm")[1]
    print(result.to_string(index=False))
    return result


FORMULA = 'C(submission_mode, Treatment(reference="voluntary"))'


def _fit_cox(df, strata):
    cph = CoxPHFitter()
    cph.fit(df[["duration", "explored", "submission_mode"] + strata], duration_col="duration",
           event_col="explored", strata=strata, formula=FORMULA)
    return cph


def run_cox_pooled(df):
    print(f"\n{'='*70}\nStratified Cox model (strata = model x issue x map_condition), "
         f"required vs. voluntary (pooled)\n{'='*70}")
    cph = _fit_cox(df, ["model_short", "issue_id", "map_condition"])
    summ = cph.summary.reset_index().rename(columns={"covariate": "term"})
    print(f"n = {len(df)} trials, {df.groupby(['model_short','issue_id','map_condition']).ngroups} strata")
    print(summ[["coef", "exp(coef)", "se(coef)", "p"]].to_string(index=False))
    return summ[["coef", "exp(coef)", "se(coef)", "p"]]


def run_cox_per_map_condition(df):
    print(f"\n{'='*70}\nStratified Cox model, required vs. voluntary, per map condition\n{'='*70}")
    rows = []
    for cond in MAP_CONDITIONS:
        sub = df[df["map_condition"] == cond]
        cph = _fit_cox(sub, ["model_short", "issue_id"])
        summ = cph.summary.reset_index()
        rows.append({"map_condition": cond, "coef": summ["coef"].iloc[0],
                    "exp(coef)": summ["exp(coef)"].iloc[0], "se(coef)": summ["se(coef)"].iloc[0],
                    "p": summ["p"].iloc[0]})
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def run_cox_per_model(df):
    print(f"\n{'='*70}\nStratified Cox model, required vs. voluntary, per model\n{'='*70}")
    rows = []
    for model_short in sorted(df["model_short"].unique()):
        sub = df[df["model_short"] == model_short]
        cph = _fit_cox(sub, ["issue_id", "map_condition"])
        summ = cph.summary.reset_index()
        rows.append({"model_short": model_short, "coef": summ["coef"].iloc[0],
                    "exp(coef)": summ["exp(coef)"].iloc[0], "se(coef)": summ["se(coef)"].iloc[0],
                    "p": summ["p"].iloc[0]})
    result = pd.DataFrame(rows)
    result["p_holm"] = multipletests(result["p"], method="holm")[1]
    print(result.to_string(index=False))
    return result


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = load_data()
    print(f"Study 2v3 sample: {len(df)} trials, explored rate = {df['explored'].mean():.3f}")

    mcnemar_pooled = run_mcnemar_pooled_explored(df)
    mcnemar_per_cond = run_mcnemar_per_map_condition_explored(df)
    mcnemar_per_model = run_mcnemar_per_model_explored(df)
    mcnemar_pooled.to_csv(os.path.join(OUT_DIR, "study2v3_explored_mcnemar_pooled.csv"), index=False)
    mcnemar_per_cond.to_csv(os.path.join(OUT_DIR, "study2v3_explored_mcnemar_per_map_condition.csv"), index=False)
    mcnemar_per_model.to_csv(os.path.join(OUT_DIR, "study2v3_explored_mcnemar_per_model.csv"), index=False)

    cox_pooled = run_cox_pooled(df)
    cox_per_cond = run_cox_per_map_condition(df)
    cox_per_model = run_cox_per_model(df)
    cox_pooled.to_csv(os.path.join(OUT_DIR, "study2v3_first_touch_cox_pooled.csv"), index=False)
    cox_per_cond.to_csv(os.path.join(OUT_DIR, "study2v3_first_touch_cox_per_map_condition.csv"), index=False)
    cox_per_model.to_csv(os.path.join(OUT_DIR, "study2v3_first_touch_cox_per_model.csv"), index=False)

    print(f"\nSaved CSVs -> {OUT_DIR}/")


if __name__ == "__main__":
    main()
