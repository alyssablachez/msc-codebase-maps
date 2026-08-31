"""
Collate Studies 1, 2, and 3's raw per-trial results into a single unified
table for the combined chapter. Reuses the condition-harmonization logic
already worked out in notebooks/study_comparison_by_map_type.ipynb
(CONDITION_ROOT, MAP_TYPE_GROUPS/ROLE_ORDER, the 4-model anchor panel)
rather than re-deriving it -- that notebook never persisted its
in-memory trials_df to disk, this script is the first time it is.

Two things this pipeline deliberately does differently from either the
notebook or scripts/compile_results.py, per explicit user decision this
session:

1. Scoring is case-insensitive by construction. gpt-oss-120b was found to
   sometimes recapitalize an otherwise-correct file path on resubmission
   (scripts/audit_case_sensitivity.py: 9/7704 trials, 100% gpt-oss-120b,
   mean F1 delta +0.96 when it happens) -- capitalization has no bearing
   on whether the right file was identified, so this is folded into the
   scoring *criteria* itself (compute_scores below), not a per-row flag.
   The original exact-match scores are kept alongside as
   precision_exact/recall_exact/f1_exact for auditability, but
   precision/recall/f1 (case-insensitive) are the primary columns.

2. No correction and no flag for the "answer overwrite" pattern found by
   scripts/audit_answer_overwrites.py (a well-formed earlier candidate
   answer replaced by a different final one, either via Study 3's
   submit-gate rejection or the forced final-answer elicitation).
   Explicit decision: the gate-rejection cases ARE Study 3's experimental
   manipulation, not a bug, and the content-stated cases are ordinary
   mid-trial deliberation, not a discarded final answer the way Study 0's
   bug was. final_files_predicted is used as-is, exactly as the notebook
   already did.

Condition harmonization:
  study 1 (context injection): none / ast_compact / freq / cochange
  study 2 (voluntary tool use): structural / temporal_frequency /
           temporal_cochange / all_tools
  study 3 (required tool use):  structural_required / ..._required (same
           4, gated submission)
  "none" (study 1 only) is the single shared no-map control for all three
  studies -- study 2/3 were deliberately not given their own baseline,
  confirmed with the user this session.

Only reps 1-3 (the primary 3-rep design) are treated as the main sample
here; reps 4+ (the expanded-replication trials for select issues,
DEVLOG 2026-08-08) are included in the output with their rep number
intact -- filter on rep <= 3 downstream for the primary analysis. Not
silently dropped, since the notebook this is based on didn't drop them
either; kept visible instead (see the rep-distribution printout below).

Usage:
    python3 scripts/collate_studies_1_2_3.py
"""
import json
import os
import sys

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")
MODEL_COSTS_XLSX = os.path.join(_ROOT, "models", "model_costs.xlsx")
OUT_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_FLAGGED = os.path.join(_ROOT, "data", "compiled_results_combined_flagged.csv")

# ── condition harmonization, ported from
# notebooks/study_comparison_by_map_type.ipynb ───────────────────────────────

CONDITION_ROOT = {
    "none": "study_1/results", "ast_compact": "study_1/results",
    "cochange": "study_1/results", "freq": "study_1/results",
    "structural": "study_2/results", "temporal_frequency": "study_2/results",
    "temporal_cochange": "study_2/results", "all_tools": "study_2/results",
    "structural_required": "study_3/results", "temporal_frequency_required": "study_3/results",
    "temporal_cochange_required": "study_3/results", "all_tools_required": "study_3/results",
}

MODELS = [
    "mistral_ministral-3b-latest",
    "fireworks_ai_accounts_fireworks_models_gpt-oss-120b",
    "deepseek_deepseek-v4-flash",
    "deepinfra_nvidia_NVIDIA-Nemotron-3-Super-120B-A12B",
]
MODEL_STRING = {
    "mistral_ministral-3b-latest":                          "mistral/ministral-3b-latest",
    "fireworks_ai_accounts_fireworks_models_gpt-oss-120b":  "fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
    "deepseek_deepseek-v4-flash":                            "deepseek/deepseek-v4-flash",
    "deepinfra_nvidia_NVIDIA-Nemotron-3-Super-120B-A12B":   "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
}
MODEL_TO_PRICE_ROW = {
    "mistral/ministral-3b-latest":                          "ministral-3b",
    "deepseek/deepseek-v4-flash":                            "deepseek-v4-flash",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b":  "gpt-oss-120b",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B":   "Nemotron-3-Super-120B-A12B",
}

