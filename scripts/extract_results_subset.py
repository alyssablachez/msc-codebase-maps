"""
Pull every result record matching a specific (repo, issue_idx, map_type)
combination across both study_1/results/ (the main 4-model batch) and
study_1/exploratory_results/ (the claude-haiku/deepseek-pro/mistral-medium
pilot), and compile them into one summary CSV -- no completeness
filtering (unlike compile_results.py), since a targeted pull like this
should return everything that exists, including partial/exploratory sets.

Reuses models/model_costs.xlsx for cost recomputation where the model has
a price-sheet entry (see compile_results.py); models without one (e.g.
claude-haiku, mistral-medium -- not in the sheet) fall back to the
harness's own recorded total_cost, flagged via cost_source so it's clear
which numbers are validated and which aren't.

Usage:
    python3 scripts/extract_results_subset.py --repo transformers --issue-idx 27 \
        --map-types none cochange --out /tmp/transformers_27.csv
"""
import argparse
import json
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile_results import (
    load_price_lookup, compute_actual_cost, validate_record,
    MAP_CONDITION_LABELS, derive_success,
)

RESULTS_DIRS = [
    ("main", os.path.join(_ROOT, "study_1", "results")),
    ("exploratory", os.path.join(_ROOT, "study_1", "exploratory_results")),
]


def find_matching_files(repo, issue_idx, map_types):
    for source_label, results_dir in RESULTS_DIRS:
        if not os.path.isdir(results_dir):
            continue
        for model_dir in sorted(os.listdir(results_dir)):
            model_path = os.path.join(results_dir, model_dir)
            if not os.path.isdir(model_path):
                continue
            for map_type in map_types:
                map_dir = os.path.join(model_path, repo, str(issue_idx), map_type)
                if not os.path.isdir(map_dir):
                    continue
                for fname in sorted(os.listdir(map_dir)):
                    if fname.startswith("rep") and fname.endswith(".json"):
                        yield os.path.join(map_dir, fname), source_label


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--issue-idx", required=True, type=int)
    ap.add_argument("--map-types", nargs="+", required=True,
                     help="Raw map_type folder names, e.g. none ast_compact freq cochange")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    price_lookup = load_price_lookup()

    rows = []
    flagged = []
    for path, source_label in find_matching_files(args.repo, args.issue_idx, args.map_types):
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            flagged.append({"path": path, "reason": f"unreadable/invalid JSON: {e}"})
            continue

        problems = validate_record(rec)
        if problems:
            flagged.append({"path": path, "reason": "; ".join(problems)})
            continue

        m, s = rec["metrics"], rec["scores"]

        if rec["model"] in price_lookup:
            cost = compute_actual_cost(
                price_lookup, rec["model"], m["total_input_tokens"],
                m.get("total_cached_tokens") or 0, m["total_output_tokens"])
            cost_source = "recomputed_from_price_sheet"
        else:
            cost = m["total_cost"]
            cost_source = "litellm_raw_UNVALIDATED"

        rows.append({
            "source": source_label,
            "model": rec["model"],
            "repo": rec["repo"],
            "issue_idx": rec["issue_idx"],
            "map_condition_raw": rec["map_type"],
            "map_condition": MAP_CONDITION_LABELS.get(rec["map_type"], rec["map_type"]),
            "rep": rec["rep"],
            "role": rec.get("role"),
            "precision": s["precision"],
            "recall": s["recall"],
            "f1": s["f1"],
            "success": derive_success(s),
            "turns_used": m["num_turns"],
            "hit_turn_cap": m["hit_turn_cap"],
            "stop_reason": m["stop_reason"],
            "submission_type": m["submission_type"],
            "total_input_tokens": m["total_input_tokens"],
            "total_output_tokens": m["total_output_tokens"],
            "total_cached_tokens": m.get("total_cached_tokens"),
            "total_cost": cost,
            "cost_source": cost_source,
            "predicted_files": rec["final_files_predicted_scorable"],
            "ground_truth_files": rec["ground_truth_scorable"],
            "source_path": path,
        })

    df = pd.DataFrame(rows)
    df = df.sort_values(["map_condition_raw", "model", "rep"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    df.to_csv(args.out, index=False)

    print(f"Matched {len(rows)} records ({len(flagged)} flagged/excluded) for "
          f"{args.repo}/{args.issue_idx}, map_types={args.map_types}")
    print(f"By source: {df['source'].value_counts().to_dict() if len(df) else {}}")
    print(f"By model: {df['model'].value_counts().to_dict() if len(df) else {}}")
    if flagged:
        print("\nFlagged:")
        for f in flagged:
            print(f"  {f['path']}: {f['reason']}")
    print(f"\nSaved -> {args.out}")


if __name__ == "__main__":
    main()
