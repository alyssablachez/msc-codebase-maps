"""
Read-only audit of all trial result files to classify empty final_files_predicted.

Categories:
  A  API_ERROR       — final_answer API call had 0 output tokens or error finish_reason
  B  CONTENT_ANSWER  — model put .py paths in message content but FINAL_ANSWER_PROMPT
                       returned empty/tool-call (overwrite bug); recoverable answer
  C  GENUINE_EMPTY   — model genuinely gave no useful answer (incl. submit_answer([]))
  D  MAX_TURNS       — hit turn cap, no recoverable .py content in last assistant turn

Usage:
    python3 scripts/audit_empty_predictions.py
"""
import csv
import glob
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Paths point at study_0/ -- the 2026-07-12 archival moved results/ and
# logs/ there (same fix already applied to scripts/collate_results.py);
# this script was never updated to match, so it was silently auditing 16
# stale pre-archival files instead of the real 1213-file dataset.
RESULTS_DIR = os.path.join(_ROOT, "study_0", "results")
LOGS_DIR    = os.path.join(_ROOT, "study_0", "logs")
OUT_CSV     = os.path.join(_ROOT, "study_0", "logs", "empty_predictions_audit.csv")

# ── helpers ───────────────────────────────────────────────────────────────────

PY_PATH_RE = re.compile(r'\b([\w][\w/\-]*\.py)\b')


def _is_empty(pred):
    if pred is None:
        return True
    if not isinstance(pred, list):
        return False
    return len(pred) == 0 or all((p or "").strip() == "" for p in pred)


def _last_normal_assistant_content(transcript):
    """Content of the last assistant turn that is NOT the 'final' elicitation turn."""
    for turn in reversed(transcript):
        if turn.get("role") == "assistant" and turn.get("turn") != "final":
            return str(turn.get("content") or "")
    return ""


def _final_turn_content(transcript):
    for turn in reversed(transcript):
        if turn.get("turn") == "final" and turn.get("role") == "assistant":
            return str(turn.get("content") or "")
    return ""


def _recover_files(text):
    """Try to extract a list of .py file paths from a block of text."""
    # Try JSON array first
    for match in re.finditer(r'\[([^\[\]]*\.py[^\[\]]*)\]', text, re.DOTALL):
        try:
            parsed = json.loads("[" + match.group(1) + "]")
            files = [f for f in parsed if isinstance(f, str) and f.endswith(".py")]
            if files:
                return files
        except json.JSONDecodeError:
            pass

    # Try JSON object with "files" key
    for match in re.finditer(r'\{[^{}]*"files"\s*:\s*(\[[^\[\]]*\])[^{}]*\}', text, re.DOTALL):
        try:
            files_list = json.loads(match.group(1))
            files = [f for f in files_list if isinstance(f, str) and f.endswith(".py")]
            if files:
                return files
        except json.JSONDecodeError:
            pass

    # Fallback: extract bare .py paths
    paths = PY_PATH_RE.findall(text)
    seen, unique = set(), []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _check_raw_log(model_str, task_idx, map_type, rep):
    """Return (api_error: bool, final_completion_tokens: int|None, final_finish_reason: str|None)."""
    safe_model = model_str.replace("/", "_")
    log_path = os.path.join(LOGS_DIR, f"raw_responses_{safe_model}_{task_idx}_{map_type}_rep{rep}.jsonl")
    if not os.path.exists(log_path):
        return False, None, None

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("_label") != "final_answer":
                continue
            usage   = entry.get("usage") or {}
            comp_tk = usage.get("completion_tokens")
            choices = entry.get("choices") or []
            finish  = choices[0].get("finish_reason") if choices else None
            api_err = (comp_tk == 0) or (finish == "error")
            return api_err, comp_tk, finish

    return False, None, None


