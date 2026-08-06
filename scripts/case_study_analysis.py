"""
Standard per-issue analysis for the manual case-study workflow
(data/model_failure_points.md, data/issue_case_study_notes.csv).

Consolidates the ad-hoc inline scripts that had been independently
rewritten (with small, unaudited variations) for every issue analyzed
since pandas/35 -- same MODELS/GROUPS/MECH conventions, same right/wrong
file counting, same search-term extraction, same touch-vs-kept and
mechanism-breakdown logic. Saved down 2026-08-04 per explicit request,
to cut repeat work and keep the methodology itself reviewable/versioned
instead of re-derived (and potentially silently drifting) each time.

Ground truth is read from data/issue_selection_final.csv and reduced to
the scorable subset via scripts/source_filter.py's scorable_files() --
the same filter run_trial.py itself uses at scoring time -- so this
script's notion of "ground truth" always matches what the harness
actually scored against, not the raw (sometimes non-scorable) column.

Reads trial results from study_1/results, study_2/results,
study_3/results for the given (repo, issue_idx) -- 144 trials when
complete (12 conditions x 4 models x 3 reps).

Usage:
    python3 scripts/case_study_analysis.py --repo scrapy --issue-idx 48
    python3 scripts/case_study_analysis.py --repo pandas --issue-idx 44 --top-terms 8
    python3 scripts/case_study_analysis.py --repo thefuck --issue-idx 10 --sections files,search
    python3 scripts/case_study_analysis.py --repo gpt-engineer --issue-idx 12 --touch-file gpt_engineer/core/files_dict.py
"""
import argparse
import ast
import json
import os
import re
import sys
from collections import Counter, defaultdict

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from source_filter import scorable_files  # noqa: E402

SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")
MAPS_ROOT = os.path.join(_ROOT, "repo_maps")
STUDY_RESULTS_DIRS = [
    os.path.join(_ROOT, f"study_{i}", "results") for i in (1, 2, 3)
]

# Folder-safe model name -> short display name, by substring match.
# Matches the convention used across every case-study session in
# data/model_failure_points.md.
MODEL_SHORT_PATTERNS = [
    ("ministral", "Ministral-3B"),
    ("gpt-oss", "gpt-oss-120B"),
    ("deepseek", "DeepSeek-V4-Flash"),
    ("Nemotron", "Nemotron-3-Super"),
]
MODEL_ORDER = ["Ministral-3B", "gpt-oss-120B", "DeepSeek-V4-Flash", "Nemotron-3-Super"]

# Study 1's 4 wholesale-map conditions + Study 2/3's 8 tool-based
# conditions, grouped by underlying map type (pooling context/tool_free/
# tool_required together) -- the "Structural/Frequency/Co-change/All
# tools" grid used in every case study's wrong/right-file and
# search-term tables.
MAP_TYPE_GROUPS = {
    "Structural": {"ast_compact", "structural", "structural_required"},
    "Frequency": {"freq", "temporal_frequency", "temporal_frequency_required"},
    "Co-change": {"cochange", "temporal_cochange", "temporal_cochange_required"},
    "All tools": {"all_tools", "all_tools_required"},
}
MAP_TYPE_GROUP_ORDER = ["Structural", "Frequency", "Co-change", "All tools"]

# Delivery-mechanism grouping (context vs. voluntary tool vs. gated
# tool) -- the axis failure points #18/#23/#24 etc. check separately
# from map type.
MECHANISM_GROUPS = {
    "context": {"ast_compact", "freq", "cochange"},
    "tool_free": {"structural", "temporal_frequency", "temporal_cochange", "all_tools"},
    "tool_required": {
        "structural_required",
        "temporal_frequency_required",
        "temporal_cochange_required",
        "all_tools_required",
    },
}
MECHANISM_ORDER = ["baseline", "context", "tool_free", "tool_required"]

STOPWORDS = {"def", "self", "import", "from", "class", "return", "the", "and", "for", "with", "none"}
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def short_model(folder_or_model_name):
    for pat, short in MODEL_SHORT_PATTERNS:
        if pat.lower() in folder_or_model_name.lower():
            return short
    return folder_or_model_name


def map_type_group(map_type):
    for group, members in MAP_TYPE_GROUPS.items():
        if map_type in members:
            return group
    return "baseline" if map_type == "none" else None


def mechanism_group(map_type):
    for group, members in MECHANISM_GROUPS.items():
        if map_type in members:
            return group
    return "baseline" if map_type == "none" else None


