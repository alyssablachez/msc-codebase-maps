"""
Builds the three-stage failure-pipeline tally for Study 1 (map-as-context)
across all 45 issues x 3 map conditions (135 rows, matching
data/issue_map_effect_ranking.csv):

  1. issue_weak       -- the issue text itself has weak/misleading signal
                          connecting it to the fix (ease_of_connection in
                          {misleading, investigation-required, missing-detail},
                          from data/issue_case_study_notes.csv).
  2. map_weak_for_gt   -- the map, for this issue's specific ground-truth
                          file(s), carries missing/weak/inapplicable signal:
                            - structural: any GT file pruned by the size
                              budget (status != "found" in
                              map_position_metrics.csv).
                            - frequency: the worst-ranked GT file sits in
                              the bottom half of the map by edit count
                              (max pct_through_files > 50).
                            - co-change: either the issue has only one
                              ground-truth file (co-change structurally
                              cannot encode a same-issue file relationship
                              when there's nothing to relate it to), or --
                              for multi-file issues -- every pair of its
                              ground-truth files has zero historical
                              co-change (from data/cochange_pair_metrics.csv).
  3. conversion_gap    -- pooled across the 4 anchor models at rep<=3,
                          the rate at which a ground-truth file gets
                          touched (read_file/lookup_*) but NOT kept in the
                          final submission is >=30%. Uses the "submitted"
                          column added to data/gt_file_touch_timing.csv
                          this session specifically for this touched-vs-
                          kept distinction.
  4. ceiling_effect     -- not a pipeline weakness at all, but a fourth
                          category needed to avoid conflating it with a
                          genuine unexplained gap: baseline F1 (pooled
                          across the 4 anchor models, rep<=3) is already
                          >=0.95, so a delta of ~0 reflects "nowhere to
                          improve," not an unaddressed failure mode.

A row counts as "unhelped" if pooled_mean_delta_f1 <= 0. The headline
number is: of the unhelped rows, how many have at least one of the three
pipeline flags set (an identifiable, attributable weakness), how many
are explained away by a baseline ceiling effect instead, and how many
have neither (a genuine unexplained gap).

Usage:
    python3 scripts/build_failure_pipeline_tally.py
"""
import ast
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_CSV = os.path.join(_ROOT, "data", "failure_pipeline_tally.csv")

MODELS = [
    "mistral/ministral-3b-latest",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
    "deepseek/deepseek-v4-flash",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
]
COND_TO_MAPTYPE = {"ast_compact": "structural", "freq": "frequency", "cochange": "cochange"}
WEAK_EASE = {"misleading", "investigation-required", "missing-detail"}
CONVERSION_GAP_THRESHOLD = 0.30


def load_ranking():
    return pd.read_csv(os.path.join(_ROOT, "data", "issue_map_effect_ranking.csv"))


def stage1_issue_weak():
    notes = pd.read_csv(os.path.join(_ROOT, "data", "issue_case_study_notes.csv"), encoding="latin-1")
    notes = notes[["repo", "issue_idx", "ease_of_connection"]].copy()
    notes["issue_weak"] = notes["ease_of_connection"].isin(WEAK_EASE)
    return notes[["repo", "issue_idx", "issue_weak", "ease_of_connection"]]


def stage2_structural_weak():
    pos = pd.read_csv(os.path.join(_ROOT, "data", "map_position_metrics.csv"))
    struct = pos[pos["map_type"] == "structural"]
    flag = struct.groupby(["repo", "issue_idx"])["status"].apply(lambda s: (s != "found").any())
    return flag.rename("structural_weak").reset_index()


def stage2_frequency_weak():
    pos = pd.read_csv(os.path.join(_ROOT, "data", "map_position_metrics.csv"))
    freq = pos[pos["map_type"] == "frequency"]
    worst = freq.groupby(["repo", "issue_idx"])["pct_through_files"].max()
    flag = (worst > 50).rename("frequency_weak").reset_index()
    return flag


def stage2_cochange_weak():
    sel = pd.read_csv(os.path.join(_ROOT, "data", "issue_selection_final.csv"))
    sel = sel[["repo", "issue_idx", "n_files"]].copy()
    pairs = pd.read_csv(os.path.join(_ROOT, "data", "cochange_pair_metrics.csv"))
    all_zero = pairs.groupby(["repo", "issue_idx"])["cochange_count"].apply(lambda s: (s == 0).all())
    sel = sel.merge(all_zero.rename("all_pairs_zero").reset_index(), on=["repo", "issue_idx"], how="left")
    sel["all_pairs_zero"] = sel["all_pairs_zero"].fillna(False)
    sel["cochange_weak"] = (sel["n_files"] == 1) | ((sel["n_files"] > 1) & sel["all_pairs_zero"])
    return sel[["repo", "issue_idx", "cochange_weak", "n_files"]]


def ceiling_effect():
    df = pd.read_pickle(os.path.join(_ROOT, "data", "compiled_results_combined.pkl"))
    df = df[(df["study"] == 1) & (df["rep"] <= 3) & (df["map_condition"] == "baseline")]
    baseline_f1 = df.groupby(["repo", "issue_idx"])["f1"].mean()
    flag = (baseline_f1 >= 0.95).rename("ceiling_effect")
    return pd.concat([baseline_f1.rename("baseline_f1"), flag], axis=1).reset_index()


