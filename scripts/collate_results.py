"""
Collate all trial results into a unified DataFrame and produce summary statistics.

Outputs:
  results_all.csv              — one row per trial
  results_summary_tables.txt   — all summary tables (labelled sections)

Usage:
    python3 scripts/collate_results.py
"""
import glob
import io
import json
import os
import re
import sys

import pandas as pd

_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESULTS_DIR = os.path.join(_ROOT, "results")
OUT_CSV     = os.path.join(_ROOT, "results_all.csv")
OUT_TABLES  = os.path.join(_ROOT, "results_summary_tables.txt")

# ── model metadata ────────────────────────────────────────────────────────────

FOLDERS = [
    "deepinfra_Qwen_Qwen3-VL-30B-A3B-Instruct",
    "deepinfra_Qwen_Qwen3-VL-235B-A22B-Instruct",
    "fireworks_ai_accounts_fireworks_models_gpt-oss-20b",
    "fireworks_ai_accounts_fireworks_models_gpt-oss-120b",
    "mistral_ministral-3b-latest",
    "mistral_ministral-14b-latest",
    "deepseek_deepseek-v4-flash",
    "deepseek_deepseek-v4-pro",
    "deepinfra_nvidia_Nemotron-3-Nano-30B-A3B",
    "deepinfra_nvidia_NVIDIA-Nemotron-3-Super-120B-A12B",
    "deepinfra_zai-org_GLM-4.7-Flash",
    "deepinfra_zai-org_GLM-4.7",
]

# (pair, size, provider, architecture)
MODEL_META = {
    "deepinfra_Qwen_Qwen3-VL-30B-A3B-Instruct":          (1, "small", "deepinfra", "MoE"),
    "deepinfra_Qwen_Qwen3-VL-235B-A22B-Instruct":         (1, "large", "deepinfra", "MoE"),
    "fireworks_ai_accounts_fireworks_models_gpt-oss-20b":  (2, "small", "fireworks", "MoE"),
    "fireworks_ai_accounts_fireworks_models_gpt-oss-120b": (2, "large", "fireworks", "MoE"),
    "mistral_ministral-3b-latest":                         (3, "small", "mistral",   "dense"),
    "mistral_ministral-14b-latest":                        (3, "large", "mistral",   "dense"),
    "deepseek_deepseek-v4-flash":                          (4, "small", "deepseek",  "MoE"),
    "deepseek_deepseek-v4-pro":                            (4, "large", "deepseek",  "MoE"),
    "deepinfra_nvidia_Nemotron-3-Nano-30B-A3B":           (5, "small", "deepinfra", "MoE"),
    "deepinfra_nvidia_NVIDIA-Nemotron-3-Super-120B-A12B": (5, "large", "deepinfra", "MoE"),
    "deepinfra_zai-org_GLM-4.7-Flash":                    (6, "small", "deepinfra", "MoE"),
    "deepinfra_zai-org_GLM-4.7":                          (6, "large", "deepinfra", "MoE"),
}

PAIR_NAMES = {
    1: "Qwen3-VL",
    2: "gpt-oss",
    3: "Ministral",
    4: "DeepSeek-V4",
    5: "Nemotron-3",
    6: "GLM-4.7",
}

FILE_PAT = re.compile(r"^task_(\d+)_(none|ast|ast_compact)_rep(\d+)\.json$")


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_empty(pred):
    if pred is None:
        return True
    return len(pred) == 0 or all((p or "").strip() == "" for p in pred)


def _short(model_dir):
    """Short display name for a model_dir."""
    return {
        "deepinfra_Qwen_Qwen3-VL-30B-A3B-Instruct":          "Qwen3-VL-30B",
        "deepinfra_Qwen_Qwen3-VL-235B-A22B-Instruct":         "Qwen3-VL-235B",
        "fireworks_ai_accounts_fireworks_models_gpt-oss-20b":  "gpt-oss-20b",
        "fireworks_ai_accounts_fireworks_models_gpt-oss-120b": "gpt-oss-120b",
        "mistral_ministral-3b-latest":                         "ministral-3b",
        "mistral_ministral-14b-latest":                        "ministral-14b",
        "deepseek_deepseek-v4-flash":                          "deepseek-flash",
        "deepseek_deepseek-v4-pro":                            "deepseek-pro",
        "deepinfra_nvidia_Nemotron-3-Nano-30B-A3B":           "Nemotron-Nano-30B",
        "deepinfra_nvidia_NVIDIA-Nemotron-3-Super-120B-A12B": "Nemotron-Super-120B",
        "deepinfra_zai-org_GLM-4.7-Flash":                    "GLM-4.7-Flash",
        "deepinfra_zai-org_GLM-4.7":                          "GLM-4.7",
    }.get(model_dir, model_dir)


