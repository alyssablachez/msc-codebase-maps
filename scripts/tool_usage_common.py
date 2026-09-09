"""
Shared helper for the Study 2 tool-usage analyses (scripts/study2_tool_usage_by_treatment.py,
scripts/study2_tool_use_turns.py, scripts/study2_all_tools_breakdown.py). The
map-lookup tools (lookup_structure, lookup_frequency, lookup_cochange) are
recorded in each trial's raw JSON transcript as role=="tool" entries with a
"name" field, alongside general-purpose harness tools (search, read_file,
list_files, submit_answer) that are not map-specific and are excluded here.
"""
import json

MAP_TOOL_NAMES = {"lookup_structure", "lookup_frequency", "lookup_cochange"}


def extract_tool_calls(source_path):
    """Returns a list of tool names called in this trial's transcript, in
    order, restricted to the three map-lookup tools -- one entry per call
    (a tool called 3 times appears 3 times), not deduplicated."""
    with open(source_path, encoding="utf-8") as f:
        d = json.load(f)
    transcript = d.get("transcript") or []
    return [turn["name"] for turn in transcript
           if turn.get("role") == "tool" and turn.get("name") in MAP_TOOL_NAMES]
