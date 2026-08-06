"""
Rank issues by whether each Study 2 (voluntary tool-based retrieval)
or Study 3 (submit-gated tool-based retrieval) condition helped or hurt
localisation, relative to that issue's own baseline -- same rationale
as scripts/rank_issues_by_map_effect.py (Study 1's wholesale-map-
injection ranking), generalised to the two tool-based studies.

Baseline is still `map_type == "none"` from study_1/results/ -- Study 2
and Study 3 have no baseline arm of their own (each is exactly 4
conditions: structural / temporal_frequency / temporal_cochange /
all_tools, with a "_required" suffix for Study 3), so every delta in
this script is still against the same no-map, no-tool control used
throughout this project, matching the MECHANISM_GROUPS convention in
scripts/case_study_analysis.py (mechanism_group("none") == "baseline").

For each (repo, issue_idx, condition) with condition in the given
study's 4 conditions:
  - per_model_delta_f1 = mean_f1(model, issue, condition) - mean_f1(model, issue, baseline)
    computed only for models with trials in BOTH the condition and the
    study_1 baseline for that issue (paired, not unpaired)
  - pooled_mean_delta_f1 / _recall = mean of the per-model deltas
  - n_helped / n_hurt / n_neutral = counts of per-model deltas > 0 / < 0 / == 0
  - delta_f1_std = std of per-model deltas (high std = model-dependent effect)
  - max_minus_median_delta_f1 / outlier_model = same single-model-outlier
    diagnostic as the Study 1 script, for the same reason (a pooled mean
    can look near-zero while one model swings hard and the rest sit flat)

No MAP_CONDITION_LABELS renaming needed here (unlike Study 1's script):
Study 2/3's own map_type values (structural, temporal_frequency,
temporal_cochange, all_tools[_required]) are already the clear,
human-readable condition names -- Study 1's script renames ast_compact/
freq/cochange into the same vocabulary.

Usage:
    python3 scripts/rank_issues_by_map_effect_tools.py
    python3 scripts/rank_issues_by_map_effect_tools.py --study 2
    python3 scripts/rank_issues_by_map_effect_tools.py --study 3 --out data/issue_map_effect_ranking_study3.csv
"""
import argparse
import json
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASELINE_RESULTS_DIR = os.path.join(_ROOT, "study_1", "results")

STUDY_CONFIG = {
    2: {
        "results_dir": os.path.join(_ROOT, "study_2", "results"),
        "conditions": ["structural", "temporal_frequency", "temporal_cochange", "all_tools"],
        "default_out": os.path.join(_ROOT, "data", "issue_map_effect_ranking_study2.csv"),
        "label": "Study 2 (voluntary tool-based retrieval)",
    },
    3: {
        "results_dir": os.path.join(_ROOT, "study_3", "results"),
        "conditions": ["structural_required", "temporal_frequency_required",
                        "temporal_cochange_required", "all_tools_required"],
        "default_out": os.path.join(_ROOT, "data", "issue_map_effect_ranking_study3.csv"),
        "label": "Study 3 (submit-gated tool-based retrieval)",
    },
}

REQUIRED_TOP_KEYS = ["model", "repo", "issue_idx", "map_type", "scores"]
REQUIRED_SCORE_KEYS = ["precision", "recall", "f1"]


def _valid(rec):
    for key in REQUIRED_TOP_KEYS:
        if key not in rec:
            return False
    if not isinstance(rec.get("scores"), dict):
        return False
    return all(key in rec["scores"] for key in REQUIRED_SCORE_KEYS)


def _load_dir(results_dir, allowed_map_types):
    rows = []
    if not os.path.isdir(results_dir):
        return pd.DataFrame(rows)
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
                if not _valid(rec):
                    continue
                if rec["map_type"] not in allowed_map_types:
                    continue
                s = rec["scores"]
                rows.append({
                    "model": rec["model"], "repo": rec["repo"],
                    "issue_idx": rec["issue_idx"], "map_type": rec["map_type"],
                    "precision": s["precision"], "recall": s["recall"], "f1": s["f1"],
                })
    return pd.DataFrame(rows)


