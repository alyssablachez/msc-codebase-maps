"""
Studies 1, 2, and 3 -- how much does case-sensitive exact-string scoring
undercount real matches? For every trial, compares F1 under the current
exact-match convention against F1 under a case-insensitive match, and
reports how many trials/files are affected and the resulting F1 delta.

This is a broader, unconditional check across ALL trials (not just the
answer-overwrite subset from scripts/audit_answer_overwrites.py, where the
pattern was first noticed) -- the question here is how pervasive the issue
is in general, not just within already-flagged trials.

Matches scripts/collate_studies_1_2_3.py's recovery logic exactly (kept as
a duplicated copy, not an import, per this project's convention of
self-contained audit scripts -- see e.g. audit_gate_overwrites.py). An
earlier version of this script fell back from final_files_predicted_
scorable to the raw final_files_predicted only when scorable was entirely
empty (`pred = d.get(scorable) or d.get(raw) or []`) -- since Python's `or`
only falls through on a falsy (fully empty) value, a *partial* drop (one
correct file survives harness/run_trial.py's case-sensitive scorable_
files() filter, one miscapitalized file silently doesn't) never triggered
the fallback and was invisible to it. That version found 9 affected
trials; this one finds 11 -- the 2 extra are exactly this partial-drop
case (e.g. pandas/26/temporal_frequency/rep3: one of two raw predictions
survived scorable-filtering, the other didn't, previously invisible).

Usage:
    python3 scripts/audit_case_sensitivity.py
"""
import glob
import json
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDIES = {
    "study_1": os.path.join(_ROOT, "study_1", "results"),
    "study_2": os.path.join(_ROOT, "study_2", "results"),
    "study_3": os.path.join(_ROOT, "study_3", "results"),
}
OUT_CSV = os.path.join(_ROOT, "data", "case_sensitivity_audit.csv")


def recover_case_only_drops(predicted_raw, predicted_scorable, ground_truth_scorable):
    """See scripts/collate_studies_1_2_3.py's identical function for the
    full rationale. Re-adds the correctly-cased ground-truth form for any
    raw prediction that matches a ground-truth file case-insensitively but
    is missing from the scorable set -- a 1:1 recovery of a genuinely-
    dropped entry, checked regardless of whether predicted_scorable is
    fully or only partially missing the match."""
    gt_lower_map = {f.lower(): f for f in ground_truth_scorable}
    scorable_lower = {f.lower() for f in predicted_scorable}
    recovered = list(predicted_scorable)
    for p in predicted_raw:
        if p.lower() in gt_lower_map and p.lower() not in scorable_lower:
            recovered.append(gt_lower_map[p.lower()])
            scorable_lower.add(p.lower())
    return recovered


def _f1(pred_set, gt_set):
    if not gt_set:
        return None
    if not pred_set:
        return 0.0
    tp = len(pred_set & gt_set)
    precision = tp / len(pred_set)
    recall = tp / len(gt_set)
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def case_insensitive_f1(pred, gt):
    gt_lower = {f.lower(): f for f in gt}
    pred_lower = {f.lower() for f in pred}
    if not gt_lower:
        return None
    if not pred_lower:
        return 0.0
    tp = len(pred_lower & set(gt_lower.keys()))
    precision = tp / len(pred_lower)
    recall = tp / len(gt_lower)
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def main():
    rows = []
    for study, results_dir in STUDIES.items():
        files = glob.glob(os.path.join(results_dir, "**", "*.json"), recursive=True)
        print(f"Scanning {study}: {len(files)} trial files...")
        for fp in files:
            try:
                d = json.load(open(fp, encoding="utf-8"))
            except Exception as e:
                print(f"WARNING: could not read {fp}: {e}")
                continue

            pred_raw = d.get("final_files_predicted") or []
            pred_scorable = d.get("final_files_predicted_scorable") or []
            gt = d.get("ground_truth_scorable") or d.get("ground_truth") or []
            if not gt:
                continue

            pred_ci = recover_case_only_drops(pred_raw, pred_scorable, gt)

            f1_exact = _f1(set(pred_scorable), set(gt))
            f1_ci = case_insensitive_f1(pred_ci, gt)

            gt_set = set(gt)
            gt_lower_map = {f.lower(): f for f in gt}
            case_only_matches = [
                (p, gt_lower_map[p.lower()])
                for p in pred_raw
                if p not in gt_set and p.lower() in gt_lower_map
            ]

            if case_only_matches:
                rows.append({
                    "study": study, "model": d.get("model", ""), "repo": d.get("repo", ""),
                    "issue_idx": d.get("issue_idx"), "map_type": d.get("map_type", ""),
                    "rep": d.get("rep"),
                    "f1_exact": f1_exact, "f1_case_insensitive": f1_ci,
                    "f1_delta": (f1_ci - f1_exact) if (f1_ci is not None and f1_exact is not None) else None,
                    "case_only_matches": json.dumps(case_only_matches),
                    "file": os.path.relpath(fp, results_dir),
                })

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    print(f"\n{'='*70}\nTrials with >=1 case-only mismatch: {len(df)}\n{'='*70}")
    print(df.groupby("study").size().to_string())

    if len(df):
        print(f"\nMean F1 delta (case-insensitive minus exact) among affected trials: "
              f"{df['f1_delta'].mean():.4f}")
        print(f"Trials where case-insensitive scoring would change F1 at all: "
              f"{(df['f1_delta'] > 0).sum()}")
        print(f"Trials where it would flip F1 from 0 to something nonzero: "
              f"{((df['f1_exact'] == 0) & (df['f1_case_insensitive'] > 0)).sum()}")

        print(f"\nPer-model breakdown (trials affected):")
        print(df.groupby("model").size().sort_values(ascending=False).to_string())

    print(f"\nSaved: {OUT_CSV}")


if __name__ == "__main__":
    main()
