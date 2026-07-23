"""
Run a single file-localisation trial using an LLM agent with tool access --
the "temporal_cochange_required" tool-based-retrieval condition -- same as "temporal_cochange", but submit_answer is gated: at least one of {"lookup_cochange"} must have been called first, or the submission is rejected and the trial continues (see DEVLOG for the submit-gate design rationale over forcing a turn-1 call, which has no file context to act on yet).
Copied from run_trial.py rather than branching it with a --map-style
conditional, since the tool-calling loop, tiered tool_choice fallback,
and turn/budget bookkeeping are shared unchanged; only TOOLS construction,
execute_tool dispatch, and the fixed CONDITION label actually differ.
No wholesale map is injected in this condition -- the model gets
the added lookup tool(s) below instead, called on demand.

Usage:
    python3 harness/run_trial_temporal_cochange_required.py --model claude-sonnet-4-6 \
        --repo-path repos/worker_1/requests_full --issue-idx 7
    python3 harness/run_trial_temporal_cochange_required.py --model claude-sonnet-4-6 \
        --repo-path repos/worker_2/core_full --issue-idx 20 --rep 1 --worker-id 2
"""
import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
import uuid

import litellm
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from git_utils import checkout, current_head, restore
from repo_config import REPO_DIR_MAP
from source_filter import scorable_files
from lookup_tool_schemas import LOOKUP_COCHANGE_TOOL
from lookup_tools import execute_lookup_cochange

# ── paths ─────────────────────────────────────────────────────────────────────

_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEL_CSV     = os.path.join(_ROOT, "data", "issue_selection_final.csv")
MAPS_ROOT   = os.path.join(_ROOT, "repo_maps")
RESULTS_DIR = os.path.join(_ROOT, "results")
LOGS_DIR    = os.path.join(_ROOT, "logs")

# Folder basename (leaf dir of --repo-path) -> canonical repo name used in
# issue_selection_final.csv / repo_maps/. Derived from repo_config.py's
# REPO_DIR_MAP so the two never drift apart.
FOLDER_TO_REPO = {os.path.basename(v): k for k, v in REPO_DIR_MAP.items()}

# Default branch to restore each repo worker copy to after a trial, keyed by
# folder basename (works regardless of which worker_N/ parent it's nested
# under). Verified against each repo's actual origin/HEAD.
DEFAULT_BRANCH = {
    "requests_full":               "main",
    "thefuck_full":                "master",
    "flask_full":                  "main",
    "fastapi_full":                "master",
    "gpt_engineer_full":           "main",
    "scrapy_full":                 "master",
    "rich_full":                   "main",
    "stable_diffusion_webui_full": "master",
    "keras_full":                  "master",
    "localstack_full":             "main",
    "ytdlp_full":                  "master",
    "pandas_full":                 "main",
    "scikit_learn_full":           "main",
    "transformers_full":           "main",
    "core_full":                   "dev",
}

# This file is single-condition -- no --map selection, no wholesale map
# injection. CONDITION is the label written to result["map_type"] and used
# in the results/logs directory layout, matching the existing
# {model}/{repo}/{issue_idx}/{map_type}/rep{n} convention so this
# condition's results sit alongside the wholesale-injection study's.
CONDITION = "temporal_cochange_required"

# Submission gate: submit_answer is rejected (not accepted) unless at least
# one of these has already been called in the trial. Capped at
# MAX_SUBMIT_REJECTIONS rejections so a model that never complies can't burn
# its entire turn budget on repeated rejected submissions -- after the cap,
# the submission is let through regardless, same as the ungated conditions.
REQUIRED_LOOKUP_TOOLS = {"lookup_cochange"}
MAX_SUBMIT_REJECTIONS = 2
SUBMIT_REJECTION_MESSAGE = (
    "Submission rejected: you must call lookup_cochange "
    "before calling submit_answer. Call it on a file you suspect is relevant, "
    "then submit again."
)

