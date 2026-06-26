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

## 2026-06-25 (Week 4)

- Considered dropping ctags outright in favour of AST alone, on the grounds that AST captures "more information." Stress-tested this reasoning before acting on it — recognised the comparison so far was confounded by yesterday's path-prefix bug, and that "more information" hadn't actually been shown to improve accuracy (Task 12 showed identical results regardless of map richness). Decided not to drop ctags casually; instead set out to properly characterise the overlap first.

- Built a direct symbol-level comparison between AST and ctags records (matching on file + name). Initial comparison showed **zero overlap** — diagnosed as the same path-prefix issue from yesterday (ctags paths still repo-prefixed, AST paths clean relative). Fixed the comparison logic to strip the prefix before matching.

- With paths normalised, found **233+ shared symbols** across all 5 task commits, differing only in which metadata each tool provides:
  - AST: docstrings, class inheritance
  - ctags: function signatures, raw source line pattern
  - Confirmed this complementary (not redundant) relationship is consistent across all 5 commits, not a one-off

- Found exactly **2 ctags-only symbols in every task** (`get_proxy`, `KD` — both lambda functions assigned to a variable rather than `def` statements). Root-caused: AST's walker only matches `ast.FunctionDef`/`AsyncFunctionDef` nodes, which lambdas-as-assignments don't trigger; ctags catches them via pattern matching instead. Decided not to fix — 2/235 symbols, lambdas are rarely fix targets — documented as a known, evidence-backed limitation instead.

- Explored whether ctags' unique strengths (signatures) and AST's unique strengths (docstrings) could be merged into one tool rather than maintained as two. Confirmed AST *can* extract signatures directly from `node.args` (more robust than ctags' regex-based approach, which sometimes truncates complex multi-line signatures) — meaning AST can fully subsume ctags' value with one addition.

- **Enhanced `generate_ast_map.py`** to extract full function/method signatures (positional args, defaults, `*args`, `**kwargs`, keyword-only args). Regenerated all 5 task maps. Signatures add ~17–18% to char count (~1,500–1,900 tokens per map) — net still favourable versus maintaining two separate map pipelines.

- **Formally retired ctags** from the active harness pipeline. Scripts and previously-generated ctags maps retained in git history for reference and methodology justification, not deleted. Two limitations now explicitly documented: (1) AST misses lambda-assigned functions, (2) AST is Python-only — confirmed not a practical constraint given current codebases are >98% Python by line count.

- Built **`scripts/compact_map.py`** — converts the enhanced AST NDJSON into a compact indented text format (file → class → method hierarchy, inline signatures, truncated docstrings, blank-line separation between files). Reviewed sample output for `requests/auth.py` and the full `requests/` package — format reads cleanly, low on token-wasting punctuation, closer to natural documentation style than raw JSON.

- Noted one formatting concern to verify: nested functions (e.g. `generate()` defined inside `Response.iter_content`) may be appearing at module level in the compact output rather than indented under their true parent — needs checking before this format goes into harness trials.

**Key learning:** before acting on an intuitive simplification ("just drop the redundant tool"), it was worth properly isolating the confound (path bug) and testing the actual claim (does richer info help accuracy) — the eventual decision to retire ctags ended up well-justified, but for different and more specific reasons than the original instinct.

**Next:** verify nested-function indentation in compact format, then measure actual token savings precisely, then run a real harness trial comparing verbose-JSON-AST vs compact-AST to see if the smaller format performs equivalently before finalising it as the structural map condition.