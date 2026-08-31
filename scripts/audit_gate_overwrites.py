"""
Study 3 (submit-gated "required" conditions) -- screen for trials where a
correctly-formatted submit_answer attempt was REJECTED by the required-tool
gate, and the eventual accepted answer (final_files_predicted) differs from
that refused attempt. This is a distinct failure mode from Study 0's
FINAL_ANSWER_PROMPT-overwrite bug (harness/run_trial.py, current era):
that bug is fixed here (the final-answer fallback now forces a submit_answer
tool call rather than freeform text, see harness/run_trial.py's elicitation
block) -- what's being screened for instead is the submit-gate itself
(harness/run_trial_*_required.py) discarding a valid, well-formed answer
because the required lookup tool hadn't been called yet, and the model's
*eventual* accepted answer turning out different (often worse) from what it
had already correctly identified before the rejection.

"Correctly formatted" here means: a non-empty list of string file paths in
the rejected submit_answer call's args -- not assessing correctness against
ground truth, only whether it was a well-formed, genuine answer attempt
(the same bar Study 0's audit used for "recoverable").

For every trial with >=1 rejected submit_answer attempt, this records the
LAST such rejected attempt (closest to the eventual outcome) and compares
it to final_files_predicted: same set, subset/superset, or genuinely
different -- plus F1 for both against ground_truth_scorable, so the actual
performance cost (if any) of the rejection is visible, not just whether the
file lists differ syntactically.

Usage:
    python3 scripts/audit_gate_overwrites.py
"""
import glob
import json
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDY3_RESULTS = os.path.join(_ROOT, "study_3", "results")
OUT_CSV = os.path.join(_ROOT, "study_3", "logs", "gate_overwrite_audit.csv")


def _is_well_formed(files):
    return isinstance(files, list) and len(files) > 0 and all(isinstance(f, str) and f.strip() for f in files)


def _f1(pred, gt):
    p, t = set(pred), set(gt)
    if not t:
        return None
    if not p:
        return 0.0
    tp = len(p & t)
    precision = tp / len(p)
    recall = tp / len(t)
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def classify_trial(d):
    transcript = d.get("transcript", [])
    rejected_submits = [
        t for t in transcript
        if t.get("rejected") and t.get("name") == "submit_answer" and "args" in t
    ]
    if not rejected_submits:
        return None

    last_rejected = rejected_submits[-1]
    refused_files = last_rejected.get("args", {}).get("files", [])
    well_formed = _is_well_formed(refused_files)

    final_files = d.get("final_files_predicted") or []
    gt = d.get("ground_truth_scorable") or d.get("ground_truth") or []

    refused_set = set(refused_files) if well_formed else set()
    final_set = set(final_files)

    if not well_formed:
        relation = "refused_malformed"
    elif refused_set == final_set:
        relation = "identical"
    elif refused_set < final_set:
        relation = "final_superset"
    elif refused_set > final_set:
        relation = "final_subset"
    elif refused_set & final_set:
        relation = "partial_overlap"
    else:
        relation = "disjoint"

    return {
        "model":               d.get("model", ""),
        "repo":                d.get("repo", ""),
        "issue_idx":           d.get("issue_idx"),
        "map_type":            d.get("map_type", ""),
        "rep":                 d.get("rep"),
        "n_rejected_submits":  len(rejected_submits),
        "refused_well_formed": well_formed,
        "refused_files":       json.dumps(refused_files),
        "final_files":         json.dumps(final_files),
        "relation":            relation,
        "refused_f1":          _f1(refused_files, gt) if well_formed else None,
        "final_f1":            _f1(final_files, gt),
        "stop_reason":         d.get("metrics", {}).get("stop_reason", ""),
    }


def main():
    files = glob.glob(os.path.join(STUDY3_RESULTS, "**", "*.json"), recursive=True)
    print(f"Scanning {len(files)} Study 3 trial files...")

    rows = []
    for fp in files:
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception as e:
            print(f"WARNING: could not read {fp}: {e}")
            continue
        row = classify_trial(d)
        if row is not None:
            row["file"] = os.path.relpath(fp, STUDY3_RESULTS)
            rows.append(row)

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    print(f"\nTrials with >=1 rejected submit_answer attempt: {len(df)} / {len(files)}")
    print(f"\nRelation between last-refused answer and final accepted answer:")
    print(df["relation"].value_counts().to_string())

    well_formed_diff = df[(df["refused_well_formed"]) & (df["relation"] != "identical")]
    print(f"\nWell-formed refused answer that ended up DIFFERENT from the final one: "
          f"{len(well_formed_diff)}")

    worse = well_formed_diff[well_formed_diff["final_f1"] < well_formed_diff["refused_f1"]]
    better = well_formed_diff[well_formed_diff["final_f1"] > well_formed_diff["refused_f1"]]
    same_f1 = well_formed_diff[well_formed_diff["final_f1"] == well_formed_diff["refused_f1"]]
    print(f"  -> final F1 WORSE than the refused answer's F1 would have been: {len(worse)}")
    print(f"  -> final F1 BETTER than the refused answer's F1:                {len(better)}")
    print(f"  -> same F1 despite different file sets:                        {len(same_f1)}")

    if len(worse):
        print(f"\n{'='*70}")
        print("TRIALS WHERE THE GATE REJECTION MADE THE OUTCOME WORSE")
        print(f"{'='*70}")
        for _, r in worse.iterrows():
            print(f"  {r['file']}")
            print(f"    refused (F1={r['refused_f1']:.3f}): {r['refused_files']}")
            print(f"    final   (F1={r['final_f1']:.3f}): {r['final_files']}")
            print(f"    n_rejected_submits={r['n_rejected_submits']}  stop_reason={r['stop_reason']}")
            print()

    print(f"Saved: {OUT_CSV}")


if __name__ == "__main__":
    main()
