"""
Shared per-trial aggregation of data/gt_file_touch_timing.csv for the two
new Study 4 metrics: "explored" (did the trial ever touch at least one
ground-truth file) and "first_touch_turn" (how long that took).

gt_file_touch_timing.csv is one row per (trial, gt_file) pair -- some
issues in the Study 4 set have multiple ground-truth files (flask/18: 2,
requests/12: 3, scikit-learn/45: 2, localstack/19: 7). Both metrics here
collapse to "any" across an issue's ground-truth files, for the same
reason complete_miss (F1==0) is defined as *no* file found rather than
scoring per-file: it's the natural predecessor stage to that existing
outcome -- "did it even look in the right place" as opposed to "did it
get full credit" -- and keeps every trial to exactly one row, avoiding
the non-independence problem of treating an issue's N ground-truth files
as N separate observations of the same trial.

first_touch_turn needs care because "never touched" isn't a missing
value -- it's right-censoring: we know the event didn't happen within
however many turns that specific trial actually ran (turns_used, from
compiled_results_combined.pkl), not that it's unknown. "final" (the
forced-final-answer step, after all regular turns) is mapped to
turns_used + 1, since it's chronologically the one turn after the last
regular one.

Usage: import from stats_study4_explored_fishers.py and
stats_study4_first_touch_survival.py; not run standalone.
"""
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOUCH_CSV = os.path.join(_ROOT, "data", "gt_file_touch_timing.csv")
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")


def load_per_trial_touch_data():
    """Returns a DataFrame, one row per trial, with columns:
    repo, issue_idx, model, map_condition_raw, rep, turns_used,
    explored (bool), touched_or_submitted (bool -- explored OR the trial
    named a ground-truth file in its final answer without ever having
    investigated it; a small, real gap, see touch_timing_common.py's
    docstring), first_touch_turn (int, only meaningful if explored),
    duration (int -- first_touch_turn if explored, else turns_used;
    the value to feed a survival model as the observed/censoring time)."""
    touch = pd.read_csv(TOUCH_CSV)
    trials = pd.read_pickle(DATA_PKL)[
        ["repo", "issue_idx", "model", "map_condition_raw", "rep", "turns_used"]
    ].drop_duplicates()

    merged = touch.merge(
        trials, left_on=["repo", "issue_idx", "model", "map_type", "rep"],
        right_on=["repo", "issue_idx", "model", "map_condition_raw", "rep"], how="left",
    )
    if merged["turns_used"].isna().any():
        n_missing = merged["turns_used"].isna().sum()
        raise ValueError(f"{n_missing} touch-timing rows had no matching trial in "
                         f"compiled_results_combined.pkl -- check the merge keys")

    def _numeric_turn(v):
        if v == "final":
            return None  # resolved per-row below, needs that trial's turns_used
        return int(v)

    rows = []
    group_cols = ["repo", "issue_idx", "model", "map_condition_raw", "rep", "turns_used"]
    for keys, g in merged.groupby(group_cols, dropna=False):
        repo, issue_idx, model, cond, rep, turns_used = keys
        touched = g[g["first_touch_turn"] != "na"]
        explored = len(touched) > 0
        touched_or_submitted = explored or bool(g["submitted"].any())
        if explored:
            numeric_turns = [
                (turns_used + 1) if v == "final" else int(v)
                for v in touched["first_touch_turn"]
            ]
            first_touch_turn = min(numeric_turns)
            duration = first_touch_turn
        else:
            first_touch_turn = None
            duration = turns_used
        rows.append({
            "repo": repo, "issue_idx": issue_idx, "model": model,
            "map_condition_raw": cond, "rep": rep, "turns_used": turns_used,
            "explored": explored, "touched_or_submitted": touched_or_submitted,
            "first_touch_turn": first_touch_turn, "duration": duration,
        })
    return pd.DataFrame(rows)
