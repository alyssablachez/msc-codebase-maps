"""
Collate all trial results into a unified DataFrame and produce summary statistics.

Outputs:
  study_0/results_all.csv              — one row per trial
  study_0/results_summary_tables.txt   — all summary tables (labelled sections)

Paths point at study_0/ -- the 2026-07-12 archival moved results/, logs/,
and this script's original outputs there, but the script itself was never
updated to match (it originally pointed at repo-root results/, from before
the multi-repo harness rewrite existed).

Cost columns (cached_tokens, cost_usd, cost_usd_uncached): Study 0's raw
per-trial JSON has no total_cached_tokens field at all (that's a Study 1+
harness addition), so cached_tokens is reconstructed here from the matching
raw_responses_*.jsonl log in study_0/logs/ -- summing each turn's
usage.prompt_tokens_details.cached_tokens, the same way total_input_tokens
in the trial JSON is itself a sum of each turn's usage.prompt_tokens
(confirmed by direct comparison: summing prompt_tokens across a trial's log
reproduces its metrics.total_input_tokens exactly). cost_usd/
cost_usd_uncached are recomputed from models/model_costs.xlsx via the same
compute_actual_cost() formula as scripts/compile_results.py (Study 1) --
cost_usd_uncached is the same trial priced as if no caching discount
applied (cached_tokens forced to 0), for measuring caching's actual saving.
Verified against the already-existing study_0/results_all.csv (built by an
earlier, undocumented one-off run of this same logic) before this script
existed in its current form: exact match on a spot-checked row.

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
STUDY0_DIR  = os.path.join(_ROOT, "study_0")
RESULTS_DIR = os.path.join(STUDY0_DIR, "results")
LOGS_DIR    = os.path.join(STUDY0_DIR, "logs")
OUT_CSV     = os.path.join(STUDY0_DIR, "results_all.csv")
OUT_TABLES  = os.path.join(STUDY0_DIR, "results_summary_tables.txt")
OUT_STATS   = os.path.join(STUDY0_DIR, "results_summary_stats.csv")
MODEL_COSTS_XLSX = os.path.join(_ROOT, "models", "model_costs.xlsx")

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

# folder -> exact row name in models/model_costs.xlsx's "Model" column
MODEL_TO_PRICE_ROW = {
    "deepinfra_Qwen_Qwen3-VL-30B-A3B-Instruct":            "Qwen3-VL-30B-A3B-Instruct",
    "deepinfra_Qwen_Qwen3-VL-235B-A22B-Instruct":          "Qwen3-VL-235B-A22B-Instruct",
    "fireworks_ai_accounts_fireworks_models_gpt-oss-20b":  "gpt-oss-20b",
    "fireworks_ai_accounts_fireworks_models_gpt-oss-120b": "gpt-oss-120b",
    "mistral_ministral-3b-latest":                         "ministral-3b",
    "mistral_ministral-14b-latest":                        "ministral-14b",
    "deepseek_deepseek-v4-flash":                          "deepseek-v4-flash",
    "deepseek_deepseek-v4-pro":                            "deepseek-v4-pro",
    "deepinfra_nvidia_Nemotron-3-Nano-30B-A3B":            "Nemotron-3-Nano-30B-A3B",
    "deepinfra_nvidia_NVIDIA-Nemotron-3-Super-120B-A12B":  "Nemotron-3-Super-120B-A12B",
    "deepinfra_zai-org_GLM-4.7-Flash":                     "GLM-4.7-Flash",
    "deepinfra_zai-org_GLM-4.7":                           "GLM-4.7",
}

FILE_PAT = re.compile(r"^task_(\d+)_(none|ast|ast_compact)_rep(\d+)\.json$")


# ── cost recomputation (models/model_costs.xlsx) ────────────────────────────────

def load_price_lookup():
    """{price_row_name: {"input": $/1M, "cached": $/1M, "output": $/1M}}.

    Falls back to the input-token rate when the sheet has no cached-price
    entry (NaN) -- assumes no caching discount rather than guessing one.
    Same logic as scripts/compile_results.py's load_price_lookup(), ported
    here rather than imported since the two scripts key by different model
    identifiers (this one by folder name, that one by litellm model string).
    """
    prices = pd.read_excel(MODEL_COSTS_XLSX)
    by_name = prices.set_index("Model")[["Input Tokens", "Cached Tokens", "Output Tokens"]].to_dict("index")
    lookup = {}
    for folder, price_row_name in MODEL_TO_PRICE_ROW.items():
        if price_row_name not in by_name:
            raise KeyError(f"'{price_row_name}' (needed for {folder}) not found in {MODEL_COSTS_XLSX}")
        row = by_name[price_row_name]
        cached_price = row["Cached Tokens"]
        lookup[folder] = {
            "input":  row["Input Tokens"],
            "cached": cached_price if pd.notna(cached_price) else row["Input Tokens"],
            "output": row["Output Tokens"],
        }
    return lookup


def compute_actual_cost(price_lookup, folder, input_tokens, cached_tokens, output_tokens):
    """USD cost recomputed from models/model_costs.xlsx, in $/1M tokens.
    total_input_tokens (the raw usage.prompt_tokens sum) includes any cached
    tokens as a subset, not in addition to them, so the uncached portion is
    the difference, not the full input count."""
    p = price_lookup[folder]
    cached = cached_tokens or 0
    uncached_input = input_tokens - cached
    cost = (uncached_input * p["input"] + cached * p["cached"] + output_tokens * p["output"]) / 1e6
    return round(cost, 6)


def sum_cached_tokens(folder, task_idx, map_type, rep):
    """Sum usage.prompt_tokens_details.cached_tokens across the turns of a
    trial's raw response log.

    The log file is append-only across retries: run_batch.py's retry logic
    (up to 2 retries, 30s backoff) re-runs a failed trial into the SAME log
    path rather than truncating it first, so a log with a crashed first
    attempt contains multiple complete "turn_0 ... final_answer" sequences
    back to back -- only the last one corresponds to the attempt that
    actually produced the saved result JSON. Detected by treating a
    recurrence of the "turn_0" label as the start of a new attempt and
    keeping only lines from the last such marker onward. Verified against
    metrics.total_input_tokens/total_output_tokens (which are only ever the
    successful attempt's own totals): summing prompt_tokens/
    completion_tokens over just the last block reproduces those exactly,
    summing the whole file does not (confirmed on a multi-attempt log where
    naively summing the whole file overcounted cached_tokens by ~3x).

    Returns 0 (with a warning) if the log is missing rather than raising,
    since a handful of early trials predate consistent logging -- matches
    load_results()'s existing warn-and-continue convention for missing/
    unreadable files."""
    log_path = os.path.join(LOGS_DIR, f"raw_responses_{folder}_{task_idx}_{map_type}_rep{rep}.jsonl")
    if not os.path.isfile(log_path):
        print(f"WARNING: no log file for cached-token reconstruction: {log_path}", file=sys.stderr)
        return 0
    try:
        with open(log_path, encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
    except Exception as e:
        print(f"WARNING: could not read {log_path}: {e}", file=sys.stderr)
        return 0

    last_attempt_start = 0
    for i, rec in enumerate(records):
        if rec.get("_label") == "turn_0":
            last_attempt_start = i
    last_attempt = records[last_attempt_start:]

    total_cached = 0
    for rec in last_attempt:
        usage = rec.get("usage") or {}
        ptd = usage.get("prompt_tokens_details") or {}
        total_cached += ptd.get("cached_tokens") or 0
    return total_cached


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


EMPTY_PREDICTIONS_AUDIT_CSV = os.path.join(STUDY0_DIR, "logs", "empty_predictions_audit.csv")


def load_category_b_corrections():
    """Category B trials (scripts/audit_empty_predictions.py): the model
    answered correctly in message content, but FINAL_ANSWER_PROMPT fired
    anyway and overwrote it with an empty final_files_predicted. Recovered
    predictions are re-scored here with plain set-based precision/recall/F1
    (matching the audit script's own "would-be F1" convention) rather than
    harness/run_trial.py's scorable_files()-filtered scoring -- that filter
    (package-scope + source-file exclusion) was introduced for the later
    multi-repo panel and it's not established that Study 0's original
    single-repo (requests) scoring used it, so matching the audit's own
    simpler convention is the more defensible choice than guessing.

    Returns {(model_dir, task_idx, map_type, rep): (precision, recall, f1, recovered_pred_list)}.
    """
    if not os.path.isfile(EMPTY_PREDICTIONS_AUDIT_CSV):
        return {}
    audit = pd.read_csv(EMPTY_PREDICTIONS_AUDIT_CSV)
    audit = audit[audit["category"] == "B"]
    corrections = {}
    for _, row in audit.iterrows():
        model_dir = row["model"].replace("/", "_")
        pred_list = json.loads(row["recovered_prediction"])
        pred = set(pred_list)
        gt   = set(json.loads(row["ground_truth"]))
        if not gt or not pred:
            continue
        tp = len(pred & gt)
        precision = tp / len(pred)
        recall    = tp / len(gt)
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        key = (model_dir, int(row["task_idx"]), row["map_type"], int(row["rep"]))
        corrections[key] = (round(precision, 4), round(recall, 4), round(f1, 4), pred_list)
    return corrections


# ── load data ─────────────────────────────────────────────────────────────────

def load_results():
    price_lookup = load_price_lookup()
    corrections = load_category_b_corrections()
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

            task_idx = d.get("task_idx")
            map_type = d.get("map_type")
            rep      = d.get("rep")
            input_tokens  = metrics.get("total_input_tokens")
            output_tokens = metrics.get("total_output_tokens")

            cached_tokens = sum_cached_tokens(folder, task_idx, map_type, rep)
            cost_usd = (compute_actual_cost(price_lookup, folder, input_tokens, cached_tokens, output_tokens)
                        if input_tokens is not None and output_tokens is not None else None)
            cost_usd_uncached = (compute_actual_cost(price_lookup, folder, input_tokens, 0, output_tokens)
                                  if input_tokens is not None and output_tokens is not None else None)

            # Category B correction (see load_category_b_corrections): only
            # ever overrides a trial that was actually empty -- never
            # touches a trial that already had a real prediction, even if
            # its key happens to collide (it won't, since the audit only
            # emits rows for trials that were empty at audit time).
            prediction_corrected = False
            precision, recall, f1 = scores.get("precision"), scores.get("recall"), scores.get("f1")
            if _is_empty(pred):
                correction_key = (folder, task_idx, map_type, rep)
                if correction_key in corrections:
                    precision, recall, f1, recovered_pred = corrections[correction_key]
                    prediction_corrected = True
                    # Also swap in the recovered list itself so
                    # empty_prediction/n_predicted_files (derived from
                    # pred below) reflect the correction consistently,
                    # rather than reporting corrected scores against a
                    # still-empty predicted-files count.
                    pred = recovered_pred

            rows.append({
                # identity
                "model_dir":   folder,
                "model_short": _short(folder),
                "model":       d.get("model", ""),
                "task_idx":    task_idx,
                "map_type":    map_type,
                "rep":         rep,
                "issue_title": d.get("issue_title", ""),
                "base_commit": d.get("base_commit", ""),
                # metrics
                "input_tokens":  input_tokens,
                "output_tokens": output_tokens,
                "cost":          metrics.get("total_cost"),
                "turns":         metrics.get("num_turns"),
                "wall_time":     metrics.get("wall_time_seconds"),
                "stop_reason":   metrics.get("stop_reason", ""),
                # cost (recomputed from models/model_costs.xlsx; see module docstring)
                "cached_tokens":      cached_tokens,
                "cost_usd":           cost_usd,
                "cost_usd_uncached":  cost_usd_uncached,
                # scores (Category B corrected in place when applicable --
                # see load_category_b_corrections and prediction_corrected)
                "precision": precision,
                "recall":    recall,
                "f1":        f1,
                "prediction_corrected": prediction_corrected,
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
    # cost_usd (recomputed from models/model_costs.xlsx) is used here, not
    # the raw harness-recorded "cost" column -- litellm silently returns
    # $0 for several of these models (no pricing entry for that model
    # string), so raw "cost" reads as exactly 0.000 for 8 of the 12 models.
    # cost_usd_uncached is shown alongside to make caching's actual saving
    # visible per model.
    out.write("Mean turns per model:\n")
    eff = (df.groupby("model_short")[["turns", "wall_time", "input_tokens", "output_tokens",
                                       "cached_tokens", "cost_usd", "cost_usd_uncached"]]
             .mean()
             .round(4)
             .reset_index())
    eff["model_short"] = pd.Categorical(eff["model_short"], categories=order, ordered=True)
    eff = eff.sort_values("model_short")
    out.write(_fmt(eff))
    out.write("\n(Note: wall_time not comparable across providers — API latency varies.\n"
              " cost_usd is recomputed from models/model_costs.xlsx -- the raw harness\n"
              " 'cost' field is unreliable, silently $0 for models litellm has no price for.)\n")

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


# ── full summary statistics (cost / time / tokens / performance) ───────────────

STATS_METRICS = {
    # (column, human label, group) -- group is just for readability in the CSV
    "cost_usd":          ("Cost (USD)", "cost"),
    "cost_usd_uncached": ("Cost, no caching discount (USD)", "cost"),
    "wall_time":         ("Wall time (s)", "time"),
    "turns":             ("Turns", "time"),
    "input_tokens":      ("Input tokens", "tokens"),
    "cached_tokens":     ("Cached tokens", "tokens"),
    "output_tokens":     ("Output tokens", "tokens"),
    "precision":         ("Precision", "performance"),
    "recall":            ("Recall", "performance"),
    "f1":                ("F1", "performance"),
}


def _describe(series):
    s = series.dropna()
    return {
        "n":      len(s),
        "min":    s.min(),
        "q1":     s.quantile(0.25),
        "median": s.median(),
        "mean":   s.mean(),
        "std":    s.std(),
        "q3":     s.quantile(0.75),
        "max":    s.max(),
    }


def compute_full_stats(df):
    """Long-format summary stats table: one row per (metric, model), plus
    one 'Overall' row per metric pooling all 900 trials. n/min/q1/median/
    mean/std/q3/max -- q1/q3 pair directly with the boxplot figures
    (figures/study0_cost_boxplot.png etc.), n is included for transparency
    even though it's a constant 75/model, 900 overall."""
    order = [_short(f) for f in FOLDERS]
    rows = []
    for col, (label, group) in STATS_METRICS.items():
        overall = _describe(df[col])
        rows.append({"metric": label, "group": group, "model_short": "Overall", **overall})
        for model_short in order:
            sub = df[df["model_short"] == model_short]
            rows.append({"metric": label, "group": group, "model_short": model_short,
                         **_describe(sub[col])})
    stats_df = pd.DataFrame(rows)
    for c in ["min", "q1", "median", "mean", "std", "q3", "max"]:
        stats_df[c] = stats_df[c].round(6)
    return stats_df


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

    # Full summary statistics -- min/q1/median/mean/std/q3/max per metric,
    # per model + overall, for direct use in report text.
    stats_df = compute_full_stats(df)
    stats_df.to_csv(OUT_STATS, index=False)
    print(f"Saved full summary statistics → {OUT_STATS}")


if __name__ == "__main__":
    main()
