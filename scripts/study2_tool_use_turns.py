"""
Study 2 -- average number of map-lookup-tool calls per trial, conditional
on the trial having used the tool at least once (i.e. excluding trials
that never called it, which scripts/study2_tool_usage_by_treatment.py
already showed is a real fraction of trials since tool use is voluntary).
"Turns" here means tool-call turns specifically, not total trial turns --
a trial calling the same lookup tool 3 times across 3 separate turns
counts as 3.

Primary sample only: study==2, rep<=3.

Usage:
    python3 scripts/study2_tool_use_turns.py
"""
import os

import numpy as np
import pandas as pd

from tool_usage_common import extract_tool_calls

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study2")
OUT_CSV = os.path.join(OUT_DIR, "study2_tool_use_turns.csv")

MAP_CONDITIONS_ORDER = ["structural", "temporal_frequency", "temporal_cochange", "all_tools"]


def _describe(n_calls_series):
    s = n_calls_series[n_calls_series > 0]
    return {
        "n_trials_used_tool": len(s),
        "mean_calls_given_used": round(s.mean(), 3) if len(s) else None,
        "median_calls_given_used": s.median() if len(s) else None,
        "std_calls_given_used": round(s.std(), 3) if len(s) > 1 else None,
        "min_calls": int(s.min()) if len(s) else None,
        "max_calls": int(s.max()) if len(s) else None,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["study"] == 2) & (df["rep"] <= 3)].copy()

    df["n_tool_calls"] = df["source_path"].apply(lambda p: len(extract_tool_calls(p)))

    rows = []
    overall = {"map_condition": "ALL", "model": "ALL", **_describe(df["n_tool_calls"])}
    rows.append(overall)

    for cond in MAP_CONDITIONS_ORDER:
        sub = df[df["map_condition"] == cond]
        rows.append({"map_condition": cond, "model": "ALL", **_describe(sub["n_tool_calls"])})
        for model in sorted(sub["model"].unique()):
            m_sub = sub[sub["model"] == model]
            rows.append({"map_condition": cond, "model": model, **_describe(m_sub["n_tool_calls"])})

    result = pd.DataFrame(rows)
    print(result.to_string(index=False))
    result.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")


if __name__ == "__main__":
    main()
