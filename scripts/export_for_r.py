"""
Export a study's primary sample to CSV for the R GLMM scripts
(stats_study{N}_r_*.R). Study 1's version of this export was done ad hoc
inline and never saved as a script; this is the reusable version,
parametrized by --study so it covers Studies 2 and 3 too.

Model names are written with underscores (deepseek_flash, gpt_oss_120b,
ministral_3b, nemotron_super) rather than the hyphenated short names used
in the Python stats scripts, because R factor levels built from
hyphenated strings are awkward in formulas -- matches the convention
already established in data/stats_study1/study1_for_r.csv.

Studies 2 and 3 have no baseline condition of their own -- study==1's
"baseline" is the shared cross-study control (see
scripts/stats_study2_f1.py's docstring for the design rationale).

Usage:
    python3 scripts/export_for_r.py --study 2
    python3 scripts/export_for_r.py --study 3
"""
import argparse
import os

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")

MODEL_SHORT_R = {
    "mistral/ministral-3b-latest":                          "ministral_3b",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b":  "gpt_oss_120b",
    "deepseek/deepseek-v4-flash":                            "deepseek_flash",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B":   "nemotron_super",
}

COLUMNS = [
    "f1", "success", "precision", "recall", "map_condition", "model_short",
    "log_codebase_size", "codebase_size", "issue_id", "repo", "issue_idx", "rep",
    "turns_used", "hit_turn_cap", "total_input_tokens", "total_output_tokens",
    "total_cost", "wall_time_seconds",
]


def load_study_data(study):
    df = pd.read_pickle(DATA_PKL)
    if study == 1:
        df = df[(df["study"] == 1) & (df["rep"] <= 3)].copy()
    else:
        df = df[(df["rep"] <= 3) & ((df["study"] == study) |
                                    ((df["study"] == 1) & (df["map_condition"] == "baseline")))].copy()
    df["log_codebase_size"] = np.log(df["codebase_size"])
    df["model_short"] = df["model"].map(MODEL_SHORT_R)
    # write as 0/1 rather than pandas' "True"/"False" strings, which
    # R's read.csv doesn't coerce to logical (only "TRUE"/"FALSE" does)
    df["success"] = df["success"].astype(int)
    df["hit_turn_cap"] = df["hit_turn_cap"].astype(int)
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", type=int, required=True, choices=[1, 2, 3])
    args = parser.parse_args()

    df = load_study_data(args.study)
    out_dir = os.path.join(_ROOT, "data", f"stats_study{args.study}")
    os.makedirs(out_dir, exist_ok=True)
    out_csv = os.path.join(out_dir, f"study{args.study}_for_r.csv")

    df[COLUMNS].to_csv(out_csv, index=False)
    print(f"Study {args.study} (+shared baseline if study>1): {len(df)} trials, "
         f"conditions: {sorted(df['map_condition'].unique())}")
    print(f"Saved: {out_csv}")


if __name__ == "__main__":
    main()
