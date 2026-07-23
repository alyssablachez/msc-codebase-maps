"""
Compare lookup_* tool usage between the free-choice (voluntary) and
required (submit-gated) conditions for a given model -- the analysis
DEVLOG 2026-07-23 calls for once both variants have real batch data.

For each base condition (structural/temporal_frequency/temporal_cochange/
all_tools), reports, separately for the voluntary and required trees:
  - fraction of trials that called the relevant lookup tool(s) at least
    once, and the mean number of calls
  - mean F1
and for required only:
  - fraction of trials with at least one rejected submit_answer, and the
    mean number of rejections
  - a count of "malformed near-miss" tool-call attempts -- a name that
    starts with a required tool's name but isn't an exact match (e.g.
    "lookup_structure{\"path\": \"...\"}", the model/API mangling name
    and arguments together), which the gate's exact-match check can't
    recognize as real usage even though the model's intent was clearly
    to call it. See DEVLOG for why this needs to be surfaced separately
    rather than silently counted as non-compliance.

Usage:
    python3 scripts/compare_tool_usage.py --model mistral/ministral-3b-latest
    python3 scripts/compare_tool_usage.py --model mistral/ministral-3b-latest \
        --results-base /home/afb225/study1/results \
        --out data/tool_usage_comparison_ministral.csv
"""
import argparse
import json
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RESULTS_BASE = "/home/afb225/study1/results"

BASE_CONDITIONS = ["structural", "temporal_frequency", "temporal_cochange", "all_tools"]

REQUIRED_TOOLS_FOR = {
    "structural":         {"lookup_structure"},
    "temporal_frequency": {"lookup_frequency"},
    "temporal_cochange":  {"lookup_cochange"},
    "all_tools":          {"lookup_structure", "lookup_frequency", "lookup_cochange"},
}
ALL_LOOKUP_TOOLS = {"lookup_structure", "lookup_frequency", "lookup_cochange"}


def load_trials(results_base, safe_model, condition):
    """Yield one dict per rep{n}.json found for (safe_model, condition),
    across however many reps exist."""
    model_dir = os.path.join(results_base, safe_model)
    if not os.path.isdir(model_dir):
        return
    for repo in sorted(os.listdir(model_dir)):
        repo_path = os.path.join(model_dir, repo)
        if not os.path.isdir(repo_path):
            continue
        for issue_idx in sorted(os.listdir(repo_path)):
            cond_dir = os.path.join(repo_path, issue_idx, condition)
            if not os.path.isdir(cond_dir):
                continue
            for fname in sorted(os.listdir(cond_dir)):
                if fname.startswith("rep") and fname.endswith(".json"):
                    path = os.path.join(cond_dir, fname)
                    try:
                        with open(path, encoding="utf-8") as f:
                            yield json.load(f)
                    except (json.JSONDecodeError, OSError):
                        continue


def analyze_transcript(transcript, relevant_tools):
    """Return (n_clean_calls, n_malformed_near_miss, n_rejections)."""
    n_clean = 0
    n_malformed = 0
    n_rejected = 0
    for t in transcript:
        if t.get("role") != "tool":
            continue
        name = t.get("name") or ""
        if t.get("rejected"):
            n_rejected += 1
            continue
        if name in relevant_tools:
            n_clean += 1
        elif any(name.startswith(rt) and name != rt for rt in ALL_LOOKUP_TOOLS):
            n_malformed += 1
    return n_clean, n_malformed, n_rejected


def summarize(trials, condition):
    relevant_tools = REQUIRED_TOOLS_FOR[condition]
    rows = []
    for d in trials:
        transcript = d.get("transcript", [])
        n_clean, n_malformed, n_rejected = analyze_transcript(transcript, relevant_tools)
        rows.append({
            "n_clean_calls": n_clean,
            "n_malformed_near_miss": n_malformed,
            "n_rejections": n_rejected,
            "used_tool": n_clean > 0,
            "f1": d.get("scores", {}).get("f1"),
        })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--results-base", default=DEFAULT_RESULTS_BASE)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    safe_model = args.model.replace("/", "_")
    summary_rows = []

    for condition in BASE_CONDITIONS:
        vol_trials = list(load_trials(args.results_base, safe_model, condition))
        req_trials = list(load_trials(args.results_base, safe_model, f"{condition}_required"))

        vol_df = summarize(vol_trials, condition)
        req_df = summarize(req_trials, condition)

        row = {"model": args.model, "condition": condition}

        if len(vol_df):
            row["voluntary_n_trials"] = len(vol_df)
            row["voluntary_pct_used_tool"] = round(vol_df["used_tool"].mean() * 100, 1)
            row["voluntary_mean_calls"] = round(vol_df["n_clean_calls"].mean(), 2)
            row["voluntary_mean_f1"] = round(vol_df["f1"].mean(), 3)
        else:
            row.update({"voluntary_n_trials": 0, "voluntary_pct_used_tool": None,
                        "voluntary_mean_calls": None, "voluntary_mean_f1": None})

        if len(req_df):
            row["required_n_trials"] = len(req_df)
            row["required_pct_used_tool"] = round(req_df["used_tool"].mean() * 100, 1)
            row["required_mean_calls"] = round(req_df["n_clean_calls"].mean(), 2)
            row["required_mean_f1"] = round(req_df["f1"].mean(), 3)
            row["required_pct_had_rejection"] = round((req_df["n_rejections"] > 0).mean() * 100, 1)
            row["required_mean_rejections"] = round(req_df["n_rejections"].mean(), 2)
            row["required_malformed_near_miss_trials"] = int((req_df["n_malformed_near_miss"] > 0).sum())
        else:
            row.update({"required_n_trials": 0, "required_pct_used_tool": None,
                        "required_mean_calls": None, "required_mean_f1": None,
                        "required_pct_had_rejection": None, "required_mean_rejections": None,
                        "required_malformed_near_miss_trials": None})

        summary_rows.append(row)

    df = pd.DataFrame(summary_rows)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 20)
    print(f"=== Tool usage comparison: {args.model} ===\n")
    print(df.to_string(index=False))

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        df.to_csv(args.out, index=False)
        print(f"\nSaved -> {args.out}")


if __name__ == "__main__":
    main()
