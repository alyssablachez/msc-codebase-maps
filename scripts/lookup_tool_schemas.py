"""
The three lookup_* tool schemas for on-demand map retrieval, in the same
style as harness/run_trial.py's existing TOOLS list. Wired in per
condition by harness/run_trial_structural.py / run_trial_temporal_frequency.py
/ run_trial_temporal_cochange.py / run_trial_all_tools.py (structural ->
LOOKUP_STRUCTURE_TOOL only, temporal_frequency -> LOOKUP_FREQUENCY_TOOL
only, temporal_cochange -> LOOKUP_COCHANGE_TOOL only, all_tools -> all
three), alongside the existing list_files/read_file/search/submit_answer
tools, which every condition keeps. Execution logic lives in
lookup_tools.py, not here -- this module is schemas only.

See DEVLOG 2026-07-16 for the design rationale behind each cap/pagination
choice.
"""

LOOKUP_STRUCTURE_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_structure",
        "description": (
            "Look up the structural signature of a specific Python file: every "
            "top-level class and function, with its line number, full signature, and "
            "full docstring. Use this to understand what a file contains before deciding "
            "whether to read it in full with read_file. "
            "Large files are returned in pages -- if the response says more members are "
            "available, call this again with a higher offset to continue reading from "
            "where you left off."
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
                    "description": (
                        "1-indexed member number (each class or function, in file order, "
                        "counts as one member) to start from. Default 1. Use the offset "
                        "suggested in a previous response to continue reading the same "
                        "file where the last page left off."
                    ),
                },
            },
            "required": ["path"],
        },
    },
}

LOOKUP_FREQUENCY_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_frequency",
        "description": (
            "Look up how often a specific file has historically been edited: total edit "
            "count and the date of its most recent edit. A high edit count means the file "
            "is actively maintained or central to the codebase -- it is a weak signal "
            "about general importance, not proof that this specific file is relevant to "
            "the current issue."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file within the repo.",
                },
            },
            "required": ["path"],
        },
    },
}

LOOKUP_COCHANGE_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_cochange",
        "description": (
            "Look up which other files have historically been changed in the same commits "
            "as a specific file (\"co-change\"), ranked by how often they changed "
            "together. Useful for finding files that tend to need updating alongside a "
            "file you already suspect is relevant -- e.g. if a fix to one file typically "
            "requires updating several sibling files, they are likely to show up here. "
            "A high co-change count is a weak signal about coupling, not proof that a "
            "partner file is relevant to the current issue -- some files are broadly "
            "coupled to many others for reasons unrelated to any specific change."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path to the file within the repo.",
                },
                "top_k": {
                    "type": "integer",
                    "description": (
                        "Maximum number of co-change partners to return, ranked highest "
                        "co-change count first. Default 10. Increase this if the top "
                        "results don't look sufficient -- there is no upper limit other "
                        "than the file's actual number of co-change partners."
                    ),
                },
            },
            "required": ["path"],
        },
    },
}

LOOKUP_TOOLS = [LOOKUP_STRUCTURE_TOOL, LOOKUP_FREQUENCY_TOOL, LOOKUP_COCHANGE_TOOL]
