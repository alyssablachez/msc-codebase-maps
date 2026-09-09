"""
Study 3 (on-demand/required map tools) -- how many trials called a
map-lookup tool at least once, broken down by treatment (map_condition)
and, within each, by model. Unlike Study 2, tool use here is gated:
submit_answer is rejected (up to MAX_SUBMIT_REJECTIONS=2 times) unless at
least one qualifying lookup tool has been called first, so usage should
be near-100% -- this script quantifies exactly how close, and where the
gap comes from (a trial exhausting its rejection cap without ever
complying would still show as "not used").

Primary sample only: study==3, rep<=3 (2160 trials, 540 per condition).
Same structure as scripts/study2_tool_usage_by_treatment.py.

Usage:
    python3 scripts/study3_tool_usage_by_treatment.py
"""
import os

import pandas as pd

from tool_usage_common import extract_tool_calls

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study3")
OUT_CSV = os.path.join(OUT_DIR, "study3_tool_usage_by_treatment.csv")

MAP_CONDITIONS_ORDER = ["structural", "temporal_frequency", "temporal_cochange", "all_tools"]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["study"] == 3) & (df["rep"] <= 3)].copy()

    df["used_tool"] = df["source_path"].apply(lambda p: len(extract_tool_calls(p)) > 0)

    rows = []
    for cond in MAP_CONDITIONS_ORDER:
        sub = df[df["map_condition"] == cond]
        n_used = int(sub["used_tool"].sum())
        n_total = len(sub)
        rows.append({
            "map_condition": cond, "model": "ALL", "n_trials": n_total,
            "n_used_tool": n_used, "pct_used_tool": round(100 * n_used / n_total, 1),
        })
        for model in sorted(sub["model"].unique()):
            m_sub = sub[sub["model"] == model]
            m_used = int(m_sub["used_tool"].sum())
            m_total = len(m_sub)
            rows.append({
                "map_condition": cond, "model": model, "n_trials": m_total,
                "n_used_tool": m_used, "pct_used_tool": round(100 * m_used / m_total, 1),
            })

    result = pd.DataFrame(rows)
    print(result.to_string(index=False))
    result.to_csv(OUT_CSV, index=False)
    print(f"\nSaved: {OUT_CSV}")


if __name__ == "__main__":
    main()
