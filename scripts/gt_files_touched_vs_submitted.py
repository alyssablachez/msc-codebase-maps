"""
Navigation vs. conversion, side by side, for multi-file ground-truth
issues: of the N ground-truth files for a trial's issue, how many did
that trial ever touch (read_file/lookup_* landing on that exact path)
versus how many did it actually keep in its final submission? A direct
companion to scripts/gt_files_touched_fraction.py, which only reports
the touched fraction (plus the touched-or-submitted union) -- this adds
the submitted fraction as its own column so the two can be compared
side by side per issue/condition, rather than only seeing their union.

"touched" and "submitted" are independent per file: a trial can touch a
file and not submit it (found it, didn't keep it -- the conversion gap),
or submit a file without ever touching it (a correct blind guess, see
touch_timing_common.py's docstring). Reports both counts and both
fractions, plus their difference (frac_gt_touched - frac_gt_submitted),
so a positive value flags issues/conditions where exploration
outpaces what actually survives into the answer.

Scoped to the 17 issues in this dataset with >=2 distinct scorable
ground-truth files (same set as scripts/gt_files_touched_fraction.py
and the cochange pair metrics), and to rep<=3 (the primary matched
sample used throughout the Studies 1-3 battery) -- pass --all-reps to
include the expanded-replication reps instead.

Usage:
    python3 scripts/gt_files_touched_vs_submitted.py
    python3 scripts/gt_files_touched_vs_submitted.py --all-reps
"""
import argparse
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOUCH_CSV = os.path.join(_ROOT, "data", "gt_file_touch_timing.csv")
OUT_CSV_TRIAL = os.path.join(_ROOT, "data", "gt_files_touched_vs_submitted_trial.csv")
OUT_CSV_ISSUE = os.path.join(_ROOT, "data", "gt_files_touched_vs_submitted_by_issue.csv")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all-reps", action="store_true",
                       help="include all reps, not just the primary rep<=3 sample")
    args = parser.parse_args()

    df = pd.read_csv(TOUCH_CSV)
    if not args.all_reps:
        df = df[df["rep"] <= 3]

    n_gt_per_issue = df.groupby(["repo", "issue_idx"])["gt_file"].nunique()
    multi_file_issues = set(n_gt_per_issue[n_gt_per_issue > 1].index)
    df = df[df.apply(lambda r: (r["repo"], r["issue_idx"]) in multi_file_issues, axis=1)]

    rows = []
    group_cols = ["repo", "issue_idx", "model", "map_type", "rep"]
    for keys, g in df.groupby(group_cols, dropna=False):
        repo, issue_idx, model, cond, rep = keys
        n_total = len(g)
        n_touched = int((g["first_touch_turn"] != "na").sum())
        n_submitted = int(g["submitted"].sum())
        rows.append({
            "repo": repo, "issue_idx": issue_idx, "model": model,
            "map_condition_raw": cond, "rep": rep,
            "n_gt_total": n_total,
            "n_gt_touched": n_touched, "frac_gt_touched": round(n_touched / n_total, 4),
            "n_gt_submitted": n_submitted, "frac_gt_submitted": round(n_submitted / n_total, 4),
            "touched_minus_submitted_frac": round((n_touched - n_submitted) / n_total, 4),
        })
    trial_df = pd.DataFrame(rows)
    trial_df.to_csv(OUT_CSV_TRIAL, index=False)

    by_issue = trial_df.groupby(["repo", "issue_idx"]).agg(
        n_trials=("frac_gt_touched", "count"),
        n_gt_total=("n_gt_total", "first"),
        mean_frac_touched=("frac_gt_touched", "mean"),
        mean_frac_submitted=("frac_gt_submitted", "mean"),
        mean_gap=("touched_minus_submitted_frac", "mean"),
    ).round(4).sort_values("mean_gap", ascending=False)
    by_issue.to_csv(OUT_CSV_ISSUE)

    print(f"{len(multi_file_issues)} multi-file issues, {len(trial_df)} trials "
         f"({'all reps' if args.all_reps else 'rep<=3 only'})")
    print()
    print(f"Overall mean frac_gt_touched:   {trial_df['frac_gt_touched'].mean():.4f}")
    print(f"Overall mean frac_gt_submitted: {trial_df['frac_gt_submitted'].mean():.4f}")
    print(f"Overall mean gap (touched - submitted): {trial_df['touched_minus_submitted_frac'].mean():.4f}")
    print()
    print("By issue, sorted by largest touched-vs-submitted gap:")
    print(by_issue.to_string())
    print(f"\nSaved -> {OUT_CSV_TRIAL}")
    print(f"Saved -> {OUT_CSV_ISSUE}")


if __name__ == "__main__":
    main()