# ── load data ─────────────────────────────────────────────────────────────────

def load_results():
    rows = []
    for folder in FOLDERS:
        folder_path = os.path.join(RESULTS_DIR, folder)
        if not os.path.isdir(folder_path):
            print(f"WARNING: folder not found: {folder}", file=sys.stderr)
            continue
        pair, size, provider, arch = MODEL_META[folder]
        for fname in os.listdir(folder_path):
            if not FILE_PAT.match(fname):
                continue
            path = os.path.join(folder_path, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
            except Exception as e:
                print(f"WARNING: could not read {path}: {e}", file=sys.stderr)
                continue

            metrics = d.get("metrics", {})
            scores  = d.get("scores",  {})
            pred    = d.get("final_files_predicted") or []
            gt      = d.get("ground_truth") or []

            rows.append({
                # identity
                "model_dir":   folder,
                "model_short": _short(folder),
                "model":       d.get("model", ""),
                "task_idx":    d.get("task_idx"),
                "map_type":    d.get("map_type"),
                "rep":         d.get("rep"),
                "issue_title": d.get("issue_title", ""),
                "base_commit": d.get("base_commit", ""),
                # metrics
                "input_tokens":  metrics.get("total_input_tokens"),
                "output_tokens": metrics.get("total_output_tokens"),
                "cost":          metrics.get("total_cost"),
                "turns":         metrics.get("num_turns"),
                "wall_time":     metrics.get("wall_time_seconds"),
                "stop_reason":   metrics.get("stop_reason", ""),
                # scores
                "precision": scores.get("precision"),
                "recall":    scores.get("recall"),
                "f1":        scores.get("f1"),
                # derived
                "empty_prediction":   _is_empty(pred),
                "n_predicted_files":  len([p for p in pred if (p or "").strip()]),
                "n_ground_truth_files": len(gt),
                # grouping
                "model_pair":    pair,
                "pair_name":     PAIR_NAMES[pair],
                "model_size":    size,
                "provider":      provider,
                "architecture":  arch,
            })

    df = pd.DataFrame(rows)
    df["task_type"] = df["n_ground_truth_files"].apply(
        lambda n: "single_file" if n == 1 else "multi_file"
    )
    return df


# ── formatting helpers ────────────────────────────────────────────────────────

def _fmt(df, floatfmt=".3f"):
    return df.to_string(float_format=lambda x: f"{x:{floatfmt}}")


def section(title):
    bar = "=" * 70
    return f"\n{bar}\n{title}\n{bar}\n"


# ── summary builders ──────────────────────────────────────────────────────────

def summary_overall(df, out):
    out.write(section("1. OVERALL DATASET SUMMARY"))

    # Completeness per model
    counts = (df.groupby("model_short")
                .size()
                .reset_index(name="n_trials")
                .assign(completeness=lambda x: x["n_trials"].apply(lambda n: f"{n}/75")))
    # Reorder to match FOLDERS order
    order = [_short(f) for f in FOLDERS]
    counts["model_short"] = pd.Categorical(counts["model_short"], categories=order, ordered=True)
    counts = counts.sort_values("model_short")

    incomplete = counts[counts["n_trials"] < 75]

    out.write("Trials per model:\n")
    out.write(counts.to_string(index=False))
    out.write("\n")
    if len(incomplete):
        out.write(f"\n** INCOMPLETE MODELS (< 75 trials): **\n")
        out.write(incomplete.to_string(index=False))
        out.write("\n")
    else:
        out.write("\nAll models complete (75/75).\n")

    # Empty prediction rate
    out.write("\nEmpty prediction rate by model:\n")
    emp = (df.groupby("model_short")
             .agg(n_trials=("f1", "count"), n_empty=("empty_prediction", "sum"))
             .assign(pct_empty=lambda x: (x["n_empty"] / x["n_trials"] * 100).round(1))
             .reset_index())
    emp["model_short"] = pd.Categorical(emp["model_short"], categories=order, ordered=True)
    emp = emp.sort_values("model_short")
    out.write(emp.to_string(index=False))
    out.write(f"\n\nOverall empty rate: {df['empty_prediction'].sum()}/{len(df)} "
              f"({df['empty_prediction'].mean()*100:.1f}%)\n")

    # Stop reason distribution
    out.write("\nStop reason distribution by model:\n")
    sr = (df.groupby(["model_short", "stop_reason"])
            .size()
            .unstack(fill_value=0)
            .reset_index())
    sr["model_short"] = pd.Categorical(sr["model_short"], categories=order, ordered=True)
    sr = sr.sort_values("model_short")
    out.write(sr.to_string(index=False))
    out.write("\n")


def summary_accuracy(df, out):
    out.write(section("2. ACCURACY SUMMARY"))
    order = [_short(f) for f in FOLDERS]

    # Mean F1 / precision / recall per model
    out.write("Mean F1 / precision / recall per model:\n")
    acc = (df.groupby("model_short")[["f1", "precision", "recall"]]
             .mean()
             .round(4)
             .reset_index())
    acc["model_short"] = pd.Categorical(acc["model_short"], categories=order, ordered=True)
    acc = acc.sort_values("model_short")
    out.write(_fmt(acc))
    out.write("\n")

    # Mean F1 per map condition overall
    out.write("\nMean F1 per map condition (overall):\n")
    out.write(_fmt(df.groupby("map_type")[["f1"]].mean().round(4)))
    out.write("\n")

    # Mean F1 per map condition per model
    out.write("\nMean F1 per map condition per model:\n")
    pivot = (df.groupby(["model_short", "map_type"])["f1"]
               .mean()
               .round(4)
               .unstack()
               .reset_index())
    pivot["model_short"] = pd.Categorical(pivot["model_short"], categories=order, ordered=True)
    pivot = pivot.sort_values("model_short")
    out.write(_fmt(pivot))
    out.write("\n")

    # Mean F1 per task per model
    out.write("\nMean F1 per task per model:\n")
    pivot2 = (df.groupby(["model_short", "task_idx"])["f1"]
                .mean()
                .round(4)
                .unstack()
                .reset_index())
    pivot2["model_short"] = pd.Categorical(pivot2["model_short"], categories=order, ordered=True)
    pivot2 = pivot2.sort_values("model_short")
    out.write(_fmt(pivot2))
    out.write("\n")

    # Mean F1 by model_size per pair
    out.write("\nMean F1 by model size per pair:\n")
    size_pair = (df.groupby(["pair_name", "model_size"])["f1"]
                   .mean()
                   .round(4)
                   .unstack()
                   .reset_index())
    out.write(_fmt(size_pair))
    out.write("\n")

    # Mean F1 by task_type
    out.write("\nMean F1 by task type (single vs multi-file):\n")
    out.write(_fmt(df.groupby("task_type")[["f1", "precision", "recall"]].mean().round(4)))
    out.write("\n")


def summary_efficiency(df, out):
    out.write(section("3. EFFICIENCY SUMMARY"))
    order = [_short(f) for f in FOLDERS]

    # Mean turns per model
    out.write("Mean turns per model:\n")
    eff = (df.groupby("model_short")[["turns", "wall_time", "input_tokens", "output_tokens", "cost"]]
             .mean()
             .round(2)
             .reset_index())
    eff["model_short"] = pd.Categorical(eff["model_short"], categories=order, ordered=True)
    eff = eff.sort_values("model_short")
    out.write(_fmt(eff))
    out.write("\n(Note: wall_time not comparable across providers — API latency varies)\n")

    # Mean turns and tokens per map condition
    out.write("\nMean turns / input_tokens / output_tokens per map condition:\n")
    map_eff = (df.groupby("map_type")[["turns", "input_tokens", "output_tokens"]]
                 .mean()
                 .round(2))
    out.write(_fmt(map_eff))
    out.write("\n")

    # Stop reason breakdown per model
    out.write("\nStop reason breakdown per model (%):\n")
    sr_pct = (df.groupby(["model_short", "stop_reason"])
                .size()
                .unstack(fill_value=0))
    sr_pct = sr_pct.div(sr_pct.sum(axis=1), axis=0).mul(100).round(1).reset_index()
    sr_pct["model_short"] = pd.Categorical(sr_pct["model_short"], categories=order, ordered=True)
    sr_pct = sr_pct.sort_values("model_short")
    out.write(_fmt(sr_pct))
    out.write("\n")


def summary_pairs(df, out):
    out.write(section("4. PER-PAIR COMPARISON"))

    rows = []
    for pair_id in range(1, 7):
        sub = df[df["model_pair"] == pair_id]
        pair_name = PAIR_NAMES[pair_id]
        for size in ("small", "large"):
            s = sub[sub["model_size"] == size]
            if s.empty:
                continue
            rows.append({
                "pair":         f"P{pair_id} {pair_name}",
                "size":         size,
                "model":        s["model_short"].iloc[0],
                "mean_f1":      round(s["f1"].mean(), 4),
                "mean_turns":   round(s["turns"].mean(), 2),
                "mean_in_tok":  round(s["input_tokens"].mean(), 0),
                "mean_out_tok": round(s["output_tokens"].mean(), 0),
                "n":            len(s),
            })

    pair_df = pd.DataFrame(rows)
    out.write(_fmt(pair_df, floatfmt=".4f"))
    out.write("\n")

    # Verdict: does large outperform small?
    out.write("\nLarge vs small F1 delta per pair:\n")
    for pair_id in range(1, 7):
        sub = pair_df[pair_df["pair"].str.startswith(f"P{pair_id}")]
        if len(sub) < 2:
            continue
        small_f1 = sub[sub["size"] == "small"]["mean_f1"].values[0]
        large_f1 = sub[sub["size"] == "large"]["mean_f1"].values[0]
        delta = large_f1 - small_f1
        verdict = "large > small" if delta > 0 else ("large < small" if delta < 0 else "tie")
        pair_name = PAIR_NAMES[pair_id]
        out.write(f"  P{pair_id} {pair_name:<14}: Δ = {delta:+.4f}  ({verdict})\n")
    out.write("\n")


def summary_map_effect(df, out):
    out.write(section("5. MAP CONDITION EFFECT"))

    # F1 by map
    out.write("Mean F1 by map condition:\n")
    m_f1 = df.groupby("map_type")["f1"].agg(["mean", "median", "std"]).round(4)
    out.write(_fmt(m_f1))
    out.write("\n")

    # Turns by map
    out.write("\nMean turns by map condition:\n")
    m_turns = df.groupby("map_type")["turns"].agg(["mean", "median", "std"]).round(2)
    out.write(_fmt(m_turns))
    out.write("\n")

    # Input tokens by map
    out.write("\nMean input tokens by map condition:\n")
    m_tok = df.groupby("map_type")[["input_tokens", "output_tokens"]].mean().round(0)
    out.write(_fmt(m_tok))
    out.write("\n")

    # Per-model F1 lift from none → ast and none → ast_compact
    out.write("\nF1 lift per model: none → ast and none → ast_compact:\n")
    order = [_short(f) for f in FOLDERS]
    pivot = (df.groupby(["model_short", "map_type"])["f1"]
               .mean()
               .unstack()
               .reset_index())
    pivot["model_short"] = pd.Categorical(pivot["model_short"], categories=order, ordered=True)
    pivot = pivot.sort_values("model_short")
    for col in ["ast", "ast_compact"]:
        if col in pivot.columns and "none" in pivot.columns:
            pivot[f"lift_{col}"] = (pivot[col] - pivot["none"]).round(4)
    out.write(_fmt(pivot))
    out.write("\n")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.width", 120)
    pd.set_option("display.max_rows", 200)

    print("Loading results...")
    df = load_results()
    print(f"Loaded {len(df)} trials from {df['model_dir'].nunique()} model folders.\n")

    # Save unified DataFrame
    df.to_csv(OUT_CSV, index=False)
    print(f"Saved unified DataFrame → {OUT_CSV}\n")

    # Build all summary tables into a buffer (print + save simultaneously)
    buf = io.StringIO()
    summary_overall(df, buf)
    summary_accuracy(df, buf)
    summary_efficiency(df, buf)
    summary_pairs(df, buf)
    summary_map_effect(df, buf)

    output = buf.getvalue()
    print(output)

    with open(OUT_TABLES, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Saved summary tables → {OUT_TABLES}")


if __name__ == "__main__":
    main()