# study, harmonized map_condition, delivery_mechanism, submission_mode
CONDITION_META = {
    "none":                        (1, "baseline",           "control",   "n/a"),
    "ast_compact":                 (1, "structural",          "injection", "n/a"),
    "freq":                        (1, "temporal_frequency",  "injection", "n/a"),
    "cochange":                    (1, "temporal_cochange",   "injection", "n/a"),
    "structural":                  (2, "structural",          "on_demand", "voluntary"),
    "temporal_frequency":          (2, "temporal_frequency",  "on_demand", "voluntary"),
    "temporal_cochange":           (2, "temporal_cochange",   "on_demand", "voluntary"),
    "all_tools":                   (2, "all_tools",           "on_demand", "voluntary"),
    "structural_required":         (3, "structural",          "on_demand", "required"),
    "temporal_frequency_required": (3, "temporal_frequency",  "on_demand", "required"),
    "temporal_cochange_required":  (3, "temporal_cochange",   "on_demand", "required"),
    "all_tools_required":          (3, "all_tools",           "on_demand", "required"),
}


def recover_case_only_drops(predicted_raw, predicted_scorable, ground_truth_scorable):
    """harness/run_trial.py's scorable_files() package-scope filter is
    itself case-sensitive, so a miscapitalized-but-otherwise-correct
    prediction (observed: gpt-oss-120b sometimes recapitalizes a path
    on resubmission) gets silently dropped from final_files_predicted_
    scorable entirely -- it never reaches scoring at all, not even as a
    wrong guess. Confirmed directly: gpt-engineer/9/ast_compact/rep4's
    raw prediction ['Gpt_engineer/core/ai.py', ...] scored 0 because
    final_files_predicted_scorable was already [] by the time scores
    were computed. Recovering this means re-adding the correctly-cased
    ground-truth form for any raw prediction that matches a ground-truth
    file case-insensitively but is missing from the scorable set -- a
    1:1 recovery of a genuinely-dropped entry, not an extra prediction."""
    gt_lower_map = {f.lower(): f for f in ground_truth_scorable}
    scorable_lower = {f.lower() for f in predicted_scorable}
    recovered = list(predicted_scorable)
    for p in predicted_raw:
        if p.lower() in gt_lower_map and p.lower() not in scorable_lower:
            recovered.append(gt_lower_map[p.lower()])
            scorable_lower.add(p.lower())
    return recovered


def compute_case_insensitive_scores(predicted, ground_truth):
    """Primary scoring criteria for this pipeline: a predicted file counts
    as a match if it equals a ground-truth file after lowercasing, not
    just on an exact string match. `predicted` should already be the
    case-recovered list from recover_case_only_drops(), not the raw
    final_files_predicted_scorable -- see module docstring point 1."""
    gt_lower = {f.lower(): f for f in ground_truth}
    pred_lower = {f.lower() for f in predicted}
    if not gt_lower:
        return {"precision": None, "recall": None, "f1": None}
    if not pred_lower:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    tp = len(pred_lower & set(gt_lower.keys()))
    precision = tp / len(pred_lower)
    recall = tp / len(gt_lower)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}


def load_price_lookup():
    prices = pd.read_excel(MODEL_COSTS_XLSX)
    by_name = prices.set_index("Model")[["Input Tokens", "Cached Tokens", "Output Tokens"]].to_dict("index")
    lookup = {}
    for model_string, price_row_name in MODEL_TO_PRICE_ROW.items():
        if price_row_name not in by_name:
            raise KeyError(f"'{price_row_name}' (needed for {model_string}) not found in {MODEL_COSTS_XLSX}")
        row = by_name[price_row_name]
        input_price = row["Input Tokens"]
        cached_price = row["Cached Tokens"]
        lookup[model_string] = {
            "input": input_price,
            "cached": cached_price if pd.notna(cached_price) else input_price,
            "output": row["Output Tokens"],
        }
    return lookup


def compute_actual_cost(price_lookup, model, input_tokens, cached_tokens, output_tokens):
    p = price_lookup[model]
    cached = cached_tokens or 0
    uncached_input = input_tokens - cached
    cost = (uncached_input * p["input"] + cached * p["cached"] + output_tokens * p["output"]) / 1e6
    return round(cost, 6)


def derive_success(recall):
    return None if recall is None else recall == 1.0


