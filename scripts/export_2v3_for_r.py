"""
Export the Study 2-vs-3 direct comparison sample to CSV for
scripts/stats_study2v3_r_*.R. Unlike scripts/export_for_r.py (which
exports one study plus the shared Study 1 baseline), this is Study 2 and
Study 3 together with no baseline row -- both share the same 4
map_condition levels and delivery_mechanism="on_demand", differing only
in submission_mode (voluntary vs. required). That's the 4th test in the
agreed battery: does making tool use mandatory change outcomes relative
to leaving it optional, holding the map conditions and delivery mechanism
fixed.

Usage:
    python3 scripts/export_2v3_for_r.py
"""
import os

import numpy as np
import pandas as pd

from export_for_r import MODEL_SHORT_R

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study2v3")

COLUMNS = [
    "f1", "success", "precision", "recall", "map_condition", "submission_mode", "model_short",
    "log_codebase_size", "codebase_size", "issue_id", "repo", "issue_idx", "rep",
    "turns_used", "hit_turn_cap", "total_input_tokens", "total_output_tokens",
    "total_cost", "wall_time_seconds",
]


def load_2v3_data():
    df = pd.read_pickle(DATA_PKL)
    df = df[(df["rep"] <= 3) & (df["study"].isin([2, 3]))].copy()
    df["log_codebase_size"] = np.log(df["codebase_size"])
    df["model_short"] = df["model"].map(MODEL_SHORT_R)
    df["success"] = df["success"].astype(int)
    df["hit_turn_cap"] = df["hit_turn_cap"].astype(int)
    return df


def main():
    df = load_2v3_data()
    os.makedirs(OUT_DIR, exist_ok=True)
    out_csv = os.path.join(OUT_DIR, "study2v3_for_r.csv")

    df[COLUMNS].to_csv(out_csv, index=False)
    print(f"Study 2 vs 3: {len(df)} trials, submission_mode: {sorted(df['submission_mode'].unique())}, "
         f"map_condition: {sorted(df['map_condition'].unique())}")
    print(f"Saved: {out_csv}")


if __name__ == "__main__":
    main()