def classify(d):
    """Return (category, recovered_prediction_list)."""
    sr         = d.get("metrics", {}).get("stop_reason", "")
    transcript = d.get("transcript", [])
    model      = d.get("model", "")
    task_idx   = d.get("task_idx")
    map_type   = d.get("map_type")
    rep        = d.get("rep")

    last_content  = _last_normal_assistant_content(transcript)
    final_content = _final_turn_content(transcript)

    # A: API error — check raw log for 0 tokens or error finish_reason on final call
    api_err, comp_tk, finish_reason = _check_raw_log(model, task_idx, map_type, rep)
    if api_err:
        return "A", []

    # B: Model answered in content but FINAL_ANSWER_PROMPT failed to capture it.
    # Signals: stop_reason is end_turn or max_turns (so FINAL_ANSWER_PROMPT was issued),
    # and the last normal assistant turn has recoverable .py paths.
    if sr in ("end_turn", "max_turns") and not d.get("_submitted_empty"):
        recovered = _recover_files(last_content)
        if recovered:
            return "B", recovered

        # Also check: final prompt got a tool-call response (finish_reason=tool_calls)
        # which means content was null and not captured. In that case check the
        # last-normal content too (already done above). If no paths, fall through.

    # C: Genuinely empty — model explicitly submitted [] or had end_turn with no content
    if sr == "submitted":
        return "C", []
    if sr == "end_turn":
        return "C", []

    # D: Hit max turns with no recoverable answer
    if sr == "max_turns":
        return "D", []

    return "C", []


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    all_files = sorted(glob.glob(os.path.join(RESULTS_DIR, "**", "*.json"), recursive=True))
    empties = []

    for path in all_files:
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception as e:
            print(f"WARNING: could not read {path}: {e}", file=sys.stderr)
            continue

        if "final_files_predicted" not in d:
            continue

        pred = d["final_files_predicted"]
        if not _is_empty(pred):
            continue

        # Mark submitted-empty flag so classifier can distinguish from max_turns submitted
        if d.get("metrics", {}).get("stop_reason") == "submitted":
            d["_submitted_empty"] = True

        category, recovered = classify(d)

        model_dir = os.path.basename(os.path.dirname(path))
        empties.append({
            "model":               d.get("model", model_dir),
            "model_dir":           model_dir,
            "file":                os.path.basename(path),
            "task_idx":            d.get("task_idx"),
            "map_type":            d.get("map_type"),
            "rep":                 d.get("rep"),
            "stop_reason":         d.get("metrics", {}).get("stop_reason", ""),
            "turns":               d.get("metrics", {}).get("num_turns"),
            "category":            category,
            "recovered_prediction": recovered,
            "ground_truth":        d.get("ground_truth", []),
            "last_content_snippet": _last_normal_assistant_content(d.get("transcript", []))[:200],
        })

    # ── summary table ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"EMPTY PREDICTIONS AUDIT — {len(empties)} trials across {len(all_files)} total")
    print(f"{'='*70}\n")

    # Per-model counts and category breakdown
    from collections import defaultdict
    model_stats = defaultdict(lambda: {"total": 0, "A": 0, "B": 0, "C": 0, "D": 0})
    for e in empties:
        ms = model_stats[e["model"]]
        ms["total"] += 1
        ms[e["category"]] += 1

    col_w = max(len(m) for m in model_stats) + 2
    hdr = f"{'Model':<{col_w}}  {'Empty':>5}  {'A':>4}  {'B':>4}  {'C':>4}  {'D':>4}"
    print(hdr)
    print("-" * len(hdr))
    for model, ms in sorted(model_stats.items(), key=lambda x: -x[1]["total"]):
        print(f"{model:<{col_w}}  {ms['total']:>5}  "
              f"{ms['A']:>4}  {ms['B']:>4}  {ms['C']:>4}  {ms['D']:>4}")

    totals = {"A": 0, "B": 0, "C": 0, "D": 0}
    for e in empties:
        totals[e["category"]] += 1
    print("-" * len(hdr))
    print(f"{'TOTAL':<{col_w}}  {len(empties):>5}  "
          f"{totals['A']:>4}  {totals['B']:>4}  {totals['C']:>4}  {totals['D']:>4}")

    print(f"\nCategories:")
    print(f"  A  API_ERROR       — 0 output tokens or error finish_reason on final call")
    print(f"  B  CONTENT_ANSWER  — recoverable .py paths in last message content")
    print(f"  C  GENUINE_EMPTY   — no useful answer (incl. explicit submit_answer([]))")
    print(f"  D  MAX_TURNS       — hit turn cap, no recoverable content")

    # ── category B detail ─────────────────────────────────────────────────────
    b_cases = [e for e in empties if e["category"] == "B"]
    if b_cases:
        print(f"\n{'='*70}")
        print(f"CATEGORY B — RECOVERABLE CONTENT ANSWERS ({len(b_cases)} trials)")
        print(f"{'='*70}\n")
        for e in b_cases:
            gt_str  = ", ".join(e["ground_truth"])  or "(none)"
            rec_str = ", ".join(e["recovered_prediction"]) or "(none recovered)"
            gt_set  = set(e["ground_truth"])
            rec_set = set(e["recovered_prediction"])
            tp      = len(gt_set & rec_set)
            f1      = (2 * tp / (len(gt_set) + len(rec_set))) if (gt_set or rec_set) else 0.0
            print(f"  {e['model_dir']}/  {e['file']}")
            print(f"    stop={e['stop_reason']}  turns={e['turns']}")
            print(f"    Recovered : {rec_str}")
            print(f"    Ground truth: {gt_str}")
            print(f"    Would-be F1 : {f1:.3f}")
            print(f"    Last content snippet: {repr(e['last_content_snippet'][:120])}")
            print()

    # ── save CSV ──────────────────────────────────────────────────────────────
    fieldnames = [
        "model", "file", "task_idx", "map_type", "rep",
        "stop_reason", "turns", "category",
        "recovered_prediction", "ground_truth",
    ]
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in empties:
            writer.writerow({
                "model":                e["model"],
                "file":                 e["file"],
                "task_idx":             e["task_idx"],
                "map_type":             e["map_type"],
                "rep":                  e["rep"],
                "stop_reason":          e["stop_reason"],
                "turns":                e["turns"],
                "category":             e["category"],
                "recovered_prediction": json.dumps(e["recovered_prediction"]),
                "ground_truth":         json.dumps(e["ground_truth"]),
            })

    print(f"\nSaved CSV → {OUT_CSV}")


if __name__ == "__main__":
    main()
