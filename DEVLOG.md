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

## 2026-06-26 (Week 4)
- Set up API keys for Mistral, Gemini, Groq, OpenRouter, Cohere (skipped DeepSeek — confirmed known platform signup issues, not on my end)
- Confirmed Mistral free tier has no billing attached — genuinely free, no charge risk
- Resolved VPN/WSL conflict: API endpoints reachable regardless of VPN state, only provider websites affected
- Attempted Anthropic prompt caching in new run_trial_cached.py — inconclusive (wrong test condition + missing debug output), parked for later
- Verified harness is model-agnostic before testing Mistral — no Anthropic-specific assumptions found
- Ran first Mistral trials (mistral/devstral-medium-latest, Mistral's coding-agent model) across none/ast/ast_compact maps on Task 0 — harness worked end-to-end with zero code changes, F1 = 1.0 on every run
- Found large run-to-run variance for Devstral (turns 9–20, cost $0.05–$0.39, tokens 174k–1.86M)
- Root cause: read_file silently ignored offset/limit-style parameters Devstral tried for partial reads, always returning the full file — worst case repeated 16x, ballooning one trial to 1.86M tokens and hitting max_turns
- Fixed read_file in both harness scripts: documented offset/limit in tool schema, implemented real line-range slicing (6 alias names supported), added [Lines N-M of Total] header, fixed MAX_FILE_CHARS to apply to slices
- Noted: bug-affected trials still scored correctly (F1 valid) but turn/cost/token metrics are inflated artifacts — flag via stop_reason == "max_turns" and exclude from efficiency averages
- Two commits: map/caching additions, then the read_file fix 

**Next:** rerun previously-buggy Devstral trials with fix in place; revisit caching properly later

## 2026-06-29 (Week 5)
- **Real fix:** added an explicit `submit_answer(files)` tool. The model can keep stating hypotheses and investigating freely, but the *only* unambiguous way to signal "I'm done" is calling this tool — removes the guesswork from loop-exit logic entirely
- Updated `BASE_SYSTEM` to instruct the model to use `submit_answer` rather than concluding in plain text; kept the existing `FINAL_ANSWER_PROMPT` fallback for trials that end via `max_turns` or natural `stop` without a `submit_answer` call
- Added a field to saved results indicating whether the final answer came from `submit_answer` or the fallback path, to see how reliably models actually adopt the new tool
- Built `scripts/run_batch.py`: randomised batch runner across task × map × rep combinations (shuffled order to avoid time/load confounds), with per-trial subprocess calls to `run_trial.py`, running cost/time tracking, and a breakdown of `stop_reason` values across the batch
- Added `--rep` argument to `run_trial.py` so repeated trials save to distinct filenames (`task_{idx}_{map}_rep{n}.json`) instead of overwriting each other
- Ran first full grid: 5 tasks × 3 maps (none/ast/ast_compact) × 5 reps = 75 trials on `mistral/devstral-medium-latest` (free tier, no cost risk)
- Main issue encountered: intermittent timeouts during the batch, requiring monitoring to distinguish genuine hangs from slow-but-progressing trials (checked via CPU activity, results folder file timestamps, and raw response log timestamps rather than interrupting the batch)
- Result:
=================================================================
BATCH COMPLETE
  Trials    68/75 succeeded  (7 failed)
  Cost      $2.4207
  Time      4h04m37s  (avg 196s/trial)

  Stop reasons:
    submitted         48  (71%)
    max_turns         20  (29%)

  Failures:
    task=0 map=none rep=2: timeout (600s)
    task=12 map=none rep=3: timeout (600s)
    task=0 map=ast rep=1: timeout (600s)
    task=0 map=none rep=0: timeout (600s)
    task=0 map=none rep=1: timeout (600s)
    task=4 map=none rep=2: timeout (600s)
    task=4 map=ast_compact rep=3: timeout (600s)
=================================================================
- Started second full grid: 5 tasks × 3 maps (none/ast/ast_compact) × 5 reps = 75 trials on `mistral/devstral-small-latest` (free tier, no cost risk)

## 2026-06-30 (Week 5)
- Completed small-latest, 3 didn't complete and didn't have the print out from the terminal becuase computer restarted
- Filled in gap for trials that timed out
- Discovered that devstral-small-latest still defaulted to the same version of Devstral as devstral-medium-latest
- Ran same trial with DeepSeek v4-flash. Only small codebase 5 tasks, 3 map conditions (none, ast, ast_compact), 5 reps
=================================================================
BATCH COMPLETE
  Trials    75/75 succeeded  (0 failed)
  Cost      $0.2639
  Time      1h32m10s  (avg 74s/trial)

  Stop reasons:
    submitted         68  (91%)
    max_turns          7  (9%)
=================================================================
- Ran same trial with DeepSeek v4-pro. Only small codebase 5 tasks, 3 map conditions (none, ast, ast_compact), 5 reps
=================================================================
BATCH COMPLETE
  Trials    75/75 succeeded  (0 failed)
  Cost      $0.8379
  Time      1h50m50s  (avg 89s/trial)

  Stop reasons:
    submitted         68  (91%)
    max_turns          7  (9%)
=================================================================
- Completed base_commit and issue body verification for medium (scrapy) and large (yt-dlp) codebase task selections
- **Scrapy primary 5:** idx 2, 33, 45, 6, 35 — confirmed all ground truth files exist at base_commit (including task 45's test fixtures which were suspected new-but confirmed pre-existing)
- **Scrapy backup 5:** idx 8, 39, 31, 17, 20
- **yt-dlp primary 5:** idx 0, 22, 25, 16, 13 — swapped original idx 4 (YouTube DASH manifest) after finding second ground truth file `youtube_live_chat.py` was likely an incidental PR touch unrelated to the issue; replaced with idx 13 (subscriber count/channel views), body verified as substantial
- **yt-dlp backup 5:** idx 34, 21, 7, 45, 38 — all body-checked, backup 38 (SonyLIV 406) confirmed solid
- Noted task 6 (scrapy MailSender) is deliberately thin/ambiguous — kept as a "hard" task in the spirit of Task 12 (requests), not a mistake
- Decided tests should remain excluded from AST maps but are still discoverable via tools — task 45 will be a natural test of whether map-excluded files are findable through tool use alone



## 2026-07-01 (Week 5)
- Investigated different platforms hosting opensource models to look for low-cost size pairs
- Ran fireworks_ai/gpt-oss-120b: this is the first time that end-turn has been used to complete the cycle
=================================================================
BATCH COMPLETE
  Trials    75/75 succeeded  (0 failed)
  Cost      $1.3236
  Time      1h05m44s  (avg 53s/trial)

  Stop reasons:
    end_turn          64  (85%)
    submitted          7  (9%)
    max_turns          4  (5%)
=================================================================
- **Expanded codebase plan to 3 per size class** — ran LOC/Python% analysis across all 46 MULocBench repos:
  - Small: requests ✅, thefuck, flask
  - Medium: scrapy ✅, MetaGPT, fastapi  
  - Large: yt-dlp ✅, keras, scikit-learn
  - Filtered on >90% Python, >20 issues, eliminated repos with heavy non-Python components (ansible 68%, OpenHands 59%, etc.)

- **Finalized model lineup for experiments** — 6 pairs across 4 providers:
  - Pair 1: Qwen3-VL-30B-A3B vs Qwen3-VL-235B-A22B (DeepInfra, MoE vision-language)
  - Pair 2: Llama-3.1-8B vs Llama-3.1-70B (DeepInfra, dense)
  - Pair 3: Gemma-3-4B vs Gemma-3-27B (DeepInfra, dense)
  - Pair 4: gpt-oss-20B vs gpt-oss-120B (Fireworks, MoE) — 120B already partially tested
  - Pair 5: Ministral-3B vs Ministral-8B (Mistral direct, dense) — swapped out Mistral Large 3 for cleaner within-family comparison
  - Pair 6: DeepSeek-V4-Flash vs DeepSeek-V4-Pro (DeepSeek direct, MoE)

Ruled out OpenRouter and aggregators — routing layer could serve requests via different backends without visibility, undermining controlled comparison. Fireworks and DeepInfra confirmed as genuine inference providers (not proxies).

**Study design merged into two studies:**
- Study 1: 4 maps × 4-model anchor panel × 3 codebase sizes × 15 issues × 3 reps ≈ 2,160 trials
- Study 2: 4 maps × all 12 models × 2 codebase sizes × 15 issues × 3 reps ≈ 4,320 trials (anchor models shared between studies)
- Codebase size is a blocking variable in both studies, not a standalone study — the real question is the interaction (does map benefit differ by model size?)

**Issue selection rule:** 4 issues per codebase = 2 single-file + 2 multi-file (capped at 2-3 files, excluding trivial/import-only touches). Simple, mechanical, pre-registerable.

**3 codebases per size tier confirmed as minimum** — 1 codebase per tier conflates size with codebase identity; 3 makes codebase a proper random effect. 4 adds only ~15-20% precision, not worth the cost.

**3 reps per condition** — issue-to-issue variance is the dominant source of variance (captured via `(1|issue)` random effect); 3 reps is sufficient to average sampling noise without over-indexing on repetition.

**Turn cap (currently 20) — do not change until pilot data reviewed.** Literature shows localisation-only agents typically solve in 5-10 turns; 20 is probably fine but risks disproportionately truncating slower conditions (larger codebases, no-map, smaller models), which would masquerade as a real effect. Decision: raise or confirm based on pilot per-model turn distribution.

**Wall-clock time downgraded from scientific outcome to operational/descriptive metric.** Cache-hit likelihood is structurally correlated with experimental factors (codebase size, map condition) — no-map trials may cache-hit more reliably than map trials, producing a spurious "maps are slower" artifact. Turn count is the real efficiency measure.

**Stats plan:**
- Primary: logistic GLMM, `success ~ map_condition * model + codebase_size + (1|issue)`
- Interaction terms are the key test — non-significant = generalizable effect; significant = report as conditional
- Paired comparisons: McNemar (2 conditions) / Cochran's Q (3+) on matched issues
- Secondary: turn count via Poisson/negative-binomial GLMM; forced-answer rate via logistic GLMM
- Multiple comparisons: Holm-Bonferroni within each test family

- **Diagnosed `final_files_predicted: []` bug on OSS models** — gpt-oss-120b example showed model answered correctly in turn 2 message content (`{"files": ["requests/utils.py"]}`), but harness sent `FINAL_ANSWER_PROMPT` afterward which returned empty string, overwriting the valid answer. Root cause: `FINAL_ANSWER_PROMPT` always fires after the loop regardless of whether a good answer was already given in content, specifically affects `end_turn` trials on models that answer in content rather than via `submit_answer`
- Decision: do NOT modify harness mid-experiment to preserve comparability — instead apply post-hoc correction to summary CSV using transcript content, with `prediction_corrected` flag to maintain transparency. Raw JSON files remain untouched.
- gpt-oss-120b stop_reason breakdown: 85% end_turn, 9% submitted, 5% max_turns — low `submit_answer` adoption consistent with OSS models that prefer answering in prose

- **Fireworks caching concern** — Fireworks AI caches responses server-side to reduce costs; this could collapse multiple reps of identical prompts into the same cached response, undermining statistical independence of reps. Wall time is also unreliable for Fireworks trials. Cost will be calculated manually from input/output token counts × published pricing rather than relying on LiteLLM's `completion_cost()`.

**TODO (pending harness modification):**
- [ ] Fix `FINAL_ANSWER_PROMPT` overwrite bug: check if final assistant content is parseable before sending the extra prompt call — only send as fallback when content is empty/unparseable
- [ ] Add cache-busting random prefix (`uuid4().hex[:8]` prepended as `[{token}]\n`) to system prompt for Fireworks trials — conditional on `"fireworks" in model name` — save `trial_token` in result JSON for auditability
- [ ] Add `submit_answer` adoption rate as a reported metric in batch runner summary
- [ ] Post-hoc audit: for all `end_turn` trials with `final_files_predicted == []`, check transcript's final assistant content for recoverable file predictions; apply correction to summary CSVs with `prediction_corrected` flag

**TODO (data collection):**
- [ ] Clone thefuck, flask, MetaGPT, fastapi, keras, scikit-learn repos with full history
- [ ] Select 5+5 tasks for each new codebase (same process as scrapy/yt-dlp)
- [ ] Generate AST maps for all primary tasks across all 9 codebases
- [ ] Run single test trials for each new model before committing to full 75-trial batches
- [ ] Recheck DeepSeek API connectivity before scheduling batch
- [ ] Run full batches for all 12 models (6 pairs) once test trials confirm tool calling works
- [ ] Decide final turn cap value based on pilot data — likely raising rather than lowering

- Ran fireworks_ai/gpt-oss-20b: Ran extremely slowly
=================================================================
BATCH COMPLETE
  Trials    68/75 succeeded  (7 failed)
  Cost      $0.6811
  Time      5h30m13s  (avg 264s/trial)

  Stop reasons:
    submitted         46  (68%)
    max_turns         13  (19%)
    end_turn           9  (13%)

  Failures:
    task=14 map=ast rep=0: timeout (600s)
    task=14 map=ast rep=2: timeout (600s)
    task=14 map=ast rep=3: timeout (600s)
    task=14 map=ast_compact rep=2: timeout (600s)
    task=0 map=ast rep=0: timeout (600s)
    task=14 map=ast rep=4: timeout (600s)
    task=14 map=ast_compact rep=4: timeout (600s)
=================================================================

## 2026-07-02 (Week 5)
- Attempted to run with Gemma and Llama models, but they failed to call tools
- Will try to replace with zai GLM-4.7 versions and Nvidia Nemotron versions
- Ran Qwen3-VL-235B-A22B: there is a bug where it doesn't calculate costs, but it looks like the total was around $1.73. I'll need to calculate this based on tokens and try to figure out why it didn't calculate correctly
=================================================================
BATCH COMPLETE
  Trials    75/75 succeeded  (0 failed)
  Cost      $0.0000
  Time      1h47m49s  (avg 86s/trial)

  Stop reasons:
    submitted         66  (88%)
    max_turns          7  (9%)
    end_turn           2  (3%)
=================================================================
- Ran ministral-3-3b
=======================================================
Model          mistral/ministral-3b-latest
Task           0 — AttributeError: 'NoneType' object has no attribute 'read'
Map            ast
Turns          6 (submitted)
Tokens         109,234 in / 2,451 out
Cost           $0.00000
Time           20.6s

Predicted      ['requests/models.py']
Expected       ['requests/models.py']
Precision      1.0
Recall         1.0
F1             1.0
=======================================================





## Empty Predictions Audit (post-hoc)

**Scope:** 619 total trials across all models collected to date  
**Empty predictions:** 53 / 619 (8.6%)  
**Audit file:** logs/empty_predictions_audit.csv

### Category breakdown

| Category | Count | Root cause |
|---|---|---|
| A: API_ERROR | 0 | No API failures detected |
| B: CONTENT_ANSWER | 17 | Harness bug — model answered correctly in message content but FINAL_ANSWER_PROMPT returned empty because the model responded with a tool call (finish_reason=tool_calls, content=null) rather than plain JSON; harness took content="" and produced [] |
| C: GENUINE_EMPTY | 5 | Model explicitly submitted [] or reached end_turn with nothing useful |
| D: MAX_TURNS | 31 | Hit 20-turn cap without converging on an answer |

### Model-level findings

**gpt-oss-120b and gpt-oss-20b** — primarily Category B. Nine of gpt-oss-120b's 12 empty trials are recoverable from transcript content. Several would have scored F1=1.0 (confirmed: task_15_ast_rep4, task_4_ast_rep2, task_4_none_rep0 all recover to F1=1.0).

**DeepSeek, Ministral-3B, Ministral-8B** — primarily Category D. Models loop through tool calls without converging before hitting max_turns. No harness bug involved — genuine model behaviour.

-Ran Ministral-3-14b
=================================================================
BATCH COMPLETE
  Trials    74/75 succeeded  (1 failed)
  Cost      $0.0000
  Time      43m18s  (avg 35s/trial)

  Stop reasons:
    submitted         67  (91%)
    max_turns          7  (9%)

  Failures:
    task=14 map=ast rep=2: exit code 1
=================================================================

-Ran deepinfra/Qwen/Qwen3-VL-30B-A3B-Instruct. VERY HIGH FAILURE RATE
=================================================================
BATCH COMPLETE
  Trials    53/75 succeeded  (22 failed)
  Cost      $0.0000
  Time      3h58m04s  (avg 190s/trial)

  Stop reasons:
    submitted         46  (87%)
    max_turns          4  (8%)
    end_turn           3  (6%)

  Failures:
    task=12 map=ast rep=1: timeout (600s)
    task=0 map=ast rep=2: timeout (600s)
    task=14 map=ast_compact rep=2: timeout (600s)
    task=14 map=none rep=4: timeout (600s)
    task=14 map=ast rep=1: timeout (600s)
    task=0 map=none rep=2: timeout (600s)
    task=14 map=ast rep=0: timeout (600s)
    task=4 map=ast_compact rep=0: timeout (600s)
    task=12 map=none rep=3: timeout (600s)
    task=4 map=ast rep=2: timeout (600s)
    task=14 map=none rep=3: timeout (600s)
    task=4 map=ast rep=4: timeout (600s)
    task=0 map=ast rep=1: timeout (600s)
    task=0 map=ast rep=4: timeout (600s)
    task=14 map=none rep=2: timeout (600s)
    task=4 map=ast rep=1: exit code 1
    task=15 map=ast_compact rep=0: exit code 1
    task=12 map=none rep=4: exit code 1
    task=14 map=none rep=0: timeout (600s)
    task=12 map=ast rep=3: exit code 1
    task=15 map=ast rep=3: exit code 1
    task=15 map=ast rep=2: exit code 1
=================================================================

### Actions

- [ ] Fix harness: when FINAL_ANSWER_PROMPT returns finish_reason=tool_calls, fall back to parsing the last normal assistant turn content instead of taking content="" as the final answer
- [ ] Apply post-hoc correction to summary CSVs for Category B trials using recovered predictions from audit CSV — flag with prediction_corrected=True
- [ ] Category D: exclude from both accuracy and efficiency analysis, flag separately — F1=0.0 is not meaningful and efficiency metrics are inflated artifacts of hitting the cap
- [ ] Category C (5 trials): include in accuracy analysis as F1=0.0, note as genuine model failures
- [ ] Category B finding is itself a reportable result: gpt-oss models systematically treat FINAL_ANSWER_PROMPT as an invitation to continue tool use rather than a request


Models & Infrastructure 

Bugs to fix so far:
- Final answer not provided in JSON
- End vs submit: Should everything be forced to submit?
- Qwen output isn't allowing for cost at least in the printout, there is an estimated cost reported in the log, but this doesn't show up in Deepseek's log so may somehow be unique to either deepinfra or Qwen

Other problems to consider:
- Caching: does it matter on a per-trial basis? Does it matter on a between trial basis?
- Time problems: fireworks.ai may be too slow for gpt-oss-20b
- Some models don't complete within 20 turns

For now:
- Running every model through none, ast, ast compact versions to get time estimates, cost estimates, check for bugs


Experimental Design and Statistics


## 2026-07-03 (Week 5)
-Ran deepinfra_nvidia_NVIDIA-Nemotron-3-Super-120B-A12B
=================================================================
BATCH COMPLETE
  Trials    73/75 succeeded  (2 failed)
  Cost      $0.0000
  Time      3h35m47s  (avg 173s/trial)

  Stop reasons:
    submitted         66  (90%)
    end_turn           7  (10%)

  Failures:
    task=14 map=ast_compact rep=3: exit code 1
    task=12 map=none rep=2: exit code 1
=================================================================

-Ran deepinfra_nvidia_Nemotron-3-Nano-30B-A3B
=================================================================
BATCH COMPLETE
  Trials    69/75 succeeded  (6 failed)
  Cost      $0.0000
  Time      4h31m28s  (avg 217s/trial)

  Stop reasons:
    submitted         40  (58%)
    max_turns         26  (38%)
    end_turn           3  (4%)

  Failures:
    task=14 map=none rep=1: timeout (600s)
    task=14 map=ast rep=1: timeout (600s)
    task=14 map=ast rep=0: timeout (600s)
    task=14 map=ast_compact rep=3: timeout (600s)
    task=14 map=none rep=2: timeout (600s)
    task=14 map=ast rep=4: timeout (600s)
=================================================================

-Ran deepinfra_zai-org_GLM-4.7-Flash
=================================================================
BATCH COMPLETE
  Trials    71/75 succeeded  (4 failed)
  Cost      $0.0000
  Time      3h21m03s  (avg 161s/trial)

  Stop reasons:
    max_turns         50  (70%)
    submitted         21  (30%)

  Failures:
    task=14 map=ast_compact rep=4: timeout (600s)
    task=4 map=none rep=4: exit code 1
    task=14 map=none rep=2: exit code 1
    task=4 map=ast rep=1: exit code 1
=================================================================

-Ran deepinfra_zai-org_GLM-4.7
=================================================================
BATCH COMPLETE
  Trials    75/75 succeeded  (0 failed)
  Cost      $0.0000
  Time      4h03m54s  (avg 195s/trial)

  Stop reasons:
    submitted         40  (53%)
    max_turns         35  (47%)
================================================================