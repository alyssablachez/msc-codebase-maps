"""
Compile all trial result JSON files from this study into a single flat
table, saved as data/compiled_results.pkl (plus a companion
data/compiled_results_flagged.csv listing anything excluded and why).

Run once (or whenever new results are added) -- the analysis notebook
loads from the compiled pickle, not by walking raw results itself.

Usage:
    python3 scripts/compile_results.py
    python3 scripts/compile_results.py --out data/compiled_results.pkl
"""
import argparse
import json
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Results for this study (2026-07-14) are consolidated into study_1/results/
# -- previously split across this repo's own results/ (rep0 only, generated
# before the migration to the native-filesystem multi-worker setup) and
# /home/afb225/study1/results/ (the live study, reps 1+, on the native Linux
# filesystem to avoid WSL checkout slowness). Both were merged into
# study_1/results/ once the study finished, mirroring the study_0/ archival
# pattern -- root results/ is now empty/removed, ready for the next study.
# study_0/ (this repo's archived pre-rewrite results) is deliberately
# excluded -- different harness, different schema, superseded experimental
# design.
RESULTS_DIRS = [
    os.path.join(_ROOT, "study_1", "results"),
]

# Only these 4 models are in scope for this analysis (confirmed by user,
# 2026-07-14) -- keyed by folder-safe name (model string, "/" -> "_").
ALLOWED_MODELS = {
    "mistral_ministral-3b-latest":                          "mistral/ministral-3b-latest",
    "deepseek_deepseek-v4-flash":                            "deepseek/deepseek-v4-flash",
    "fireworks_ai_accounts_fireworks_models_gpt-oss-120b":  "fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
    "deepinfra_nvidia_NVIDIA-Nemotron-3-Super-120B-A12B":   "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
}

SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")
DEFAULT_OUT = os.path.join(_ROOT, "data", "compiled_results.pkl")

# A "complete" trial set for one (model, rep) is every (issue, map
# condition) combination in the study design: 45 issues x 4 map
# conditions.
N_ISSUES = 45
N_MAP_CONDITIONS = 4
EXPECTED_PER_REP = N_ISSUES * N_MAP_CONDITIONS

REQUIRED_TOP_KEYS = [
    "model", "repo", "issue_idx", "tier", "role", "map_type", "rep",
    "issue_title", "base_commit", "metrics",
    "final_files_predicted", "final_files_predicted_scorable",
    "ground_truth", "ground_truth_scorable", "scores",
]
REQUIRED_METRICS_KEYS = [
    "total_input_tokens", "total_output_tokens", "total_cost",
    "num_turns", "wall_time_seconds", "stop_reason", "hit_turn_cap",
    "submission_type",
]
REQUIRED_SCORE_KEYS = ["precision", "recall", "f1"]

# Renames the harness's map_type values to clearer condition labels for
# the analysis/plots. "none" is the no-map control; ast_compact reflects
# code *structure*; freq/cochange are both derived from git history, i.e.
# *temporal* signal, but of different kinds (edit frequency vs. co-change
# relationships) -- kept as two distinct conditions rather than merged,
# since they were tested as separate arms of the study.
MAP_CONDITION_LABELS = {
    "none":        "baseline",
    "ast_compact": "structural",
    "freq":        "temporal_frequency",
    "cochange":    "temporal_cochange",
}


def find_result_files():
    """Yield (path, source_dir) for every rep*.json under an allowed
    model directory in any of the configured RESULTS_DIRS."""
    for results_dir in RESULTS_DIRS:
        if not os.path.isdir(results_dir):
            print(f"WARNING: results dir not found, skipping: {results_dir}", file=sys.stderr)
            continue
        for model_dir in sorted(os.listdir(results_dir)):
            if model_dir not in ALLOWED_MODELS:
                continue
            model_path = os.path.join(results_dir, model_dir)
            if not os.path.isdir(model_path):
                continue
            for dirpath, _, filenames in os.walk(model_path):
                for fname in filenames:
                    if fname.startswith("rep") and fname.endswith(".json"):
                        yield os.path.join(dirpath, fname), results_dir


def validate_record(rec):
    """Return a list of problem descriptions (empty if the record is
    clean enough to compile)."""
    problems = []
    for key in REQUIRED_TOP_KEYS:
        if key not in rec:
            problems.append(f"missing top-level key '{key}'")
    if isinstance(rec.get("metrics"), dict):
        for key in REQUIRED_METRICS_KEYS:
            if key not in rec["metrics"]:
                problems.append(f"missing metrics key '{key}'")
    else:
        problems.append("'metrics' missing or not a dict")
    if isinstance(rec.get("scores"), dict):
        for key in REQUIRED_SCORE_KEYS:
            if key not in rec["scores"]:
                problems.append(f"missing scores key '{key}'")
    else:
        problems.append("'scores' missing or not a dict")
    if rec.get("map_type") not in MAP_CONDITION_LABELS:
        problems.append(f"unrecognised map_type '{rec.get('map_type')!r}'")
    return problems