def main():
    sel = pd.read_csv(SEL_CSV)
    size_lookup = {
        (row["repo"], int(row["issue_idx"])): (row["tier"], row["python_loc"])
        for _, row in sel.iterrows()
    }
    price_lookup = load_price_lookup()

    rows = []
    flagged = []

    for condition, results_subdir in CONDITION_ROOT.items():
        study, map_condition, delivery_mechanism, submission_mode = CONDITION_META[condition]
        base = os.path.join(_ROOT, results_subdir)
        for model_dir in MODELS:
            model_path = os.path.join(base, model_dir)
            if not os.path.isdir(model_path):
                continue
            for repo in sorted(os.listdir(model_path)):
                repo_dir = os.path.join(model_path, repo)
                if not os.path.isdir(repo_dir):
                    continue
                for issue_idx_str in sorted(os.listdir(repo_dir)):
                    cond_dir = os.path.join(repo_dir, issue_idx_str, condition)
                    if not os.path.isdir(cond_dir):
                        continue
                    for fname in sorted(os.listdir(cond_dir)):
                        if not (fname.startswith("rep") and fname.endswith(".json")):
                            continue
                        path = os.path.join(cond_dir, fname)
                        try:
                            with open(path, encoding="utf-8") as f:
                                d = json.load(f)
                        except (json.JSONDecodeError, OSError) as e:
                            flagged.append({"path": path, "reason": f"unreadable/invalid JSON: {e}"})
                            continue

                        scores = d.get("scores", {})
                        metrics = d.get("metrics", {})
                        if scores.get("f1") is None:
                            flagged.append({"path": path, "reason": "scores.f1 is None (no ground truth)"})
                            continue

                        size_key = (repo, int(issue_idx_str))
                        if size_key not in size_lookup:
                            flagged.append({"path": path, "reason": f"issue {size_key} not in issue_selection_final.csv"})
                            continue
                        tier, codebase_size = size_lookup[size_key]

                        predicted_raw_all = d.get("final_files_predicted") or []
                        predicted = d.get("final_files_predicted_scorable") or []
                        ground_truth = d.get("ground_truth_scorable") or []
                        predicted_ci = recover_case_only_drops(predicted_raw_all, predicted, ground_truth)
                        ci_scores = compute_case_insensitive_scores(predicted_ci, ground_truth)

                        model_string = MODEL_STRING[model_dir]
                        input_tokens = metrics.get("total_input_tokens")
                        output_tokens = metrics.get("total_output_tokens")
                        cached_tokens = metrics.get("total_cached_tokens") or 0

                        rows.append({
                            "study":               study,
                            "delivery_mechanism":  delivery_mechanism,
                            "submission_mode":     submission_mode,
                            "map_condition":       map_condition,
                            "map_condition_raw":   condition,
                            "model":               model_string,
                            "repo":                repo,
                            "issue_idx":           int(issue_idx_str),
                            "issue_id":            f"{repo}/{issue_idx_str}",
                            "tier":                tier,
                            "codebase_size":       codebase_size,
                            "rep":                 d.get("rep"),
                            "base_commit":         d.get("base_commit"),
                            "ground_truth_files":  ground_truth,
                            "predicted_files":     predicted_ci,
                            "ground_truth_files_raw": d.get("ground_truth"),
                            "predicted_files_raw":    d.get("final_files_predicted"),
                            # case-insensitive (primary, see module docstring)
                            "precision":           ci_scores["precision"],
                            "recall":              ci_scores["recall"],
                            "f1":                  ci_scores["f1"],
                            "success":             derive_success(ci_scores["recall"]),
                            # exact-match (reference/audit only)
                            "precision_exact":     scores.get("precision"),
                            "recall_exact":        scores.get("recall"),
                            "f1_exact":            scores.get("f1"),
                            "turns_used":          metrics.get("num_turns"),
                            "hit_turn_cap":        metrics.get("hit_turn_cap"),
                            "stop_reason":         metrics.get("stop_reason"),
                            "submission_type":     metrics.get("submission_type"),
                            "total_input_tokens":  input_tokens,
                            "total_output_tokens": output_tokens,
                            "total_cached_tokens": cached_tokens,
                            "total_cost":          (compute_actual_cost(price_lookup, model_string, input_tokens,
                                                                        cached_tokens, output_tokens)
                                                     if input_tokens is not None and output_tokens is not None else None),
                            "total_cost_litellm_raw": metrics.get("total_cost"),
                            "wall_time_seconds":   metrics.get("wall_time_seconds"),
                            "source_path":         path,
                        })

    df = pd.DataFrame(rows)

    print(f"Compiled {len(df)} trials ({len(flagged)} flagged/excluded)")
    print(f"\nBy study:")
    print(df.groupby("study").size().to_string())
    print(f"\nBy (study, map_condition, submission_mode):")
    print(df.groupby(["study", "map_condition", "submission_mode"]).size().to_string())
    print(f"\nBy model:")
    print(df.groupby("model").size().to_string())
    print(f"\nRep distribution (reps 4+ are the expanded-replication trials -- "
          f"DEVLOG 2026-08-08 -- not part of the primary 3-rep design; filter "
          f"rep <= 3 for the primary analysis):")
    print(df["rep"].value_counts().sort_index().to_string())

    n_ci_diff = (df["f1"] != df["f1_exact"]).sum()
    print(f"\nTrials where case-insensitive scoring changed F1 vs. exact match: {n_ci_diff}")

    os.makedirs(os.path.dirname(OUT_PKL), exist_ok=True)
    df.to_pickle(OUT_PKL)
    print(f"\nSaved -> {OUT_PKL}")

    pd.DataFrame(flagged, columns=["path", "reason"]).to_csv(OUT_FLAGGED, index=False)
    print(f"Flagged records -> {OUT_FLAGGED}")


if __name__ == "__main__":
    main()
