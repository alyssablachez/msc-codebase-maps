"""
Shared per-trial aggregation of data/gt_file_touch_timing.csv, generalized
from stats_study4_touch_timing_common.py so the same two metrics
("explored" and time-to-first-touch) can be added to the main Studies
1/2/3/2v3 battery, not just Study 4's 7 replication issues.

gt_file_touch_timing.csv is one row per (trial, ground-truth file) pair.
Both new metrics collapse multi-file issues to "any ground-truth file"
per trial (see stats_study4_touch_timing_common.py's docstring for why:
it's the natural predecessor stage to the existing complete_miss outcome,
and keeps one row per trial rather than several correlated ones).

first_touch_turn is right-censored, not missing, when a file is never
touched: we know the event didn't happen within that trial's own
turns_used, not that its timing is unknown. "final" (the forced-final-
answer step) maps to turns_used + 1.

Usage: import attach_touch_timing(df) after loading a study's normal
compiled_results_combined.pkl slice (must already have repo, issue_idx,
model, map_condition_raw, rep, turns_used columns) -- adds "explored"
(bool), "duration" (int, the value to feed a survival model), and
"touched_or_submitted" (bool). "explored" only counts genuine
investigation (read_file/lookup_* landing on the file); a trial can name
the right file in its final answer without ever having looked at it at
all (a correct blind guess). Kept as a separate column rather than
folded into "explored"/"duration", since "did the model investigate this
file" and "did the model ever name this file" are different questions --
collapsing them would erase the distinction this project's navigation-
mechanism findings (e.g. why the Study 3 submit-gate raises touch rates)
actually depend on. Small in practice (146/7,111 = 2.1% of otherwise-
"never touched" rows), but real.
"""
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOUCH_CSV = os.path.join(_ROOT, "data", "gt_file_touch_timing.csv")

_cache = None


def _per_trial_touch_data():
    global _cache
    if _cache is not None:
        return _cache

    touch = pd.read_csv(TOUCH_CSV)
    rows = []
    group_cols = ["repo", "issue_idx", "model", "map_type", "rep"]
    for keys, g in touch.groupby(group_cols, dropna=False):
        repo, issue_idx, model, cond, rep = keys
        touched = g[g["first_touch_turn"] != "na"]
        rows.append({
            "repo": repo, "issue_idx": issue_idx, "model": model,
            "map_condition_raw": cond, "rep": rep,
            "explored": len(touched) > 0,
            "touched_or_submitted": len(touched) > 0 or bool(g["submitted"].any()),
            "raw_touch_turns": list(touched["first_touch_turn"]),
        })
    _cache = pd.DataFrame(rows)
    return _cache


def attach_touch_timing(df):
    """df must already have repo, issue_idx, model, map_condition_raw,
    rep, turns_used. Returns a copy with "explored", "touched_or_submitted",
    and "duration" added."""
    touch = _per_trial_touch_data()
    merged = df.merge(touch, on=["repo", "issue_idx", "model", "map_condition_raw", "rep"], how="left")
    if merged["explored"].isna().any():
        n_missing = merged["explored"].isna().sum()
        raise ValueError(f"{n_missing} trials had no matching row in {TOUCH_CSV} -- "
                         f"was it regenerated after the last data collection?")

    def _duration(row):
        if not row["explored"]:
            return row["turns_used"]
        numeric = [(row["turns_used"] + 1) if v == "final" else int(v) for v in row["raw_touch_turns"]]
        return min(numeric)

    merged["duration"] = merged.apply(_duration, axis=1)
    return merged.drop(columns=["raw_touch_turns"])
