"""
For every (trial, ground-truth file) pair across the whole dataset,
record when that file was first touched by a tool call (if ever) and
how many distinct turns touched it -- saved to a CSV, one row per
(trial, gt_file) pair.

"Touched" reuses the same definition as scripts/case_study_analysis.py's
touched_files(): a read_file call or any lookup_* call (lookup_structure/
lookup_frequency/lookup_cochange) whose path argument matches the GT
file exactly. submit_answer never counts as a touch. This applies
regardless of whether the call lands on a normal numbered turn or the
trailing forced-final-answer step (turn == "final" in the transcript)
-- if the model is still genuinely trying to read the file on its very
last turn, that counts; only submit_answer or a plain stop (no tool
call at all) don't (confirmed with user, 2026-08-06).

Ground truth is read directly from each trial's own ground_truth_scorable
field rather than recomputed via scorable_files() -- it's already the
exact list that trial was scored against, so this can't drift from what
was actually used at scoring time.

Reads the transcript's flattened role=="tool" entries directly (turn,
name, args already present as plain fields) rather than re-deriving
turn numbers from the raw assistant-side tool_calls array the way
case_study_analysis.py's touched_files() does -- that helper discards
turn info entirely, so it isn't reused here, only its semantics are.

first_touch_turn: the minimum turn among matching touches, treating the
integer turns in their natural order and "final" as coming after all of
them (it's chronologically the trial's last possible action). "na" if
the file was never touched at all.

turns_touched: count of *distinct* turns that touched the file (a turn
issuing several tool calls to the same file counts once, not once per
call). 0 if never touched -- not "na" -- so the column stays directly
summable/averageable.

Usage:
    python3 scripts/gt_file_touch_timing.py
    python3 scripts/gt_file_touch_timing.py --out data/gt_file_touch_timing.csv
"""
import argparse
import glob
import json
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDY_RESULTS_DIRS = [os.path.join(_ROOT, f"study_{i}", "results") for i in (1, 2, 3)]
DEFAULT_OUT = os.path.join(_ROOT, "data", "gt_file_touch_timing.csv")

TOUCH_TOOL_NAMES = lambda name: name == "read_file" or name.startswith("lookup_")


def find_result_files():
    for results_dir in STUDY_RESULTS_DIRS:
        pattern = os.path.join(results_dir, "*", "*", "*", "*", "rep*.json")
        yield from glob.glob(pattern)


def touch_turns_for_file(transcript, gt_file):
    """List of raw turn values (ints and/or the string "final") where
    gt_file was touched via read_file/lookup_*, in transcript order."""
    turns = []
    for entry in transcript:
        if entry.get("role") != "tool":
            continue
        name = entry.get("name") or ""
        if not TOUCH_TOOL_NAMES(name):
            continue
        path = (entry.get("args") or {}).get("path")
        if path == gt_file:
            turns.append(entry.get("turn"))
    return turns


def _sort_key(turn):
    """Order numbered turns normally; "final" always sorts after every
    integer turn, since it's chronologically the trial's last possible
    action."""
    if turn == "final":
        return (1, 0)
    return (0, turn)


def first_touch_and_count(turns):
    if not turns:
        return "na", 0
    distinct = sorted(set(turns), key=_sort_key)
    return distinct[0], len(distinct)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    rows = []
    n_trials = 0
    n_skipped = 0
    for path in find_result_files():
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except (json.JSONDecodeError, OSError):
            n_skipped += 1
            continue

        gt_files = d.get("ground_truth_scorable")
        transcript = d.get("transcript")
        if gt_files is None or transcript is None:
            n_skipped += 1
            continue

        n_trials += 1
        for gt_file in gt_files:
            turns = touch_turns_for_file(transcript, gt_file)
            first_touch_turn, turns_touched = first_touch_and_count(turns)
            rows.append({
                "model": d.get("model"),
                "repo": d.get("repo"),
                "issue_idx": d.get("issue_idx"),
                "map_type": d.get("map_type"),
                "rep": d.get("rep"),
                "gt_file": gt_file,
                "first_touch_turn": first_touch_turn,
                "turns_touched": turns_touched,
            })

    print(f"{n_trials} trials processed, {n_skipped} skipped (malformed/missing fields)")
    print(f"{len(rows)} (trial, gt_file) rows total")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    fieldnames = ["model", "repo", "issue_idx", "map_type", "rep",
                  "gt_file", "first_touch_turn", "turns_touched"]
    import csv
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    print(f"Saved -> {args.out}")


if __name__ == "__main__":
    main()
