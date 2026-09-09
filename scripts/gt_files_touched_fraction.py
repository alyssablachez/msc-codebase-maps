"""
Navigation metric for multi-file ground-truth issues: of the N ground-
truth files for a trial's issue, how many did that trial ever touch
(read_file/lookup_* landing on that exact path, per
data/gt_file_touch_timing.csv). A finer-grained companion to the
"explored" binary (any file touched) -- that metric collapses to a
single bool per trial and is uninformative here since it can't
distinguish "touched 1 of 7" from "touched 7 of 7".

Also reports frac_gt_touched_or_submitted alongside frac_gt_touched:
"touched" only counts genuine investigation, but a trial can name a
ground-truth file in its final answer without ever having looked at it
(a correct blind guess) -- see touch_timing_common.py's docstring. Small
in practice but kept as a separate column rather than silently folded
in, same reasoning as everywhere else this distinction shows up.

Scoped to the 17 issues in this dataset with >=2 distinct scorable
ground-truth files (same set scripts/generate_cochange_index.py's pair
metrics use) -- single-file issues would make this identical to
"explored", not a new metric.

Usage:
    python3 scripts/gt_files_touched_fraction.py
"""
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOUCH_CSV = os.path.join(_ROOT, "data", "gt_file_touch_timing.csv")
OUT_CSV = os.path.join(_ROOT, "data", "gt_files_touched_fraction.csv")


def main():
    df = pd.read_csv(TOUCH_CSV)

    n_gt_per_issue = df.groupby(["repo", "issue_idx"])["gt_file"].nunique()
    multi_file_issues = set(n_gt_per_issue[n_gt_per_issue > 1].index)
    df = df[df.apply(lambda r: (r["repo"], r["issue_idx"]) in multi_file_issues, axis=1)]

    rows = []
    group_cols = ["repo", "issue_idx", "model", "map_type", "rep"]
    for keys, g in df.groupby(group_cols, dropna=False):
        repo, issue_idx, model, cond, rep = keys
        n_total = len(g)
        n_touched = (g["first_touch_turn"] != "na").sum()
        n_touched_or_submitted = ((g["first_touch_turn"] != "na") | g["submitted"]).sum()
        rows.append({
            "repo": repo, "issue_idx": issue_idx, "model": model,
            "map_condition_raw": cond, "rep": rep,
            "n_gt_total": n_total, "n_gt_touched": int(n_touched),
            "frac_gt_touched": round(n_touched / n_total, 4),
            "n_gt_touched_or_submitted": int(n_touched_or_submitted),
            "frac_gt_touched_or_submitted": round(n_touched_or_submitted / n_total, 4),
        })
    result = pd.DataFrame(rows)
    result.to_csv(OUT_CSV, index=False)

    print(f"{len(multi_file_issues)} multi-file issues, {len(result)} trials")
    print(f"\nOverall frac_gt_touched distribution:")
    print(result["frac_gt_touched"].describe())
    print(f"\nTrials touching ALL gt files: {(result['frac_gt_touched']==1.0).sum()} "
         f"({(result['frac_gt_touched']==1.0).mean():.1%})")
    print(f"Trials touching NONE: {(result['frac_gt_touched']==0.0).sum()} "
         f"({(result['frac_gt_touched']==0.0).mean():.1%})")
    print(f"\nMean frac_gt_touched by issue:")
    print(result.groupby(["repo", "issue_idx"])["frac_gt_touched"].agg(["mean", "count"])
          .sort_values("mean").to_string())
    print(f"\nSaved -> {OUT_CSV}")


if __name__ == "__main__":
    main()
