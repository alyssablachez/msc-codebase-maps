"""
Run a single file-localisation trial using an LLM agent with tool access.

Usage:
    python3 harness/run_trial.py --model claude-sonnet-4-6 --task 0 --map none
    python3 harness/run_trial.py --model claude-sonnet-4-6 --task 4 --map ast --max-turns 15
"""
import argparse
import json
import os
import pickle
import re
import subprocess
import sys
import time

import litellm
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from git_utils import checkout, current_head, restore

# ── paths ─────────────────────────────────────────────────────────────────────

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKL_FILE  = os.path.join(_ROOT, "data", "all_issues_with_pr_commit_comment_all_project_0922.pkl")
REPO_DIR  = os.path.join(_ROOT, "repos", "requests_full")
MAPS_DIR  = os.path.join(_ROOT, "repo_maps", "requests")
RESULTS_DIR = os.path.join(_ROOT, "results")

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
            "description": "Read the full contents of a file within the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path to the file within the repo.",
                    }
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


def execute_tool(name, args, repo_dir):
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
                content = f.read()
            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + f"\n\n... (file truncated at {MAX_FILE_CHARS} chars)"
            return content

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

        else:
            return f"Error: unknown tool '{name}'"

    except Exception as exc:
        return f"Error executing {name}: {exc}"


# ── prompts ───────────────────────────────────────────────────────────────────

BASE_SYSTEM = """\
You are an expert software engineer helping to identify which source files in a codebase need to be modified to resolve a GitHub issue.

You have access to three tools to navigate the repository:
- list_files(path): List files and directories at a path. Use "" for the repo root.
- read_file(path): Read a file's full contents.
- search(pattern, path): Grep recursively for a pattern within path (or the whole repo if path is "").

Use these tools to investigate the issue thoroughly. Trace the logic through the codebase, read relevant source files, and verify your hypotheses before committing to an answer. Focus on source files — not tests or documentation.\
"""

MAP_SYSTEM_ADDON = """\

You have been provided with a {map_type} codebase map below. Use it to orient yourself quickly — it lists every class and function in the package with file locations. Cross-reference it with the issue to identify likely relevant files before diving into tool calls.

<codebase_map>
{map_content}
</codebase_map>\
"""

FINAL_ANSWER_PROMPT = """\
You have finished your investigation. Now provide your final answer.

Output a JSON list of file paths (relative to the repository root) that you believe need to be modified to resolve this issue. Include only source files, not tests or docs. Output valid JSON only — no explanation, no markdown fences.

Example: ["requests/models.py", "requests/auth.py"]\
"""


# ── scoring ───────────────────────────────────────────────────────────────────