# ── tool schemas ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "List files and directories at a path within the checked-out repository. "
                "Returns a sorted list of names. Use path=\"\" for the repo root."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path within the repo (empty string for root).",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the contents of a file within the repository. "
                "Supports optional line-range parameters for large files: "
                "offset (1-indexed start line, default 1) and "
                "limit (number of lines to return, default all). "
                "Use these to read a file in sections rather than all at once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file within the repo.",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "1-indexed line number to start from (aliases: start).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of lines to return (aliases: length). "
                                       "Can also use end (1-indexed last line) instead.",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": (
                "Search recursively for a text pattern (grep) within the repository. "
                "Searches .py files only. Returns file:line:match lines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Pattern to search for.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Sub-path to limit the search (empty string for whole repo).",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    LOOKUP_COCHANGE_TOOL,
    {
        "type": "function",
        "function": {
            "name": "submit_answer",
            "description": (
                "Submit your final answer: the list of source files that need to be modified "
                "to resolve the issue. Call this once you are confident — the trial ends "
                "immediately and no further tool calls will be made."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File paths relative to the repository root.",
                    },
                },
                "required": ["files"],
            },
        },
    },
]

# ── tool execution ─────────────────────────────────────────────────────────────

MAX_FILE_CHARS  = 40_000
MAX_SEARCH_LINES = 200


def _safe_path(repo_dir, rel):
    """Resolve rel against repo_dir and verify it stays inside."""
    full = os.path.realpath(os.path.join(repo_dir, rel))
    if not full.startswith(os.path.realpath(repo_dir)):
        raise ValueError(f"path '{rel}' escapes the repository root")
    return full