def stage3_conversion_gap():
    touch = pd.read_csv(os.path.join(_ROOT, "data", "gt_file_touch_timing.csv"))
    touch = touch[touch["model"].isin(MODELS) & (touch["rep"] <= 3)]
    touch = touch[touch["map_type"].isin(["ast_compact", "freq", "cochange"])]
    touched = touch[touch["first_touch_turn"] != "na"].copy()
    rate = touched.groupby(["repo", "issue_idx", "map_type"])["submitted"].apply(lambda s: (~s).mean())
    n = touched.groupby(["repo", "issue_idx", "map_type"]).size()
    out = pd.DataFrame({"touched_not_kept_rate": rate, "n_touched": n}).reset_index()
    out["conversion_gap"] = out["touched_not_kept_rate"] >= CONVERSION_GAP_THRESHOLD
    return out.rename(columns={"map_type": "map_condition_raw"})


def main():
    rank = load_ranking()
    s1 = stage1_issue_weak()
    s2a = stage2_structural_weak()
    s2b = stage2_frequency_weak()
    s2c = stage2_cochange_weak()
    s3 = stage3_conversion_gap()
    s4 = ceiling_effect()

    df = rank.merge(s1, on=["repo", "issue_idx"], how="left")
    df = df.merge(s2a, on=["repo", "issue_idx"], how="left")
    df = df.merge(s2b, on=["repo", "issue_idx"], how="left")
    df = df.merge(s2c, on=["repo", "issue_idx"], how="left")
    df = df.merge(s3, on=["repo", "issue_idx", "map_condition_raw"], how="left")
    df = df.merge(s4, on=["repo", "issue_idx"], how="left")

    def map_weak_row(row):
        if row["map_condition_raw"] == "ast_compact":
            return bool(row["structural_weak"])
        if row["map_condition_raw"] == "freq":
            return bool(row["frequency_weak"])
        if row["map_condition_raw"] == "cochange":
            return bool(row["cochange_weak"])
        return False

    df["map_weak_for_gt"] = df.apply(map_weak_row, axis=1)
    df["conversion_gap"] = df["conversion_gap"].fillna(False)
    df["ceiling_effect"] = df["ceiling_effect"].fillna(False)
    df["unhelped"] = df["pooled_mean_delta_f1"] <= 0
    df["any_pipeline_flag"] = df["issue_weak"] | df["map_weak_for_gt"] | df["conversion_gap"]
    df["fully_explained"] = df["any_pipeline_flag"] | df["ceiling_effect"]

    cols = ["repo", "issue_idx", "map_condition_raw", "pooled_mean_delta_f1", "unhelped",
           "issue_weak", "ease_of_connection", "map_weak_for_gt", "conversion_gap",
           "touched_not_kept_rate", "n_touched", "baseline_f1", "ceiling_effect",
           "any_pipeline_flag", "fully_explained"]
    df[cols].to_csv(OUT_CSV, index=False)

    n_total = len(df)
    unhelped_df = df[df["unhelped"]]
    n_unhelped = len(unhelped_df)
    n_ceiling = (unhelped_df["ceiling_effect"] & ~unhelped_df["any_pipeline_flag"]).sum()
    n_pipeline_flagged = unhelped_df["any_pipeline_flag"].sum()
    n_genuinely_unexplained = n_unhelped - n_pipeline_flagged - n_ceiling

    print(f"Total (issue, condition) rows: {n_total}")
    print(f"Unhelped (delta F1 <= 0): {n_unhelped} ({n_unhelped/n_total:.1%})")
    print(f"  -- with >=1 identifiable pipeline weakness: {n_pipeline_flagged} ({n_pipeline_flagged/n_unhelped:.1%} of unhelped)")
    print(f"  -- ceiling effect only (baseline already >=0.95 F1): {n_ceiling} ({n_ceiling/n_unhelped:.1%} of unhelped)")
    print(f"  -- genuinely unexplained (neither): {n_genuinely_unexplained} ({n_genuinely_unexplained/n_unhelped:.1%} of unhelped)")
    print()
    print("Breakdown by individual flag, among unhelped rows:")
    print(f"  issue_weak:      {unhelped_df['issue_weak'].sum()} ({unhelped_df['issue_weak'].mean():.1%})")
    print(f"  map_weak_for_gt: {unhelped_df['map_weak_for_gt'].sum()} ({unhelped_df['map_weak_for_gt'].mean():.1%})")
    print(f"  conversion_gap:  {unhelped_df['conversion_gap'].sum()} ({unhelped_df['conversion_gap'].mean():.1%})")
    print(f"  ceiling_effect:  {unhelped_df['ceiling_effect'].sum()} ({unhelped_df['ceiling_effect'].mean():.1%})")
    print()
    print("By condition (share of ALL 45 rows per condition, not just unhelped):")
    print(df.groupby("map_condition_raw")[["unhelped", "issue_weak", "map_weak_for_gt", "conversion_gap",
                                          "ceiling_effect", "fully_explained"]].mean().round(3))
    print()
    print("Genuinely unexplained rows:")
    print(df[(df["unhelped"]) & (~df["fully_explained"])][
        ["repo", "issue_idx", "map_condition_raw", "pooled_mean_delta_f1", "baseline_f1"]
    ].to_string(index=False))
    print(f"\nSaved -> {OUT_CSV}")


if __name__ == "__main__":
    main()