def compute_scores(predicted, ground_truth):
    p, t = set(predicted), set(ground_truth)
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
    parser.add_argument("--task",      type=int, required=True,
                        help="Task index into the requests subset of MuLocBench")
    parser.add_argument("--map",       choices=["none", "ast", "ctags"], default="none")
    parser.add_argument("--max-turns", type=int, default=20)
    args = parser.parse_args()

    # ── load task ─────────────────────────────────────────────────────────────
    with open(PKL_FILE, "rb") as f:
        data = pickle.load(f)
    df = pd.DataFrame(data)
    req = df[df["repo_name"] == "requests"].reset_index(drop=True)
    row = req.iloc[args.task]

    base_commit  = row["base_commit"]
    issue_title  = row["title"]
    issue_body   = (row["body"] or "").strip()
    loctype      = row.get("loctype", {})
    ground_truth = loctype.get("code", []) if isinstance(loctype, dict) else []

    print(f"Task {args.task}: {issue_title}")
    print(f"Commit:       {base_commit[:8]}")
    print(f"Map:          {args.map}")
    print(f"Ground truth: {ground_truth}")
    print()

    # ── load map ──────────────────────────────────────────────────────────────
    map_content = None
    if args.map != "none":
        map_file = os.path.join(MAPS_DIR, f"task_{args.task}", f"{args.map}_map.json")
        if not os.path.exists(map_file):
            print(f"ERROR: map file not found: {map_file}", file=sys.stderr)
            sys.exit(1)
        with open(map_file, encoding="utf-8") as f:
            map_content = f.read().strip()

    # ── build system prompt ───────────────────────────────────────────────────
    system_prompt = BASE_SYSTEM
    if map_content:
        system_prompt += "\n" + MAP_SYSTEM_ADDON.format(
            map_type=args.map.upper(),
            map_content=map_content,
        )

    user_message = f"## Issue: {issue_title}\n\n{issue_body}"

    # ── checkout repo ─────────────────────────────────────────────────────────
    original_head = current_head(REPO_DIR)
    print(f"Checking out {base_commit[:8]} (was {original_head[:8]})")
    checkout(REPO_DIR, base_commit)

    messages = [
        {"role": "system",  "content": system_prompt},
        {"role": "user",    "content": user_message},
    ]

    total_input_tokens  = 0
    total_output_tokens = 0
    total_cost          = 0.0
    num_turns           = 0
    stop_reason         = "max_turns"
    transcript          = []
    start_time          = time.time()

    try:
        # ── tool-calling loop ─────────────────────────────────────────────────
        for turn in range(args.max_turns):
            response = litellm.completion(
                model=args.model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
            )

            total_input_tokens  += response.usage.prompt_tokens
            total_output_tokens += response.usage.completion_tokens
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

                result = execute_tool(name, tc_args, REPO_DIR)
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

        # ── elicit final answer ───────────────────────────────────────────────
        messages.append({"role": "user", "content": FINAL_ANSWER_PROMPT})
        final_resp = litellm.completion(model=args.model, messages=messages)

        total_input_tokens  += final_resp.usage.prompt_tokens
        total_output_tokens += final_resp.usage.completion_tokens
        try:
            total_cost += litellm.completion_cost(completion_response=final_resp)
        except Exception:
            pass

        final_text = (final_resp.choices[0].message.content or "").strip()
        transcript.append({"turn": "final", "role": "assistant", "content": final_text})

        # Parse JSON list from final answer (handle markdown fences gracefully)
        predicted_files = []
        try:
            match = re.search(r"\[.*?\]", final_text, re.DOTALL)
            predicted_files = json.loads(match.group() if match else final_text)
        except (json.JSONDecodeError, AttributeError):
            print(f"WARNING: could not parse final answer as JSON: {final_text!r}")

    finally:
        wall_time = time.time() - start_time
        print(f"Restoring HEAD to {original_head[:8]}")
        restore(REPO_DIR, original_head)

    # ── score ─────────────────────────────────────────────────────────────────
    scores = compute_scores(predicted_files, ground_truth)

    # ── save result ───────────────────────────────────────────────────────────
    safe_model = args.model.replace("/", "_")
    out_dir  = os.path.join(RESULTS_DIR, safe_model)
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"task_{args.task}_{args.map}.json")

    result = {
        "model":      args.model,
        "task_idx":   args.task,
        "map_type":   args.map,
        "issue_title": issue_title,
        "base_commit": base_commit,
        "metrics": {
            "total_input_tokens":  total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "total_cost":          round(total_cost, 6),
            "num_turns":           num_turns,
            "wall_time_seconds":   round(wall_time, 2),
            "stop_reason":         stop_reason,
        },
        "final_files_predicted": predicted_files,
        "ground_truth":          ground_truth,
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
    print(f"{'Task':<{w}} {args.task} — {issue_title}")
    print(f"{'Map':<{w}} {args.map}")
    print(f"{'Turns':<{w}} {num_turns} ({stop_reason})")
    print(f"{'Tokens':<{w}} {total_input_tokens:,} in / {total_output_tokens:,} out")
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


if __name__ == "__main__":
    main()
