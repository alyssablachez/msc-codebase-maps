"""
Canonical per-repo configuration for the 15 study repos: folder name and
package name, keyed by the repo name as it appears in
data/issue_selection_final.csv.

Single source of truth, imported by both map-generation scripts
(generate_all_maps.py, regenerate_ast_maps.py, recover_map_stats.py) and
trial-running scripts (harness/run_trial.py, scripts/run_batch.py) so the
repo-name -> folder-name mapping can't drift out of sync between them --
which is exactly what happened before this was centralized: run_batch.py
used to hand-roll f"{repo}_full", silently breaking for gpt-engineer
(-> gpt_engineer_full), stable-diffusion-webui (-> stable_diffusion_webui_full),
yt-dlp (-> ytdlp_full), and scikit-learn (-> scikit_learn_full).

No side effects at import time -- pure data only. Deliberately has zero
dependencies (no pandas/yaml/etc.) so trial-running environments don't need
to install anything just to resolve a repo name.
"""

REPO_DIR_MAP = {
    "requests":               "repos/requests_full",
    "thefuck":                "repos/thefuck_full",
    "flask":                  "repos/flask_full",
    "gpt-engineer":           "repos/gpt_engineer_full",
    "fastapi":                "repos/fastapi_full",
    "scrapy":                 "repos/scrapy_full",
    "rich":                   "repos/rich_full",
    "stable-diffusion-webui": "repos/stable_diffusion_webui_full",
    "keras":                  "repos/keras_full",
    "localstack":             "repos/localstack_full",
    "yt-dlp":                 "repos/ytdlp_full",
    "pandas":                 "repos/pandas_full",
    "scikit-learn":           "repos/scikit_learn_full",
    "transformers":           "repos/transformers_full",
    "core":                   "repos/core_full",
}

PACKAGE_MAP = {
    "requests":               "requests",
    "thefuck":                "thefuck",
    "flask":                  "flask",
    "gpt-engineer":           "gpt_engineer",
    "fastapi":                "fastapi",
    "scrapy":                 "scrapy",
    "rich":                   "rich",
    "stable-diffusion-webui": "modules",
    "keras":                  "keras",
    "localstack":             "localstack",
    "yt-dlp":                 "yt_dlp",
    "pandas":                 "pandas",
    "scikit-learn":           "sklearn",
    "transformers":           "transformers",
    "core":                   "homeassistant",
}
