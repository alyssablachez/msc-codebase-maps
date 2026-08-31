"""
Shared helpers for the per-study stats batteries (scripts/stats_study{1,2,3}_*.py).
Factored out once Study 2's battery made clear this logic repeats verbatim
across studies -- Study 1's own scripts (stats_study1_f1.py,
stats_study1_success.py) predate this module and are left untouched rather
than retrofitted, so their already-reported numbers can't regress.
"""
import numpy as np
import pandas as pd
from scipy import stats


def lr_test(model_full, model_reduced):
    """Likelihood-ratio test for two nested statsmodels ML fits."""
    lr_stat = -2 * (model_reduced.llf - model_full.llf)
    df_diff = model_full.df_model - model_reduced.df_model
    p = stats.chi2.sf(lr_stat, df_diff)
    return lr_stat, p, df_diff


def wilcoxon_effect_size(diff):
    """Matched-pairs rank-biserial correlation, the Wilcoxon effect size."""
    diff = diff[diff != 0]
    if len(diff) == 0:
        return np.nan
    ranks = stats.rankdata(np.abs(diff))
    w_pos = ranks[diff > 0].sum()
    w_neg = ranks[diff < 0].sum()
    return (w_pos - w_neg) / (w_pos + w_neg)


def matched_wide(df, level_order, value_col, index_cols=("model_short", "issue_id", "rep"), pivot_col="map_condition"):
    """Pivot to one row per matched unit (index_cols), one column per level
    of pivot_col, dropping any unit missing a level. Defaults to the
    per-study map_condition comparison; the Study 2-vs-3 scripts pass
    pivot_col="submission_mode" and fold map_condition into index_cols
    instead, since there each (model, issue, rep, map_condition) unit is
    matched across voluntary vs. required rather than across map types."""
    wide = (df.pivot_table(index=list(index_cols), columns=pivot_col,
                           values=value_col, aggfunc="first")
               .dropna())
    return wide[level_order]


def mcnemar_row(wide, cond, ref):
    from statsmodels.stats.contingency_tables import mcnemar
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
