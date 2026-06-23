# Codebase Maps for AI Coding Agents

MSc research project investigating whether providing a structured map of a codebase (ctags or AST-based) or some other representation improves the performance of AI coding agents on software engineering tasks. Benchmarked against MuLocBench tasks on `psf/requests`.

## Folder Structure

```
final_project/
├── data/               # Raw datasets (MuLocBench pickle)
├── docs/               # Planning docs and notes
├── notebooks/          # Exploratory Jupyter notebooks
├── repo_maps/          # Generated codebase maps, organised by repo and task
│   └── requests/
│       └── task_{idx}/ # ast_map.json + ctags_map.json per benchmark task
├── repos/              # Full repository clones
│   └── requests_full/
├── results/            # Output figures and analysis JSON
├── scripts/            # Utility and map-generation scripts
├── DEVLOG.md           # Running development log
└── README.md
```

## Key Scripts

All scripts are designed to be run from the project root:

```bash
python3 scripts/generate_task_maps.py   # checkout each task's base commit,
                                         # generate AST + ctags maps, restore HEAD
python3 scripts/generate_ast_map.py     # one-off AST map for current HEAD
python3 scripts/token_estimate_ctags.py # compare token counts across map types
```

> **Note:** `run_trial.py` (the main agent harness) has not been created yet.

## Data

- `data/all_issues_with_pr_commit_comment_all_project_0922.pkl` — MuLocBench dataset. List of dicts with fields: `repo_name`, `base_commit`, `title`, `body`, `code`, plus nested PR/commit/comment data.

## Map Generation

Maps are generated per benchmark task at the task's `base_commit`:

- **AST map** (`ast_map.json`): NDJSON, one record per class/function. Fields: `type`, `file`, `name`, `line`, `docstring` (first line), `bases` or `class`.
- **ctags map** (`ctags_map.json`): NDJSON from `ctags --output-format=json`, filtered to Python classes/functions/methods, excluding `tests/` and `docs/`.
