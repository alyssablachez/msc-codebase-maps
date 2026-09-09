"""
Shared configuration for the Study 4 battery -- the expanded-replication
program (DEVLOG 2026-08-08), treated as its own standalone study rather
than folded into Studies 1-3: these are single-issue, targeted follow-ups
on specific patterns noticed in the main case-study work, each pushed to
n=15 reps per (issue, condition, model) cell, not a factorial design
comparable to the main battery.

Tests here are UNPAIRED (Fisher's exact, Mann-Whitney U, Kruskal-Wallis),
not matched-pairs (Wilcoxon/McNemar) -- confirmed by reading the harness
scripts (run_batch.py, run_batch_tools.py, run_batch_tools_required.py):
the per-trial seed (`worker_id * 1000 + rep`) only controls
`random.shuffle(trials)` (execution order within a worker), never passed
to the LLM API call, so there is no shared randomness linking "rep 3
under baseline" to "rep 3 under structural" -- unlike the main battery,
where matching is justified by holding (model, issue) fixed, a single-
issue analysis already holds those fixed by construction and has nothing
left for rep-number pairing to control for.

Each issue's entry: `models` (list of model strings), `baseline` (raw
condition name), `conditions` (ordered list of raw non-baseline
condition names actually pushed to n=15). `map_condition_raw` values are
exactly as recorded in data/compiled_results_combined.pkl.
"""

ISSUES = {
    ("flask", 18): {
        "models": ["deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B"],
        "baseline": "none",
        "conditions": ["ast_compact", "structural", "structural_required"],
        "pattern": "Directly-traced causal case: lookup_structure returns app.py's "
                  "logger property at its exact line number, and Nemotron reads that "
                  "line next in 5/6 original trials.",
    },
    ("gpt-engineer", 9): {
        "models": [
            "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
            "deepseek/deepseek-v4-flash",
            "fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
            "mistral/ministral-3b-latest",
        ],
        "baseline": "none",
        "conditions": [
            "ast_compact", "freq", "cochange",
            "structural", "temporal_frequency", "temporal_cochange", "all_tools",
            "structural_required", "temporal_frequency_required",
            "temporal_cochange_required", "all_tools_required",
        ],
        "pattern": "Negative delta in 11/11 non-baseline conditions across all three "
                  "studies -- the single worst row in Study 1's ranking table.",
    },
    ("keras", 5): {
        "models": [
            "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
            "deepseek/deepseek-v4-flash",
            "fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
            "mistral/ministral-3b-latest",
        ],
        "baseline": "none",
        "conditions": ["freq", "temporal_frequency", "all_tools_required"],
        "pattern": "Top-ranked 'most helped' issue in every study's ranking table, but "
                  "transcript inspection found no content-mediated map use at all.",
    },
    ("localstack", 2): {
        "models": ["deepseek/deepseek-v4-flash"],
        "baseline": "none",
        "conditions": [
            "ast_compact", "cochange", "freq",
            "structural", "temporal_cochange", "temporal_frequency", "all_tools",
            "structural_required", "temporal_cochange_required",
            "temporal_frequency_required", "all_tools_required",
        ],
        "pattern": "DeepSeek's weak score breaks down sharply by delivery mechanism -- "
                  "tool_free hits max_turns 100% of the time, context delivery is "
                  "DeepSeek's best mechanism. Pattern doesn't resolve into one clean story.",
    },
    ("localstack", 19): {
        "models": [
            "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
            "deepseek/deepseek-v4-flash",
            "fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
            "mistral/ministral-3b-latest",
        ],
        "baseline": "none",
        "conditions": ["ast_compact", "temporal_frequency", "all_tools_required"],
        "pattern": "Verified comparison case: maps flip a wrong doc-file answer to the "
                  "right source file without changing exploration at all.",
    },
    ("requests", 12): {
        "models": ["deepseek/deepseek-v4-flash"],
        "baseline": "none",
        "conditions": ["ast_compact", "cochange", "freq"],
        "pattern": "DeepSeek's api.py inclusion tracks exactly which conditions deliver "
                  "its real co-change link to the found file -- strongest content-"
                  "mediated candidate found. First new rep came back worse than any "
                  "original rep; stayed open as of the DEVLOG entry.",
    },
    ("scikit-learn", 45): {
        "models": ["mistral/ministral-3b-latest"],
        "baseline": "none",
        "conditions": ["freq"],
        "pattern": "Ministral-3B alone misses an otherwise-100% answer 3/3 under "
                  "wholesale freq injection. Already confirmed at n=15 in the DEVLOG "
                  "(Fisher's exact p=0.0063) -- reproduced here as a saved script/CSV.",
    },
}

MODEL_LABELS = {
    "deepseek/deepseek-v4-flash": "deepseek-flash",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b": "gpt-oss-120b",
    "mistral/ministral-3b-latest": "ministral-3b",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B": "nemotron-super",
}
