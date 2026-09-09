# Codebase Maps for LLM Code Localisation

MSc research project on whether giving a large language model a compact **map** of a
codebase helps it locate the file(s) that must change to resolve a GitHub issue —
across codebases of very different sizes.

Three map types are tested, each distilling one thing an experienced engineer knows:

| Map | What it captures |
|-----|------------------|
| **Structural** | every class and function, with location and signature (AST-derived, compacted) |
| **Frequency**  | how often and how recently each file has been edited |
| **Co-change**  | which files have historically been changed together |

Each is delivered either **injected into the model's context** or as an **on-demand
lookup tool** — used voluntarily, or required before an answer can be submitted.

**Headline result:** no map type, in any delivery mode, reliably improved localisation
accuracy at any codebase size. Injected maps did cut the number of reasoning turns to
an answer, at a large cost in input tokens — a speed/cost trade, not an accuracy gain.

Benchmark: issues drawn from **MULocBench** (Zhang et al., 2025) — 45 issues across
15 open-source Python repositories in three size tiers.

## Studies

| Dir | Study | Design |
|-----|-------|--------|
| `study_0/` | **Pilot** | Map design (AST vs. ctags → AST-compact; NDJSON vs. compact formatting), 12-model panel evaluation, AST vs. AST-compact comparison. `requests`, 5 issues, 900 trials. |
| `study_1/` | **Maps as context** | 4 conditions (none / structural / frequency / co-change) × 4 models × 45 issues × 3 reps = 2160 trials. |
| `study_2/` | **Voluntary tools** | Same factorial; maps exposed as lookup tools the model may call at will. |
| `study_3/` | **Required tools** | As Study 2, but `submit_answer` is gated until a lookup tool has been called. |
| `haiku_trial/` | **Study 4 (Haiku)** | Per-task behaviour follow-ups; Claude Haiku exploration of `transformers/27` with a prompt-caching harness variant (`run_trial_haiku.py`). |

Main model panel: `gpt-oss-120b`, `nemotron-super`, `ministral-3b`, `deepseek-v4-flash`.

## Layout

```
final_project/
├── data/           MULocBench pickle, issue-selection CSVs, and stats outputs
│   └── stats_study{1..4}/, stats_study2v3/, stats_haiku_trial/
├── harness/        run_trial.py (baseline + injected maps) plus 8 condition-specific
│                   variants: structural / temporal_frequency / temporal_cochange /
│                   all_tools, each with a *_required.py submit-gated version
├── repo_maps/      generated maps per {repo}/{issue_idx}: compact (AST), cochange,
│                   freq — raw, docstring-stripped, and pruned to 30k / 50k / 55k caps
├── repos/          full clones of the 15 benchmark repos at their base commits (gitignored)
├── scripts/        map generation, issue selection, statistics (R + Python), helpers
├── figures/        figures/scripts/*.py generators → rendered *.png
├── tables/         LaTeX appendix tables
├── models/         model cost sheet
├── notebooks/      exploratory analysis
├── logs/           batch-run logs (gitignored)
├── DEVLOG.md       running development log
└── README.md
```

## Pipeline

1. **Select issues** — `scripts/build_issue_pool_with_loc.py`; stratified sampling
   produces `data/issue_selection_final.csv` (45 issues, 15 repos, 3 size tiers).
2. **Generate maps** — `scripts/generate_all_maps.py` checks out each issue's
   `base_commit` and builds the structural, co-change, and frequency maps;
   `generate_pruned_maps.py` / `generate_pruned_aux_maps.py` apply the token-budget
   pruning (docstrings stripped, then least-frequently-edited files dropped until the
   map is under the cap). 55k was the smallest cap keeping ≥1 ground-truth file for
   every task, and is the version used in the trials.
3. **Run trials** — a batch runner invokes `harness/run_trial.py` (or the relevant
   variant) per `(model, issue, condition, rep)`. Each trial gives the model tool
   access to a repo checked out at `base_commit`, a turn budget (30; +2 backstop for
   the `_required` variants), and scores its `submit_answer` against the ground-truth
   files. Tools: `list_files`, `read_file`, `search`, `submit_answer`, plus
   `lookup_structure` / `lookup_frequency` / `lookup_cochange` in the tool conditions.
4. **Analyse** — `scripts/stats_*.py`: GLMMs (R, `glmmTMB` / `lme4`) plus
   distribution-free tests (Friedman / Wilcoxon, Cochran's Q / McNemar); outputs to
   `data/stats_study*/`.
5. **Figures & tables** — `figures/scripts/plot_*.py` and the `tables/*.tex` generators.

## Data

- `data/all_issues_with_pr_commit_comment_all_project_0922.pkl` — full MULocBench
  dataset (per issue: `repo_name`, `base_commit`, `title`, `body`, ground-truth files,
  nested PR/commit/comment data).
- `data/issue_selection_final.csv` — the 45 selected issues with tier, role,
  ground truth, file count, and Python LoC at the base commit.

All scripts are run from the project root.