def execute_tool(name, args, repo_dir, repo_name, issue_idx, maps_root):
    try:
        if name == "list_files":
            rel = args.get("path") or ""
            full = _safe_path(repo_dir, rel)
            if not os.path.exists(full):
                return f"Error: path '{rel}' does not exist"
            if os.path.isfile(full):
                return f"Error: '{rel}' is a file, not a directory — use read_file instead"
            entries = sorted(os.listdir(full))
            return "\n".join(entries) if entries else "(empty directory)"

        elif name == "read_file":
            rel = args.get("path") or ""
            if not rel:
                return "Error: path argument is required"
            full = _safe_path(repo_dir, rel)
            if not os.path.isfile(full):
                return f"Error: '{rel}' does not exist or is not a file"
            with open(full, encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            total_lines = len(all_lines)

            # Normalise offset/limit aliases across naming conventions models may use
            offset = args.get("offset") or args.get("start")   # 1-indexed start line
            limit  = args.get("limit")  or args.get("length")  # number of lines
            end    = args.get("end")                            # 1-indexed end line

            if offset is not None or limit is not None or end is not None:
                # Convert to 0-indexed slice bounds
                start_idx = min(max(0, int(offset) - 1), total_lines) if offset is not None else 0
                if end is not None:
                    stop_idx = int(end)           # end is 1-indexed inclusive → stop exclusive
                elif limit is not None:
                    stop_idx = start_idx + int(limit)
                else:
                    stop_idx = total_lines
                stop_idx = min(stop_idx, total_lines)
                lines = all_lines[start_idx:stop_idx]
                content = "".join(lines)
                header = f"[Lines {start_idx + 1}–{stop_idx} of {total_lines}]\n"
            else:
                content = "".join(all_lines)
                header = ""

            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + f"\n\n... (truncated at {MAX_FILE_CHARS} chars)"
            return header + content

        elif name == "search":
            pattern = args.get("pattern") or ""
            if not pattern:
                return "Error: pattern argument is required"
            rel = args.get("path") or ""
            search_root = _safe_path(repo_dir, rel)
            if not os.path.exists(search_root):
                return f"Error: path '{rel}' does not exist"
            result = subprocess.run(
                ["grep", "-r", "-n", "--include=*.py", pattern, search_root],
                capture_output=True, text=True,
            )
            output = result.stdout.strip()
            if not output:
                return "No matches found"
            repo_real = os.path.realpath(repo_dir) + "/"
            lines = [
                line[len(repo_real):] if line.startswith(repo_real) else line
                for line in output.splitlines()
            ]
            if len(lines) > MAX_SEARCH_LINES:
                lines = lines[:MAX_SEARCH_LINES]
                lines.append(f"... (truncated — showing first {MAX_SEARCH_LINES} matches)")
            return "\n".join(lines)

        elif name == "lookup_cochange":
            return execute_lookup_cochange(args, repo_name, issue_idx, maps_root)

        else:
            return f"Error: unknown tool '{name}'"

    except Exception as exc:
        return f"Error executing {name}: {exc}"


# ── map loading ───────────────────────────────────────────────────────────────

# ── prompts ───────────────────────────────────────────────────────────────────

BASE_SYSTEM = """\
You are an expert software engineer helping to identify which source files in a codebase need to be modified to resolve a GitHub issue.

You have access to five tools:
- list_files(path): List files and directories at a path. Use "" for the repo root.
- read_file(path, offset=None, limit=None): Read a file's contents. By default reads the whole file — prefer this unless the file is very large, in which case you may pass offset (starting line) and limit (number of lines) to read a smaller slice.
- search(pattern, path): Grep recursively for a pattern within path (or the whole repo if path is "").
- lookup_cochange(path, top_k=None): Look up which other files have historically been changed alongside a given file in the same commits, ranked by how often. A co-change relationship reflects historical correlation, not guaranteed relevance -- some partners may be coupled for unrelated reasons. Use it to find candidate files once you've identified a likely one, then verify with read_file or search rather than assuming a partner is relevant.
- submit_answer(files): Submit your final answer — a JSON list of file paths (relative to repo root) that need to be modified. Call this once you are confident. The trial ends immediately.

Use list_files, read_file, search, and lookup_cochange to investigate the issue. Once you are reasonably confident you have identified the correct file(s), call submit_answer — you do not need to exhaustively verify every hypothesis. Focus on source files, not tests or documentation. Before submit_answer will be accepted, you must call lookup_cochange — an attempt to submit without doing so will be rejected so you can call it and try again.\
"""

FINAL_ANSWER_PROMPT = """\
STOP exploring. Based on everything you've found so far, call submit_answer \
now with your best list of file paths — even if you're not fully certain. \
Do not call any other tool.\
"""

TURN_WARNING_PROMPT = """\
You have about {remaining} turns left before this trial ends. Start \
narrowing down to your best answer now and call submit_answer soon — an \
imperfect answer submitted in time is better than running out of turns \
with no answer at all.\
"""

TURN_WARNING_THRESHOLD = 5  # inject the warning this many turns before max_turns


def _cached_tokens(response):
    """Extract cached prompt tokens from a litellm response, if the provider
    reports them (e.g. via usage.prompt_tokens_details.cached_tokens)."""
    try:
        details = response.usage.prompt_tokens_details
        return getattr(details, "cached_tokens", None) or 0
    except AttributeError:
        return 0


# ── debug logging ─────────────────────────────────────────────────────────────

def _log_response(log_file, label, response):
    """Append one raw API response as a JSON line to log_file."""
    try:
        rec = response.model_dump() if hasattr(response, "model_dump") else {"raw": str(response)}
    except Exception:
        rec = {"raw": str(response)}
    rec["_label"] = label
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")


def _parse_submit_args(tc_args):
    """Normalise submit_answer tool-call arguments into a list of file paths.
    Handles a bare list, {"files": [...]}, or {"files": "single/path.py"}."""
    if isinstance(tc_args, list):
        return tc_args
    if isinstance(tc_args, dict):
        files = tc_args.get("files", [])
        return [files] if isinstance(files, str) else files
    return []


# ── scoring ───────────────────────────────────────────────────────────────────

def compute_scores(predicted, ground_truth, repo, issue_idx, maps_root):
    """Score against the subset of ground truth that's both a legitimate
    source file and within the resolved package directory for this issue
    (see scripts/source_filter.py) — ground_truth as stored is the full raw
    file list and may include tests/docs/config files, non-Python files, or
    real .py files outside the package scope the maps/tools operate in
    (e.g. a repo-root utils/ dir), none of which this harness could ever
    surface. predicted is filtered the same way so a model isn't penalised
    on precision for correctly not predicting such a file either."""
    p = set(scorable_files(predicted, repo, issue_idx, maps_root))
    t = set(scorable_files(ground_truth, repo, issue_idx, maps_root))
    if not t:
        return {"precision": None, "recall": None, "f1": None}
    if not p:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
    tp = len(p & t)
    precision = tp / len(p)
    recall    = tp / len(t)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": round(precision, 4),
        "recall":    round(recall,    4),
        "f1":        round(f1,        4),
    }


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Run a single file-localisation trial")
    parser.add_argument("--model",     default="claude-sonnet-4-6")
    parser.add_argument("--repo-path", required=True,
                        help="Path to the repo worker copy, "
                             "e.g. /home/afb225/study1/repos/worker_1/requests_full")
    parser.add_argument("--issue-idx", type=int, required=True,
                        help="Issue index within its repo, matching issue_selection_final.csv")
    parser.add_argument("--max-turns", type=int, default=20)
    parser.add_argument("--rep",       type=int, default=0,
                        help="Repetition index, appended to the output filename.")
    parser.add_argument("--worker-id", type=int, default=None,
                        help="Which worker (1-5) is running this trial, for traceability.")
    parser.add_argument("--maps-base", default=None,
                        help="Override the root directory maps are read from "
                             "(default: repo_maps/ relative to this repo).")
    parser.add_argument("--results-base", default=None,
                        help="Override the root directory results are written to "
                             "(default: results/ relative to this repo).")
    args = parser.parse_args()

    maps_root   = args.maps_base   if args.maps_base   else MAPS_ROOT
    results_root = args.results_base if args.results_base else RESULTS_DIR

    # ── resolve repo ──────────────────────────────────────────────────────────
    repo_dir = os.path.abspath(args.repo_path)
    folder_basename = os.path.basename(os.path.normpath(repo_dir))
    repo_name = FOLDER_TO_REPO.get(folder_basename)
    if repo_name is None:
        print(f"ERROR: unrecognized repo folder '{folder_basename}' "
              f"(from --repo-path={args.repo_path}); not in FOLDER_TO_REPO", file=sys.stderr)
        sys.exit(1)

    default_branch = DEFAULT_BRANCH.get(folder_basename)
    if default_branch is None:
        print(f"WARNING: no default branch configured for '{folder_basename}', "
              f"falling back to 'main'", file=sys.stderr)
        default_branch = "main"

    # ── load issue ────────────────────────────────────────────────────────────
    sel_df = pd.read_csv(SEL_CSV)
    match = sel_df[(sel_df["repo"] == repo_name) & (sel_df["issue_idx"] == args.issue_idx)]
    if match.empty:
        print(f"ERROR: issue not found in {SEL_CSV}: repo={repo_name} "
              f"issue_idx={args.issue_idx}", file=sys.stderr)
        sys.exit(1)
    sel_row = match.iloc[0]

    base_commit  = sel_row["base_commit"]
    issue_title  = sel_row["title"]
    issue_body   = str(sel_row["body"]).strip() if pd.notna(sel_row["body"]) else ""
    ground_truth = ast.literal_eval(sel_row["ground_truth"])

    safe_model = args.model.replace("/", "_")
    logs_dir = os.path.join(LOGS_DIR, safe_model, repo_name, str(args.issue_idx), CONDITION)
    os.makedirs(logs_dir, exist_ok=True)
    log_file = os.path.join(logs_dir, f"rep{args.rep}.jsonl")

    print(f"Repo:         {repo_name} (worker={args.worker_id}, path={repo_dir})")
    print(f"Issue idx:    {args.issue_idx} — {issue_title}")
    print(f"Commit:       {base_commit[:8]}")
    print(f"Condition:    {CONDITION}")
    print(f"Ground truth: {ground_truth}")
    print()

    # ── build system prompt ───────────────────────────────────────────────────
    # No wholesale map injection in this condition -- BASE_SYSTEM already
    # documents the added lookup tool(s); the model calls them on demand.
    system_prompt = BASE_SYSTEM

    trial_token = uuid.uuid4().hex[:8]
    user_message = f"[trial:{trial_token}]\n## Issue: {issue_title}\n\n{issue_body}"

    # ── checkout repo ─────────────────────────────────────────────────────────
    pre_trial_head = current_head(repo_dir)
    print(f"Checking out {base_commit[:8]} (worker repo was at {pre_trial_head[:8]})")
    checkout(repo_dir, base_commit)

    messages = [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": user_message},
    ]

    total_input_tokens  = 0
    total_output_tokens = 0
    total_cached_tokens = 0
    total_cost          = 0.0
    num_turns           = 0
    stop_reason         = "max_turns"
    transcript          = []
    start_time          = time.time()
    submitted           = False
    predicted_files     = []
    warned_turn_budget   = False
    lookup_calls_made   = set()   # names of REQUIRED_LOOKUP_TOOLS called so far
    submit_rejections   = 0

    try:
        # ── tool-calling loop ─────────────────────────────────────────────────
        for turn in range(args.max_turns):
            remaining = args.max_turns - turn
            if not warned_turn_budget and remaining <= TURN_WARNING_THRESHOLD:
                messages.append({
                    "role": "user",
                    "content": TURN_WARNING_PROMPT.format(remaining=remaining),
                })
                warned_turn_budget = True
                print(f"  [turn budget warning injected, {remaining} turns left]")

            response = litellm.completion(
                model=args.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            _log_response(log_file, f"turn_{turn}", response)

            total_input_tokens  += response.usage.prompt_tokens
            total_output_tokens += response.usage.completion_tokens
            total_cached_tokens += _cached_tokens(response)
            try:
                total_cost += litellm.completion_cost(completion_response=response)
            except Exception:
                pass

            num_turns += 1
            choice        = response.choices[0]
            assistant_msg = choice.message
            finish_reason = choice.finish_reason

            # Build a serialisable dict to append to messages
            msg_dict = {"role": "assistant"}
            if assistant_msg.content:
                msg_dict["content"] = assistant_msg.content

            tc_list = assistant_msg.tool_calls or []
            if tc_list:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tc_list
                ]

            messages.append(msg_dict)
            transcript.append({
                "turn":         turn,
                "role":         "assistant",
                "content":      assistant_msg.content,
                "tool_calls":   msg_dict.get("tool_calls", []),
                "finish_reason": finish_reason,
            })

            print(f"  Turn {turn + 1}: finish={finish_reason}, "
                  f"tool_calls={len(tc_list)}, "
                  f"in={response.usage.prompt_tokens} out={response.usage.completion_tokens}")

            if finish_reason == "stop" or not tc_list:
                stop_reason = "end_turn"
                break

            # Execute each tool call and append results
            for tc in tc_list:
                name = tc.function.name
                try:
                    tc_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tc_args = {}

                if name == "submit_answer":
                    gate_satisfied = (
                        bool(lookup_calls_made & REQUIRED_LOOKUP_TOOLS)
                        or submit_rejections >= MAX_SUBMIT_REJECTIONS
                    )
                    if not gate_satisfied:
                        submit_rejections += 1
                        tool_result = SUBMIT_REJECTION_MESSAGE
                        print(f"    submit_answer → REJECTED ({submit_rejections}/"
                              f"{MAX_SUBMIT_REJECTIONS}): required lookup tool not yet called")
                        messages.append({
                            "role":         "tool",
                            "tool_call_id": tc.id,
                            "content":      tool_result,
                        })
                        transcript.append({
                            "turn":         turn,
                            "role":         "tool",
                            "tool_call_id": tc.id,
                            "name":         name,
                            "args":         tc_args,
                            "result":       tool_result,
                            "rejected":     True,
                        })
                        continue

                    predicted_files = _parse_submit_args(tc_args)
                    stop_reason = "submitted"
                    tool_result = "Answer submitted."
                    print(f"    submit_answer → {predicted_files}")
                    messages.append({
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "content":      tool_result,
                    })
                    transcript.append({
                        "turn":         turn,
                        "role":         "tool",
                        "tool_call_id": tc.id,
                        "name":         name,
                        "args":         tc_args,
                        "result":       tool_result,
                    })
                    submitted = True
                    break

                if name in REQUIRED_LOOKUP_TOOLS:
                    lookup_calls_made.add(name)
                result = execute_tool(name, tc_args, repo_dir, repo_name, args.issue_idx, maps_root)
                print(f"    {name}({tc_args}) → {len(result)} chars")

                tool_msg = {
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "content":      result,
                }
                messages.append(tool_msg)
                transcript.append({
                    "turn":         turn,
                    "role":         "tool",
                    "tool_call_id": tc.id,
                    "name":         name,
                    "args":         tc_args,
                    "result":       result,
                })

            if submitted:
                break

        if not submitted:
            # ── elicit final answer ───────────────────────────────────────────
            # Force a submit_answer tool call rather than asking the model to
            # switch to freeform JSON text — after 40+ turns of tool-calling,
            # some models (observed with DeepSeek) leak raw tool-call special
            # tokens into freeform text, or ignore the "JSON only" instruction
            # and write prose instead. Forcing tool_choice keeps the model in
            # the same structured-output mode it's already reliable in.
            # Some models/providers reject a *forced* tool_choice outright
            # (DeepSeek: "Thinking mode does not support this tool_choice";
            # Deepinfra: UnsupportedParamsError) -- fall back to tools
            # available but unforced (tool_choice="auto", the same mode
            # already used successfully throughout the main loop) before
            # giving up on tools entirely. Even that isn't 100% reliable for
            # every model (observed occasional empty/prose/garbled answers
            # regardless) -- accepted as a documented residual limitation,
            # see DEVLOG.md 2026-07-13.
            messages.append({"role": "user", "content": FINAL_ANSWER_PROMPT})
            try:
                final_resp = litellm.completion(
                    model=args.model,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice={"type": "function", "function": {"name": "submit_answer"}},
                )
            except Exception as exc:
                print(f"WARNING: forced submit_answer call failed ({exc}), "
                      f"retrying with tools available but tool_choice unforced")
                try:
                    final_resp = litellm.completion(
                        model=args.model,
                        messages=messages,
                        tools=TOOLS,
                        tool_choice="auto",
                    )
                except Exception as exc2:
                    print(f"WARNING: unforced tool_choice call also failed ({exc2}), "
                          f"retrying without any tools schema")
                    final_resp = litellm.completion(model=args.model, messages=messages)
            _log_response(log_file, "final_answer", final_resp)

            total_input_tokens  += final_resp.usage.prompt_tokens
            total_output_tokens += final_resp.usage.completion_tokens
            total_cached_tokens += _cached_tokens(final_resp)
            try:
                total_cost += litellm.completion_cost(completion_response=final_resp)
            except Exception:
                pass

            final_msg = final_resp.choices[0].message
            final_tc_list = final_msg.tool_calls or []
            submit_tc = next(
                (tc for tc in final_tc_list if tc.function.name == "submit_answer"), None)

            if submit_tc is not None:
                try:
                    tc_args = json.loads(submit_tc.function.arguments)
                except json.JSONDecodeError:
                    tc_args = {}
                predicted_files = _parse_submit_args(tc_args)
                transcript.append({
                    "turn": "final", "role": "assistant",
                    "content": None, "tool_calls": [{
                        "name": "submit_answer", "arguments": submit_tc.function.arguments,
                    }],
                })
            else:
                # Fallback: provider didn't honor forced tool_choice, or
                # returned freeform text instead — try the old text-parsing
                # path so a well-behaved plain-text answer still counts.
                final_content = final_msg.content or ""
                if not final_content and final_resp.choices[0].finish_reason == "tool_calls":
                    final_content = next(
                        (t.get("content", "") for t in reversed(transcript)
                         if t.get("role") == "assistant"
                         and t.get("turn") != "final"
                         and t.get("content")
                         and t.get("content") != "None"),
                        ""
                    )
                final_text = final_content.strip()
                transcript.append({"turn": "final", "role": "assistant", "content": final_text})
                try:
                    match = re.search(r"\[.*?\]", final_text, re.DOTALL)
                    predicted_files = json.loads(match.group() if match else final_text)
                except (json.JSONDecodeError, AttributeError):
                    print(f"WARNING: could not parse final answer as JSON: {final_text!r}")

    finally:
        wall_time = time.time() - start_time
        print(f"Restoring {folder_basename} to default branch '{default_branch}'")
        restore(repo_dir, default_branch)

    # ── score ─────────────────────────────────────────────────────────────────
    scores = compute_scores(predicted_files, ground_truth, repo_name, args.issue_idx, maps_root)

    # ── save result ───────────────────────────────────────────────────────────
    out_dir = os.path.join(results_root, safe_model, repo_name, str(args.issue_idx), CONDITION)
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"rep{args.rep}.json")

    result = {
        "model":      args.model,
        "repo":       repo_name,
        "issue_idx":  args.issue_idx,
        "tier":       sel_row["tier"],
        "role":       sel_row["role"],
        "map_type":   CONDITION,
        "rep":        args.rep,
        "worker_id":  args.worker_id,
        "issue_title": issue_title,
        "base_commit": base_commit,
        "metrics": {
            "total_input_tokens":  total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cached_tokens": total_cached_tokens,
            "total_cost":          round(total_cost, 6),
            "num_turns":           num_turns,
            "wall_time_seconds":   round(wall_time, 2),
            "stop_reason":         stop_reason,
            "hit_turn_cap":        stop_reason == "max_turns",
            "submission_type":     (
                "submit_answer" if stop_reason == "submitted" else
                "end_turn"      if stop_reason == "end_turn"  else
                "max_turns"     if stop_reason == "max_turns" else
                "unknown"
            ),
            "trial_token":         trial_token,
        },
        "final_files_predicted": predicted_files,
        "final_files_predicted_scorable": scorable_files(predicted_files, repo_name, args.issue_idx, maps_root),
        "ground_truth":          ground_truth,
        "ground_truth_scorable": scorable_files(ground_truth, repo_name, args.issue_idx, maps_root),
        "scores":                scores,
        "transcript":            transcript,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # ── print summary ─────────────────────────────────────────────────────────
    w = 14
    print()
    print("=" * 55)
    print(f"{'Model':<{w}} {args.model}")
    print(f"{'Repo':<{w}} {repo_name}")
    print(f"{'Issue':<{w}} {args.issue_idx} — {issue_title}")
    print(f"{'Condition':<{w}} {CONDITION}")
    print(f"{'Turns':<{w}} {num_turns} ({stop_reason})")
    print(f"{'Tokens':<{w}} {total_input_tokens:,} in / {total_output_tokens:,} out "
          f"({total_cached_tokens:,} cached)")
    print(f"{'Cost':<{w}} ${total_cost:.5f}")
    print(f"{'Time':<{w}} {wall_time:.1f}s")
    print()
    print(f"{'Predicted':<{w}} {predicted_files}")
    print(f"{'Expected':<{w}} {ground_truth}")
    print(f"{'Precision':<{w}} {scores['precision']}")
    print(f"{'Recall':<{w}} {scores['recall']}")
    print(f"{'F1':<{w}} {scores['f1']}")
    print("=" * 55)
    print(f"Saved → {out_file}")
    print(f"Log   → {log_file}")


if __name__ == "__main__":
    main()
