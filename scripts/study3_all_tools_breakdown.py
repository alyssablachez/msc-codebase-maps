"""
Study 3 -- within the `all_tools_required` treatment, which tool(s) did
the model call to satisfy the gate (satisfied by any one of the three,
per methodology -- the gate does not require all three). Same structure
as scripts/study2_all_tools_breakdown.py; the interesting contrast is
whether required trials show the same lookup_structure-dominant
preference Study 2 showed voluntarily, or whether being forced to comply
flattens that preference toward whichever tool is easiest/fastest to
satisfy the gate with.

Primary sample only: study==3, rep<=3, map_condition=="all_tools" (540 trials).

Usage:
    python3 scripts/study3_all_tools_breakdown.py
"""
import os

import pandas as pd

from tool_usage_common import MAP_TOOL_NAMES, extract_tool_calls

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study3")
OUT_CSV = os.path.join(OUT_DIR, "study3_all_tools_breakdown.csv")
OUT_CSV_DISTINCT = os.path.join(OUT_DIR, "study3_all_tools_n_distinct_tools_used.csv")

TOOL_ORDER = ["lookup_structure", "lookup_frequency", "lookup_cochange"]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["study"] == 3) & (df["rep"] <= 3) & (df["map_condition"] == "all_tools")].copy()
    n_total = len(df)

    df["tool_calls"] = df["source_path"].apply(extract_tool_calls)
    df["distinct_tools_used"] = df["tool_calls"].apply(lambda calls: len(set(calls)))

    rows = []
    for tool in TOOL_ORDER:
        call_counts = df["tool_calls"].apply(lambda calls, t=tool: calls.count(t))
        used_mask = call_counts > 0
        n_used = int(used_mask.sum())
        rows.append({
            "tool": tool,
            "n_trials": n_total,
            "n_trials_used_at_least_once": n_used,
            "pct_trials_used_at_least_once": round(100 * n_used / n_total, 1),
            "total_calls_across_all_trials": int(call_counts.sum()),
            "mean_calls_given_used": round(call_counts[used_mask].mean(), 3) if n_used else None,
        })
    result = pd.DataFrame(rows)
    print(result.to_string(index=False))
    result.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")

    dist = df["distinct_tools_used"].value_counts().sort_index()
    dist_df = pd.DataFrame({
        "n_distinct_tools_used": dist.index,
        "n_trials": dist.values,
        "pct_trials": (100 * dist.values / n_total).round(1),
    })
    print()
    print(dist_df.to_string(index=False))
    dist_df.to_csv(OUT_CSV_DISTINCT, index=False)
    print(f"\nSaved: {OUT_CSV_DISTINCT}")


if __name__ == "__main__":
    main()
