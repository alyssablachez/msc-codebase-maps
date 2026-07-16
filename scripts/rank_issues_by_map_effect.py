"""
Rank issues by whether each map condition helped or hurt localisation,
relative to that issue's own baseline (none) trials -- pooling across
*both* study_1/results/ (main 4-model batch) and
study_1/exploratory_results/ (claude-haiku/deepseek-pro/mistral-medium
pilot), with no completeness filtering (unlike compile_results.py),
since a per-model delta is meaningful even from a partial set.

Deliberately keeps model-level detail rather than only reporting a
pooled issue-level number: an issue's "average" map effect can look
near-zero while one model swings hard positive and the rest sit at zero
(see transformers/27 + temporal_cochange + claude-haiku, 2026-07-16) --
that's a real, informative pattern a pooled mean alone would hide.

For each (repo, issue_idx, map_condition) with map_condition != baseline:
  - per_model_delta_f1 = mean_f1(model, issue, condition) - mean_f1(model, issue, baseline)
    computed only for models with trials in BOTH the condition and baseline
    for that issue (paired, not unpaired)
  - pooled_mean_delta_f1 / _recall = mean of the per-model deltas
  - n_helped / n_hurt / n_neutral = counts of per-model deltas > 0 / < 0 / == 0
  - delta_std = std of per-model deltas (high std = model-dependent effect,
    the thing this script is specifically designed to surface)

Usage:
    python3 scripts/rank_issues_by_map_effect.py
    python3 scripts/rank_issues_by_map_effect.py --out data/issue_map_effect_ranking.csv
"""
import argparse
import json
import os

import numpy as np
import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from compile_results import validate_record, MAP_CONDITION_LABELS

RESULTS_DIRS = [
    os.path.join(_ROOT, "study_1", "results"),
    os.path.join(_ROOT, "study_1", "exploratory_results"),
]
DEFAULT_OUT = os.path.join(_ROOT, "data", "issue_map_effect_ranking.csv")


def load_all_trials():
    rows = []
    for results_dir in RESULTS_DIRS:
        if not os.path.isdir(results_dir):
            continue
        for model_dir in sorted(os.listdir(results_dir)):
            model_path = os.path.join(results_dir, model_dir)
            if not os.path.isdir(model_path):
                continue
            for dirpath, _, filenames in os.walk(model_path):
                for fname in filenames:
                    if not (fname.startswith("rep") and fname.endswith(".json")):
                        continue
                    path = os.path.join(dirpath, fname)
                    try:
                        with open(path, encoding="utf-8") as f:
                            rec = json.load(f)
                    except (json.JSONDecodeError, OSError):
                        continue
                    if validate_record(rec):
                        continue
                    s = rec["scores"]
                    rows.append({
                        "model": rec["model"], "repo": rec["repo"],
                        "issue_idx": rec["issue_idx"], "map_type": rec["map_type"],
                        "rep": rec["rep"], "precision": s["precision"],
                        "recall": s["recall"], "f1": s["f1"],
                    })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    df = load_all_trials()
    print(f"Loaded {len(df)} trials across "
          f"{df[['repo','issue_idx']].drop_duplicates().shape[0]} issues, "
          f"{df['model'].nunique()} models")

    # Per-(model, repo, issue, map_type) mean across reps
    per_cell = (df.groupby(["model", "repo", "issue_idx", "map_type"])[["f1", "recall"]]
                  .mean().reset_index())
    baseline = (per_cell[per_cell["map_type"] == "none"]
                .drop(columns="map_type")
                .rename(columns={"f1": "baseline_f1", "recall": "baseline_recall"}))

    rows = []
    for map_type in ["ast_compact", "freq", "cochange"]:
        cond = (per_cell[per_cell["map_type"] == map_type]
                .drop(columns="map_type")
                .rename(columns={"f1": "cond_f1", "recall": "cond_recall"}))
        merged = cond.merge(baseline, on=["model", "repo", "issue_idx"], how="inner")
        merged["delta_f1"] = merged["cond_f1"] - merged["baseline_f1"]
        merged["delta_recall"] = merged["cond_recall"] - merged["baseline_recall"]
        merged["map_condition_raw"] = map_type

        for (repo, issue_idx), g in merged.groupby(["repo", "issue_idx"]):
            # max_minus_median: catches a single model swinging hard while the
            # rest sit flat (e.g. transformers/27 cochange + claude-haiku) --
            # delta_f1_std is kept too, but it under-weights exactly this
            # pattern, since it averages the outlier against several
            # near-zero deltas rather than comparing it to the group's
            # central tendency directly.
            outlier_idx = g["delta_f1"].idxmax()
            rows.append({
                "repo": repo,
                "issue_idx": issue_idx,
                "map_condition_raw": map_type,
                "map_condition": MAP_CONDITION_LABELS[map_type],
                "n_models": len(g),
                "models": ", ".join(sorted(g["model"])),
                "pooled_mean_delta_f1": round(g["delta_f1"].mean(), 4),
                "pooled_mean_delta_recall": round(g["delta_recall"].mean(), 4),
                "delta_f1_std": round(g["delta_f1"].std(), 4) if len(g) > 1 else 0.0,
                "max_minus_median_delta_f1": round(g["delta_f1"].max() - g["delta_f1"].median(), 4),
                "outlier_model": g.loc[outlier_idx, "model"],
                "outlier_model_delta_f1": round(g.loc[outlier_idx, "delta_f1"], 4),
                "median_delta_f1": round(g["delta_f1"].median(), 4),
                "n_helped_f1": int((g["delta_f1"] > 0).sum()),
                "n_hurt_f1": int((g["delta_f1"] < 0).sum()),
                "n_neutral_f1": int((g["delta_f1"] == 0).sum()),
                "per_model_delta_f1": "; ".join(
                    f"{m}={d:+.3f}" for m, d in sorted(zip(g["model"], g["delta_f1"]))
                ),
            })

    result = pd.DataFrame(rows).sort_values("pooled_mean_delta_f1", ascending=False).reset_index(drop=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    result.to_csv(args.out, index=False)

    pd.set_option("display.width", 200)
    print(f"\nTop 10 most HELPED (issue, map_condition) pairs by pooled mean delta_f1:")
    print(result.head(10)[["repo", "issue_idx", "map_condition", "n_models",
                            "pooled_mean_delta_f1", "delta_f1_std", "n_helped_f1", "n_hurt_f1"]].to_string(index=False))

    print(f"\nTop 10 most HURT (issue, map_condition) pairs by pooled mean delta_f1:")
    print(result.tail(10)[["repo", "issue_idx", "map_condition", "n_models",
                            "pooled_mean_delta_f1", "delta_f1_std", "n_helped_f1", "n_hurt_f1"]].to_string(index=False))

    print(f"\nMost SINGLE-MODEL-DRIVEN effects (highest max_minus_median_delta_f1, i.e. one "
          f"model swings hard while the rest sit near the group's median -- n_models >= 3):")
    outliers = result[result["n_models"] >= 3].sort_values("max_minus_median_delta_f1", ascending=False)
    print(outliers.head(10)[["repo", "issue_idx", "map_condition", "n_models", "outlier_model",
                              "outlier_model_delta_f1", "median_delta_f1",
                              "max_minus_median_delta_f1"]].to_string(index=False))

    print(f"\n(delta_f1_std is also in the CSV for general spread, but under-weights this "
          f"exact pattern -- it averages the outlier against several near-zero deltas rather "
          f"than comparing it to the group's central tendency directly.)")

    print(f"\nSaved -> {args.out}")


if __name__ == "__main__":
    main()