def derive_success(scores):
    """Primary success definition used throughout the analysis: recall
    == 1.0, i.e. every ground-truth file (after the scorable_files()
    package-scope filter already applied by the harness) was found,
    regardless of extra false-positive predictions.

    This is a deliberate analytical choice, not the only defensible one
    -- see the notebook's Step 1 markdown for the justification and for
    how to swap in an exact-match (f1 == 1.0) or any-hit (recall > 0)
    definition instead. precision/recall/f1 are all retained per-trial
    in the compiled table specifically so this can be redefined without
    recompiling.
    """
    recall = scores.get("recall")
    if recall is None:
        return None
    return recall == 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    sel = pd.read_csv(SEL_CSV)
    size_lookup = {
        (row["repo"], int(row["issue_idx"])): (row["tier"], row["python_loc"])
        for _, row in sel.iterrows()
    }

    rows = []
    flagged = []
    seen_keys = {}  # (model, repo, issue_idx, map_type, rep) -> path, catches
                     # duplicates across the two RESULTS_DIRS

    for path, source_dir in find_result_files():
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

        key = (rec["model"], rec["repo"], rec["issue_idx"], rec["map_type"], rec["rep"])
        if key in seen_keys:
            flagged.append({
                "path": path,
                "reason": f"duplicate of {seen_keys[key]} "
                          f"(same model/repo/issue_idx/map_type/rep)",
            })
            continue
        seen_keys[key] = path

        size_key = (rec["repo"], int(rec["issue_idx"]))
        if size_key not in size_lookup:
            flagged.append({
                "path": path,
                "reason": f"issue {size_key} not found in issue_selection_final.csv",
            })
            continue
        tier, codebase_size = size_lookup[size_key]

        m, s = rec["metrics"], rec["scores"]
        rows.append({
            "source_dir":              source_dir,
            "source_path":             path,
            "model":                   rec["model"],
            "codebase":                rec["repo"],
            "issue_idx":               rec["issue_idx"],
            "issue_id":                f"{rec['repo']}/{rec['issue_idx']}",
            "issue_title":             rec["issue_title"],
            "role":                    rec["role"],
            "tier":                    tier,
            "codebase_size":           codebase_size,
            "map_condition_raw":       rec["map_type"],
            "map_condition":           MAP_CONDITION_LABELS[rec["map_type"]],
            "rep":                     rec["rep"],
            "worker_id":               rec.get("worker_id"),
            "base_commit":             rec["base_commit"],
            "ground_truth_files":      rec["ground_truth_scorable"],
            "predicted_files":         rec["final_files_predicted_scorable"],
            "ground_truth_files_raw":  rec["ground_truth"],
            "predicted_files_raw":     rec["final_files_predicted"],
            "precision":               s["precision"],
            "recall":                  s["recall"],
            "f1":                      s["f1"],
            "success":                 derive_success(s),
            "turns_used":              m["num_turns"],
            "hit_turn_cap":            m["hit_turn_cap"],
            "stop_reason":             m["stop_reason"],
            "submission_type":         m["submission_type"],
            "total_input_tokens":      m["total_input_tokens"],
            "total_output_tokens":     m["total_output_tokens"],
            "total_cached_tokens":     m.get("total_cached_tokens"),
            "total_cost":              m["total_cost"],
            "wall_time_seconds":       m["wall_time_seconds"],
        })

    df = pd.DataFrame(rows)

    # ── complete-trial-set filtering ─────────────────────────────────────
    # A (model, rep) pair is "complete" only if it has all 180 trials. Per
    # user instruction: incomplete pairs are excluded from the compiled
    # output, not silently down-weighted or included as-is.
    if len(df):
        counts = df.groupby(["model", "rep"]).size()
    else:
        counts = pd.Series(dtype=int)
    complete_pairs = set(counts[counts == EXPECTED_PER_REP].index)
    incomplete_pairs = counts[counts != EXPECTED_PER_REP]

    df["is_complete_set"] = df.apply(
        lambda r: (r["model"], r["rep"]) in complete_pairs, axis=1)
    df_complete = (df[df["is_complete_set"]]
                   .drop(columns=["is_complete_set"])
                   .reset_index(drop=True))

    # ── report ────────────────────────────────────────────────────────────
    total_scanned = len(rows) + len(flagged)
    print(f"Scanned {total_scanned} result files across {len(RESULTS_DIRS)} "
          f"source directories, {len(ALLOWED_MODELS)} allowed models")
    print(f"  Clean records:   {len(rows)}")
    print(f"  Flagged records: {len(flagged)}")
    if flagged:
        print("\nFlagged (excluded from compiled output):")
        for f in flagged[:50]:
            print(f"  {f['path']}: {f['reason']}")
        if len(flagged) > 50:
            print(f"  ... and {len(flagged) - 50} more (see flagged CSV)")

    print(f"\n(model, rep) pairs found: {len(counts)}")
    print(f"  Complete ({EXPECTED_PER_REP} trials each): {len(complete_pairs)}")
    if len(incomplete_pairs):
        print("  Incomplete (excluded from compiled output):")
        for (model, rep), n in incomplete_pairs.items():
            print(f"    {model} rep{rep}: {n}/{EXPECTED_PER_REP}")

    n_pairs = (df_complete[["model", "rep"]].drop_duplicates().shape[0]
               if len(df_complete) else 0)
    print(f"\nFinal compiled dataset: {len(df_complete)} trials "
          f"from {n_pairs} complete (model, rep) sets")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    df_complete.to_pickle(args.out)
    print(f"\nSaved -> {args.out}")

    flagged_path = args.out.replace(".pkl", "_flagged.csv")
    pd.DataFrame(flagged, columns=["path", "reason"]).to_csv(flagged_path, index=False)
    print(f"Flagged records saved -> {flagged_path}")


if __name__ == "__main__":
    main()