def rank_for_study(study, out_path):
    cfg = STUDY_CONFIG[study]
    baseline_df = _load_dir(BASELINE_RESULTS_DIR, {"none"})
    cond_df = _load_dir(cfg["results_dir"], set(cfg["conditions"]))
    print(f"\n=== {cfg['label']} ===")
    print(f"Loaded {len(baseline_df)} baseline trials (study_1, map_type=none), "
          f"{len(cond_df)} condition trials across "
          f"{cond_df[['repo', 'issue_idx']].drop_duplicates().shape[0]} issues, "
          f"{cond_df['model'].nunique()} models")

    baseline_cell = (baseline_df.groupby(["model", "repo", "issue_idx"])[["f1", "recall"]]
                      .mean().reset_index()
                      .rename(columns={"f1": "baseline_f1", "recall": "baseline_recall"}))
    cond_cell = (cond_df.groupby(["model", "repo", "issue_idx", "map_type"])[["f1", "recall"]]
                 .mean().reset_index()
                 .rename(columns={"f1": "cond_f1", "recall": "cond_recall"}))

    rows = []
    for condition in cfg["conditions"]:
        cond = cond_cell[cond_cell["map_type"] == condition].drop(columns="map_type")
        merged = cond.merge(baseline_cell, on=["model", "repo", "issue_idx"], how="inner")
        merged["delta_f1"] = merged["cond_f1"] - merged["baseline_f1"]
        merged["delta_recall"] = merged["cond_recall"] - merged["baseline_recall"]

        for (repo, issue_idx), g in merged.groupby(["repo", "issue_idx"]):
            outlier_idx = g["delta_f1"].idxmax()
            rows.append({
                "repo": repo,
                "issue_idx": issue_idx,
                "map_condition_raw": condition,
                "map_condition": condition,
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
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    result.to_csv(out_path, index=False, lineterminator="\n")

    pd.set_option("display.width", 200)
    print(f"\nTop 10 most HELPED (issue, condition) pairs by pooled mean delta_f1:")
    print(result.head(10)[["repo", "issue_idx", "map_condition", "n_models",
                            "pooled_mean_delta_f1", "delta_f1_std", "n_helped_f1", "n_hurt_f1"]].to_string(index=False))

    print(f"\nTop 10 most HURT (issue, condition) pairs by pooled mean delta_f1:")
    print(result.tail(10)[["repo", "issue_idx", "map_condition", "n_models",
                            "pooled_mean_delta_f1", "delta_f1_std", "n_helped_f1", "n_hurt_f1"]].to_string(index=False))

    print(f"\nMost SINGLE-MODEL-DRIVEN effects (highest max_minus_median_delta_f1, "
          f"n_models >= 3):")
    outliers = result[result["n_models"] >= 3].sort_values("max_minus_median_delta_f1", ascending=False)
    print(outliers.head(10)[["repo", "issue_idx", "map_condition", "n_models", "outlier_model",
                              "outlier_model_delta_f1", "median_delta_f1",
                              "max_minus_median_delta_f1"]].to_string(index=False))

    print(f"\nSaved -> {out_path}")
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--study", type=int, choices=[2, 3], default=None,
                     help="Restrict to one study (2 or 3). Default: run both.")
    ap.add_argument("--out", default=None,
                     help="Output CSV path (only valid with --study). Default: "
                          "data/issue_map_effect_ranking_study{2,3}.csv")
    args = ap.parse_args()

    studies = [args.study] if args.study else [2, 3]
    if args.out and not args.study:
        raise SystemExit("--out requires --study")

    for study in studies:
        out_path = args.out or STUDY_CONFIG[study]["default_out"]
        rank_for_study(study, out_path)


if __name__ == "__main__":
    main()