def load_ground_truth(repo, issue_idx):
    """(raw_ground_truth_list, scorable_ground_truth_list) for this issue,
    read directly from issue_selection_final.csv and reduced via the same
    scorable_files() filter run_trial.py itself scores against."""
    sel = pd.read_csv(SEL_CSV)
    row = sel[(sel["repo"] == repo) & (sel["issue_idx"] == issue_idx)]
    if row.empty:
        raise SystemExit(f"No row for repo={repo!r} issue_idx={issue_idx!r} in {SEL_CSV}")
    raw_gt = ast.literal_eval(row.iloc[0]["ground_truth"])
    scorable_gt = scorable_files(raw_gt, repo, issue_idx, MAPS_ROOT)
    return raw_gt, scorable_gt


def load_trials(repo, issue_idx):
    """List of (filepath, parsed_dict) for every trial result found across
    all three studies for this (repo, issue_idx). Silently skips files
    that fail to parse (should not happen for complete, valid results)."""
    trials = []
    for results_dir in STUDY_RESULTS_DIRS:
        pattern = os.path.join(results_dir, "*", repo, str(issue_idx), "*", "rep*.json")
        import glob

        for path in sorted(glob.glob(pattern)):
            try:
                with open(path, encoding="utf-8") as f:
                    trials.append((path, json.load(f)))
            except (json.JSONDecodeError, OSError):
                continue
    return trials


def _extract_tool_calls(transcript):
    """Yield (tool_name, args_dict) for every assistant tool call in a
    transcript, tolerant of both dict-args and JSON-string-args forms."""
    for turn in transcript:
        if turn.get("role") != "assistant":
            continue
        for tc in turn.get("tool_calls") or []:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            raw_args = fn.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    args = {}
            else:
                args = raw_args or {}
            yield name, args


def touched_files(transcript):
    """Set of file paths this trial ever read or looked up (read_file
    calls, plus lookup_structure/lookup_frequency/lookup_cochange calls
    -- the tool-based equivalent of reading a file)."""
    touched = set()
    for name, args in _extract_tool_calls(transcript):
        if name == "read_file" or name.startswith("lookup_"):
            path = args.get("path")
            if path:
                touched.add(path)
    return touched


def num_assistant_turns(transcript):
    return sum(1 for t in transcript if t.get("role") == "assistant")


# ── report sections ──────────────────────────────────────────────────────


def section_files(trials, scorable_gt, models):
    print("=" * 72)
    print("WRONG/RIGHT FILE BREAKDOWN")
    print("=" * 72)
    right, wrong = Counter(), Counter()
    per_model_f1 = defaultdict(list)
    for _, d in trials:
        pred = set(d.get("final_files_predicted_scorable") or [])
        model = short_model(d["model"])
        f1 = (d.get("scores") or {}).get("f1")
        if f1 is not None:
            per_model_f1[model].append(f1)
        for p in pred:
            (right if p in scorable_gt else wrong)[p] += 1

    print(f"\nTotal trials: {len(trials)}")
    print("\n--- Right file hit counts ---")
    for f, c in right.most_common():
        print(f"{c:3d}/{len(trials)}  {f}")
    missing = set(scorable_gt) - set(right.keys())
    if missing:
        print("Not found even once:", missing)

    print("\n--- Wrong files (top 20) ---")
    for f, c in wrong.most_common(20):
        print(f"{c:3d}  {f}")
    if not wrong:
        print("(none -- every prediction across all trials fell within ground truth)")

    print("\n--- Mean F1 per model ---")
    for m in models:
        vals = per_model_f1.get(m, [])
        if vals:
            print(f"{m}: {sum(vals)/len(vals):.4f}  (n={len(vals)})")


def section_grid(trials, scorable_gt, models, target_files=None):
    print("\n" + "=" * 72)
    print("RIGHT-FILE HIT RATE BY MODEL x MAP-TYPE GROUP")
    print("=" * 72)
    targets = target_files or sorted(scorable_gt)
    right_by_mg = defaultdict(Counter)
    total_by_mg = defaultdict(int)
    for _, d in trials:
        model = short_model(d["model"])
        grp = map_type_group(d["map_type"])
        pred = set(d.get("final_files_predicted_scorable") or [])
        if grp:
            total_by_mg[(model, grp)] += 1
            for p in pred & set(targets):
                right_by_mg[(model, grp)][p] += 1

    for target in targets:
        print(f"\n--- {target} ---")
        for m in models:
            row = []
            for g in MAP_TYPE_GROUP_ORDER:
                r = right_by_mg[(m, g)].get(target, 0)
                t = total_by_mg[(m, g)]
                row.append(f"{r}/{t}")
            print(f"  {m:20s} {row}")


