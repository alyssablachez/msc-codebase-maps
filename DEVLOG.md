# Development Log

## 2026-06-22 (Week 4)
- Reorganized project directory structure

## 2026-06-23 (Week 4)

- Made first git commit and pushed project to GitHub (msc-codebase-maps)
- Set up SSH authentication for git
- Discovered AST and ctags maps disagreed significantly in size at some commits (ctags up to 3x larger than AST)
- Root cause: `requests` vendored third-party dependencies (urllib3, chardet, idna) under `requests/packages/` during 2013–2016; ctags' whole-repo recursive scan picked these up, AST's shallow directory walk didn't
- Refactored monolithic map generation script into modular, independently-callable scripts: `generate_ast_map.py`, `generate_ctags_map.py`, `compare_maps.py`, `estimate_tokens.py`, plus shared `git_utils.py`
- First fix attempt: excluded `tests`, `docs`, `packages` via ctags `--exclude` flags — worked, but discovered a stray `test_requests.py` at repo root (pre-2014 layout) slipped through since it wasn't inside a `tests/` folder
- Decided on more principled fix: point both AST and ctags directly at the resolved package directory (`requests/` or `src/requests/`) rather than the whole repo + growing exclude list
- Made AST recursive to match ctags' `--recurse`, but this reintroduced the vendored-packages problem since `packages/` lives *inside* the package folder itself
- Final fix: explicit `--exclude-dirs` (default `["packages"]`) applied to both tools when recursing through the package directory, configurable for future codebases with different vendoring conventions
- Regenerated all 5 task maps; comparison still needs verification after latest fix

**Key learning:** real historical codebases have packaging quirks (vendoring) that aren't visible from current HEAD — worth checking structure at each target commit before assuming map generation logic transfers cleanly across commits.

**Next:** verify final map sizes/comparison, then build run_trial.py harness (Week 3 goal, now overdue)

## 2026-06-24 (Week 4)

- Built `harness/run_trial.py` — LiteLLM-based, model-agnostic tool-calling harness
  - Three read-only tools: `list_files`, `read_file`, `search`, with guardrails (`MAX_FILE_CHARS`, `MAX_SEARCH_LINES`) and path-escape protection (`_safe_path`)
  - Captures: tokens (in/out), cost via `litellm.completion_cost()`, wall time, turn count, predicted files
  - Scores predictions against MULocBench `loctype['code']` ground truth (precision/recall/F1)
  - Reuses `scripts/git_utils.py` for checkout/restore, with `finally` block guaranteeing repo is always restored even on failure

- First successful end-to-end trials:
  - **Task 0** (single-file, "AttributeError: NoneType has no attribute 'read'"):
    - No map (3 runs): 6-7 turns, 41.8-49.5s, $0.35-0.43, 108-133k in tokens — **F1 = 1.0** every run
    - AST map (2 runs): 4 turns, 29.2-40.9s, $0.44, ~140k in tokens — **F1 = 1.0**, consistently fewer turns than no-map but higher cost per trial
    - ctags map (1 run): **8 turns, 38.8s, $0.97, 313k in tokens** — F1 = 1.0 but far more expensive than either other condition
    - Map improved navigation efficiency (fewer turns) but increased cost — map content resent in full every turn due to stateless API
  - **Task 12** (multi-file, "max_retries" — 3 ground truth files: `sessions.py`, `adapters.py`, `api.py`):
    - No map: 4 turns, 27.1s, $0.08, 22k in tokens — **F1 = 0.5** (found `adapters.py` only)
    - AST map: 3 turns, 21.0s, $0.20, 63k in tokens — **F1 = 0.5** (same result, fewer turns)
    - ctags map: 6 turns, 28.5s, $0.43, 137k in tokens — **F1 = 0.5** (same result, more turns/cost)
    - All three conditions converged on the same incomplete answer — map type did not change *accuracy* on this task, only efficiency/cost
    - Investigated: issue body itself only references `HTTPAdapter.max_retries` — doesn't textually point to the other two files. Missing files are connected by *call chain*, not by shared symbols/structure, which neither AST nor ctags maps capture
    - Genuine finding: structural maps may have a ceiling on tasks requiring architectural/call-chain knowledge not stated in the issue text — a **temporal map** (commit co-occurrence) may be needed to catch this pattern

- **Bug found:** Task 0's ctags trial transcript shows the model's first tool call used an absolute, repo-prefixed path (`repos/requests_full/requests/models.py`) and got a near-empty result, then had to self-correct to the relative path (`requests/models.py`) on a later turn. This points to the ctags map storing repo-prefixed paths rather than clean relative paths like the AST map — actively misleading the model and likely the main driver of ctags' inflated turns/cost on this task. Needs fixing before ctags numbers can be trusted as comparable to AST.

- Confirmed conversation history is fully resent every turn (stateless API) — this is *why* map content compounds in cost across turns, not a harness bug. Identified Anthropic prompt caching as the fix (caches identical prefix across turns within a trial; doesn't leak across trials/sessions)

- Realised current per-trial cost (~$0.08–0.97, varying heavily by map type) is unsustainable at the repeat × randomised-order scale needed for statistical power (~75+ trials for 5 tasks × 3 maps × 5 repeats on one model alone)

- Decided priority order for next steps: (1) compress AST map format to reduce token cost, (2) implement prompt caching, (3) build temporal map prototype, (4) randomised repeat-trial runner — deferring retry-logic, free/local models, alternate harness frameworks, and Claude Code agent comparison until Part 1 is complete

- First git commit of harness code + initial trial results pushed to GitHub
- Saved full terminal trial log to `logs/trial_log_week4.txt` for permanent record

**Next:** improve formatting of AST map to reduce token counts, rerun on a lighter model