def section_search(trials, models, top_n=6):
    print("\n" + "=" * 72)
    print("SEARCH TERMS BY MODEL x MAP-TYPE GROUP")
    print("=" * 72)
    search_terms = defaultdict(Counter)
    search_count = defaultdict(int)
    for _, d in trials:
        model = short_model(d["model"])
        grp = map_type_group(d["map_type"])
        if not grp:
            continue
        for name, args in _extract_tool_calls(d.get("transcript") or []):
            if "search" not in name.lower():
                continue
            q = args.get("query") or args.get("pattern")
            if not q:
                continue
            search_count[(model, grp)] += 1
            for tok in TOKEN_RE.findall(q.lower()):
                if tok not in STOPWORDS:
                    search_terms[(model, grp)][tok] += 1

    print("\n--- search call counts ---")
    for m in models:
        print(m, {g: search_count[(m, g)] for g in MAP_TYPE_GROUP_ORDER})

    print("\n--- top search terms ---")
    for m in models:
        print(m)
        for g in MAP_TYPE_GROUP_ORDER:
            print(f"  {g}: {search_terms[(m, g)].most_common(top_n)}")


def section_touch(trials, models, touch_files_arg):
    print("\n" + "=" * 72)
    print(f"TOUCH-VS-KEPT: {touch_files_arg}")
    print("=" * 72)
    target_set = set(touch_files_arg)
    touch = defaultdict(lambda: [0, 0])
    kept = defaultdict(lambda: [0, 0])
    for _, d in trials:
        model = short_model(d["model"])
        mech = mechanism_group(d["map_type"])
        if not mech:
            continue
        pred = set(d.get("final_files_predicted_scorable") or [])
        touched = touched_files(d.get("transcript") or [])
        hit_touch = bool(touched & target_set)
        hit_kept = bool(pred & target_set)
        touch[(model, mech)][1] += 1
        touch[(model, mech)][0] += hit_touch
        kept[(model, mech)][1] += 1
        kept[(model, mech)][0] += hit_kept

    for m in models:
        for g in MECHANISM_ORDER:
            t, n = touch[(m, g)]
            k, _ = kept[(m, g)]
            if n:
                print(f"{m:20s} {g:15s} touched={t}/{n}  kept={k}/{n}")


def section_turns(trials, models):
    print("\n" + "=" * 72)
    print("ASSISTANT TURN COUNTS PER MODEL")
    print("=" * 72)
    turns = defaultdict(list)
    for _, d in trials:
        model = short_model(d["model"])
        turns[model].append(num_assistant_turns(d.get("transcript") or []))
    for m in models:
        v = turns.get(m)
        if v:
            print(f"{m:20s} mean={sum(v)/len(v):5.1f}  min={min(v):3d}  max={max(v):3d}  n={len(v)}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--repo", required=True)
    ap.add_argument("--issue-idx", required=True, type=int)
    ap.add_argument(
        "--sections",
        default="files,grid,search,turns",
        help="Comma-separated subset of: files,grid,search,touch,turns "
        "(default: files,grid,search,turns -- add 'touch' explicitly "
        "with --touch-file, since it needs a target)",
    )
    ap.add_argument(
        "--touch-file",
        action="append",
        default=[],
        help="File(s) to run the touch-vs-kept breakdown for (repeatable). "
        "Required for the 'touch' section.",
    )
    ap.add_argument(
        "--grid-file",
        action="append",
        default=[],
        help="Restrict the model x map-type grid to specific file(s) "
        "(repeatable). Default: every scorable ground-truth file.",
    )
    ap.add_argument("--top-terms", type=int, default=6, help="Top-N search terms shown per cell")
    args = ap.parse_args()

    sections = [s.strip() for s in args.sections.split(",") if s.strip()]

    raw_gt, scorable_gt = load_ground_truth(args.repo, args.issue_idx)
    trials = load_trials(args.repo, args.issue_idx)
    if not trials:
        raise SystemExit(f"No trial results found for {args.repo}/{args.issue_idx}")

    print(f"repo={args.repo}  issue_idx={args.issue_idx}")
    print(f"raw ground_truth ({len(raw_gt)}): {raw_gt}")
    print(f"scorable ground_truth ({len(scorable_gt)}): {scorable_gt}")
    print(f"trials loaded: {len(trials)}")

    if "files" in sections:
        section_files(trials, scorable_gt, MODEL_ORDER)
    if "grid" in sections:
        section_grid(trials, scorable_gt, MODEL_ORDER, target_files=args.grid_file or None)
    if "search" in sections:
        section_search(trials, MODEL_ORDER, top_n=args.top_terms)
    if "touch" in sections:
        if not args.touch_file:
            raise SystemExit("--sections touch requires at least one --touch-file")
        section_touch(trials, MODEL_ORDER, args.touch_file)
    if "turns" in sections:
        section_turns(trials, MODEL_ORDER)


if __name__ == "__main__":
    main()
