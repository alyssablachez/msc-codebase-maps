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

## 2026-07-04
-Ran together_ai/openai/gpt-oss-120b
=================================================================
BATCH COMPLETE
  Trials    75/75 succeeded  (0 failed)
  Cost      $0.4447
  Time      36m40s  (avg 29s/trial)

  Stop reasons:
    end_turn          69  (92%)
    submitted          6  (8%)
=================================================================


## 2026-07-07
- Attempted final fixes to get gpt-oss models hosted by together AI to use tools with my harness, but no success
- Re-ran all missing trials from the 12 paired models by hand

## 2026-07-08
- Started visual exploration of the data collected from 12 models and 3 map conditions (none, ast, ast compact) on requests codebase & 5 issues
-- results_all.csv
-- notebooks/results_barplots
- Created a models/model_costs file to record pricing for the various models
- Altered the harness with the following bug fixes: 
-- Fix submit_answer bare list crash: handle models that pass [\"file.py\"]
  instead of {\"files\": [\"file.py\"]} (affected Qwen VL-30B)
-- Fix FINAL_ANSWER_PROMPT overwrite bug: fall back to last assistant turn
  content when final response has finish_reason=tool_calls (Category B fix,
  affected gpt-oss models)
-- Strengthen FINAL_ANSWER_PROMPT wording to prevent models treating it as
  an invitation to continue tool use
-- Add cache-busting random token prefix to system prompt for all providers
-- Add hit_turn_cap and submission_type fields to result JSON metrics
-- Add retry logic to run_batch.py: up to 2 retries with 30s backoff,
  900s timeout per trial
-- Remove run_trial_together.py and run_trial_cached.py (superseded)
- Reviewed plan to have 3 codebases for each level, and decided instead to go for 5 codebases with 3 issues for each size level
- Settled on panel of codebases, excluding several based on %python, large degree of ML-specific issues, non-English issues, low number of issues
- Selecting the 3 issues for each codebase, biasing towards issues with a decent length body

## 2026-07-09 
## Issue Selection Methodology

### Overview
Issues were selected from the MULocBench dataset for each of the 15 codebases in the study. The selection process went through two phases: an initial hand-curated phase (discarded) and a final randomised stratified sampling phase.

### Why Randomised Selection?
An initial hand-curated selection was explored but discarded on methodological grounds. Hand-curation introduced subjective selection bias — issues were being chosen based on body length preferences, difficulty intuitions, and file spread aesthetics. A reviewer could reasonably ask whether issues were cherry-picked to favour conditions where maps were likely to help, or to produce a particular difficulty profile. Randomised stratified sampling from a principled inclusion pool removes this concern and means results generalise to the broader population of issues in these codebases rather than a subjectively filtered subset.

### Inclusion Criteria (Pool Construction)
The following criteria were applied mechanically to construct the pool of candidate issues per repository. All criteria are principled exclusions with explicit rationale:

1. **At least one Python source file in ground truth** — issues targeting only config files, JSON, YAML, or non-Python assets are excluded as they do not test Python code localisation
2. **No absolute paths in ground truth** — e.g. `/home/user/project/file.py` cannot be resolved within the cloned repository and would always score F1=0
3. **No None values in ground truth** — dataset artifacts where the ground truth entry is null
4. **English title** — titles with >15% non-ASCII characters excluded (heuristic for non-English issues that may affect model performance inconsistently)
5. **English body** — bodies with >15% non-ASCII characters excluded for the same reason
6. **Non-empty body** — body must be at least 20 characters; empty or near-empty bodies provide no signal for the localisation task
7. **Non-empty title** — must have a meaningful title string

### Source File Filtering
Ground truth files were filtered to Python source files only for the purposes of pool construction and stratification. Files matching the following patterns were excluded:

- Test files: `test_*`, `*_test.py`, `/tests/`, `/test/`
- Benchmark files: `benchmark`, `bench_`, `asv_bench`
- Example files: `/examples/`, `/docs/`, `autogen.py`
- Config/data files: `setup.py`, `setup.cfg`, `.cfg`, `.toml`, `.ini`, `.json`, `.yml`, `.yaml`
- Snapshot/validation files: `.snapshot.`, `.validation.`
- Cython files: `.pyx`, `.pxd`, `.pxi`, `.in`
- Other: `conftest.py`, `mockserver.py`

This filtering was applied at pool construction time for stratification purposes. The full raw ground truth (including test files) is preserved in `data/issue_selection_random.csv` for reference. The source file filter is re-applied at scoring time consistently across all codebases.

### Stratified Sampling
For each repository, the pool was stratified by file type based on filtered source files:
- **Single-file issues**: ground truth contains exactly one source file after filtering
- **Multi-file issues**: ground truth contains two or more source files after filtering

Three issues were sampled per repository:
1. **Single** — one issue sampled randomly from the single-file stratum
2. **Multi** — one issue sampled randomly from the multi-file stratum  
3. **Flexible** — one issue sampled randomly from the remaining pool (either file type)

Sampling was performed without replacement. The overlap check ensured no two selected issues shared any ground truth files — if overlap was detected, sampling was retried up to 50 times before flagging a warning.

**Random seed: 88** (document this for reproducibility)

### Manual Override
**Deep-Live-Cam** was exempt from random sampling. The usable pool contained only 8 issues, with 5 of them targeting `modules/ui.py` — making it impossible to select three non-overlapping issues via random sampling. The three available non-overlapping issues were selected directly:
- [1] single — `modules/processors/frame/face_enhancer.py`
- [11] multi — `modules/ui.py` + `modules/core.py`
- [0] flexible — `modules/ui.py`

This limitation is noted in the methodology: Deep-Live-Cam has a narrow issue distribution concentrated in the UI module, which is a known constraint of this codebase.

### Ground Truth Resolution
**gpt-engineer [32]** had a bare filename `ai.py` as ground truth with no directory path. This was resolved to `gpt_engineer/core/ai.py` via unique basename matching within the repository (`find repos/gpt-engineer -name "ai.py"` returned exactly one match). This resolution is documented here for transparency.

### Distribution Validation
Following selection, the distribution of the selected issues was compared against the full pool using Mann-Whitney U tests (non-parametric, appropriate for bounded/skewed distributions) for file count and body length, and Fisher's exact test or chi-square for file type proportions. Tests were run overall and per size tier (small/medium/large). Results confirmed no statistically significant bias in file count or file type distribution between pool and selected. Body length comparison was noted as exploratory given the small selected n=45.

-------------------------------------------
Finalised Map Design to be Evaluated
-------------------------------------------
## Map Design Decisions

### Map Types
Three map types are generated per issue, all at `base_commit` (the state of 
the codebase immediately before the fixing PR was merged). Maps are scoped to 
the resolved package directory only, as determined by `scripts/package_resolver.py`.
Each map is stored as a separate file at `repo_maps/{repo}/{issue_idx}/`.

### AST Compact Map (`compact_map.txt`)
- Generated by `scripts/generate_ast_map.py` → `scripts/compact_map.py`
- Parses the package directory using Python's `ast` module
- Shows classes, methods, and module-level functions with:
  - Signatures and line numbers
  - Docstrings truncated to 80 characters
- Files sorted alphabetically
- `--skip-dirs` default is empty — no hardcoded exclusions
- Two-stage pipeline: raw NDJSON (`ast_map.json`) → compact text (`compact_map.txt`)

### Frequency Map (`freq_map.txt`)
- Generated by `scripts/generate_freq_map.py`
- For each source file in the package directory, reports:
  - Number of commits touching that file up to and including `base_commit`
  - Date of most recent such commit
- Covers all source files — no top-N cap
- Sorted by edit frequency descending (most edited files first)
- Generated via a single bulk `git log` call for performance
- Format:
requests/models.py  [89 edits, last: 2016-11-23]
requests/sessions.py  [71 edits, last: 2016-11-20]
### Co-change Map (`cochange_map.txt`)
- Generated by `scripts/generate_cochange_map.py`
- For each source file, shows the top 3 files most frequently edited 
  in the same commit, up to and including `base_commit`
- Symmetric — if A lists B as a co-change partner, B also lists A
- Co-change partners restricted to source files within the package 
  directory only (no test files, no external dependencies)
- No frequency or date information — co-change relationships only
- Generated via a single bulk `git log` call for performance
- Format:
requests/models.py
→ requests/sessions.py (23x)
→ requests/adapters.py (18x)
→ requests/utils.py (12x)
### Shared Decisions
- All maps generated at `base_commit` — no leakage of post-fix information
- Scope is the resolved package directory, not the full repo
- Vendored third-party code is included if present within the package 
  directory at `base_commit` — no special exclusion logic, ensuring 
  consistency across repos and commits without requiring per-repo knowledge
- Separate output files per map type ensure clean separation of concerns 
  in the harness
- Map generation statistics (commit date, files walked, token counts, 
  generation time) tracked in `repo_maps/map_generation_stats.csv`

## 2026-07-10 / 2026-07-11
## Codebase Size Audit and Extra-Repo Pool

### Motivation
After finalising the 45-issue selection, audited whether the small/medium/large
tier labels assigned to the 15 codebases actually reflect codebase size, and
whether the "large" tier covers a wide enough size range for the study.

### Size Audits
- `scripts/audit_repo_sizes_current.py` — measures Python and total text LOC
  for each of the 15 repos as currently checked out on disk (whole repo and
  main source package dir), independent of any specific issue's base_commit.
- `scripts/audit_codebase_sizes.py` — per-issue audit across all 45 selected
  issues, computing whole-repo and package-dir LOC at each issue's
  `base_commit` via `git archive`, to check whether tier labels are
  consistent with actual size at the commit each issue was scored against
  (not just current HEAD).
- `scripts/add_loc_to_stats.py` — folds LOC figures into the map generation
  stats table.
- Finding: the existing "large" tier tops out around ~220k LOC
  (`data/issue_pool_with_loc_summary.txt`), leaving no representation of
  substantially larger codebases.

### Extended Issue Pool with LoC
- `scripts/build_issue_pool_with_loc.py` — rebuilt the full usable-issue pool
  for all 15 existing repos (same usability filters as the original
  selection pool) with per-issue package-dir Python LoC measured at
  `base_commit`. 378 usable issues total. Confirms tier ordering: small
  (95 issues, mean ~5.3k LoC) < medium (83 issues, mean ~14k LoC) < large
  (200 issues, mean ~108k LoC, max 220k).
- `scripts/build_issue_pool_extra_repos.py` — identical pipeline applied to
  4 candidate repos not in the original panel: `youtube-dl`, `ComfyUI`,
  `transformers`, `home-assistant/core`. 70 usable issues found
  (`data/issue_pool_extra_repos.csv` / `_summary.txt`):
  - youtube-dl: 14 usable / 14 total
  - ComfyUI: 3 usable / 10 total
  - transformers: 33 usable / 44 total
  - core (home-assistant): 20 usable / 26 total
  - LoC range 4.3k–942k, mean ~343k — pushes well past the existing
    "large" tier ceiling. ComfyUI (~17k mean) is the only one landing in
    "medium"; the other three are all "large" or beyond.
- Tier labels in `build_issue_pool_extra_repos.py` are placeholders pending
  review of this LoC output — not yet reconciled with the main 15-repo
  selection or issue_selection_final.csv.

### Status
Exploratory — results not yet merged into the finalised issue selection.
Next step is deciding whether to add an extra size tier (e.g. "extra-large")
using one or more of these candidate repos, or to treat this purely as a
validation check on the existing tier boundaries.

## 2026-07-12
## Tackling the Map Size Problem: No-Docstring and Pruned Compact Maps

### Motivation
The audit above confirmed some compact maps are far too large to use as-is
(`core/17` reaches 652k tokens with docstrings). Started reducing map size
without regenerating the underlying AST data.

### Version 2: No-Docstring Compact Map
- `scripts/compact_map_nodoc.py` — same block format as
  `scripts/compact_map.py` (reuses its `_class_header`/`_fn_line` helpers),
  but omits all docstring lines. Renders directly from the existing
  `ast_map.json`, no AST re-parsing needed.
- `scripts/generate_nodoc_maps.py` — batch-generated `compact_map_nodoc.txt`
  for all 45 issues. Sizes recorded in `repo_maps/compact_nodoc_stats.csv`
  (original vs. nodoc chars/tokens, % reduction).
- Reduction ranged ~1% (fastapi — docstring-sparse) to ~49% (core —
  docstring-heavy).

### Version 3: Frequency-Pruned Compact Map
- `scripts/generate_pruned_maps.py` — built on top of the no-docstring map.
  Files are dropped one at a time, least-edited-first (per each issue's
  `freq_map.txt`), until the map is under a token budget. Equivalently:
  keep files in descending edit-frequency order, taking the largest prefix
  that fits (always keeps at least the single most-edited file, even if it
  alone exceeds budget).
- Kept files are rendered alphabetically in the output, matching the
  existing map convention.
- Parameterised by `--token-budget`; 30k keeps the original unsuffixed
  filenames (`compact_map_pruned.txt`, `compact_pruned_stats.csv`) for
  backward compatibility, other budgets get a `_{N}k` suffix so multiple
  budgets coexist (e.g. `compact_map_pruned_50k.txt`).
- At **30k tokens**: 15/45 issues require pruning (mostly yt-dlp, pandas,
  scikit-learn, transformers, core).
- At **50k tokens**: 12/45 issues require pruning.

### Ground-Truth-in-Pruned Check
- `scripts/check_pruned_ground_truth.py` — compares each issue's
  `ground_truth` files against the files dropped during pruning.
  Also parameterised by `--token-budget`.
- **At 30k**: 9/45 issues (20%) lose ≥1 ground-truth file to pruning
  (9/15 of the issues that get pruned at all). Of those 9, 5 lose *every*
  ground-truth file (`yt-dlp/23`, `pandas/35`, `pandas/38`, `core/17`,
  `core/16`) — the pruned condition has zero chance of localising
  correctly for these regardless of model quality.
- **At 50k**: 6/45 issues lose ≥1 ground-truth file; 3 lose all
  (`pandas/38`, `core/17`, `core/16`).
- Results: `data/pruned_ground_truth_check.csv` (30k) and
  `data/pruned_ground_truth_check_50k.csv` (50k).

### Minimum Budget to Retain ≥1 Ground-Truth File
- `scripts/min_budget_for_gt.py` — for every issue, walks the same
  descending-edit-frequency file order and finds the cumulative token size
  at which the *first* ground-truth file is reached. This is the minimum
  budget under which frequency-pruning would keep at least one correct
  answer file. Output: `data/min_budget_for_gt.csv`.
- Worst cases (a single very large/rarely-edited codebase can force the
  minimum budget close to the size of the full map):

  | repo | issue | role | min tokens for ≥1 GT file | full map size |
  |---|---|---|---|---|
  | core | 17 | single | 190,391 | 337,766 |
  | core | 8 | multi | 133,870 | 282,257 |
  | core | 16 | flexible | 53,692 | 155,996 |
  | pandas | 38 | flexible | 52,911 | 89,453 |
  | yt-dlp | 23 | flexible | 42,218 | 78,780 |
  | pandas | 35 | single | 39,566 | 53,361 |
  | scikit-learn | 45 | multi | 34,161 | 50,433 |
  | transformers | 5 | multi | 33,609 | 95,590 |
  | scikit-learn | 5 | flexible | 28,899 | 46,547 |
  | transformers | 27 | flexible | 28,731 | 222,549 |

  A budget of ~53,700 tokens would guarantee ≥1 ground-truth file survives
  for every issue except `core/17` and `core/8`, which need 134k–190k
  tokens — i.e. pruning essentially cannot help those two without
  defeating its own purpose.

### Separate Finding: AST-Map Blind Spot (not a pruning artifact)
- `fastapi/20`'s ground truth is `fastapi/background.py`, a one-line
  re-export module (`from starlette.background import BackgroundTasks as
  BackgroundTasks  # noqa`) with zero classes/functions. It never appears
  in the AST-based map **at any budget, pruned or not** — files with no
  top-level defs are invisible to AST-based compact maps by construction.
  This is a structural limitation of the map type, not of the
  frequency-pruning approach, and needs a separate decision (exclude the
  issue from map-based conditions, or document as a known limitation).

### Status
Exploratory. Open decisions: (1) whether the 3rd map version should prune
from the no-docstring base (as implemented) or from the original
with-docstring compact map instead; (2) what token budget to standardise
on given the ground-truth-loss tradeoffs above; (3) how to handle
`core/17`/`core/8` (structurally unprunable without losing the answer) and
`fastapi/20` (AST blind spot) in the final study design.

## 2026-07-12 (cont'd)
## Finalising Pruned Maps at 55k, Extended to Freq/Co-change

### What Was Done
Settled on 55k tokens as the working cutoff and extended the same
least-frequently-edited-first pruning rule (previously only applied to the
compact map) to the frequency map and co-change map, since both can also
blow the budget for the largest repos:

- `scripts/generate_pruned_aux_maps.py` — prunes `freq_map.txt` and
  `cochange_map.txt` per issue, independently of each other and of the
  compact map (a file kept in the pruned compact map is not necessarily
  kept in the pruned freq/cochange map, since per-file token cost differs
  by map type). Freq map pruning is a straight prefix-cut (it's already
  sorted by edit count); co-change map is re-ranked by edit frequency, then
  cut, then re-rendered alphabetically to match the existing format.
- `scripts/check_aux_pruned_ground_truth.py` — same ground-truth-loss check
  as `check_pruned_ground_truth.py`, applied to the freq/cochange outputs.
- Also ran `check_pruned_ground_truth.py --token-budget 55000` (previously
  only checked at 30k/50k).

### Results at 55k
Only the three `core` issues need any pruning at all for freq/cochange —
every other repo's freq and co-change maps stay under 55k tokens even
though their compact maps don't. Co-change is the most expensive format per
file (~3x the size of the freq map for the same file set), so it gets
pruned hardest among the three map types.

| map type  | issues pruned | issues losing ≥1 GT file | which                                      |
|---|---|---|---|
| compact   | 10/45          | 5/45  | pandas/38, transformers/5, transformers/27, core/17, core/8 |
| freq      | 2/45 (core/17, core/8) | 0/45 | — |
| cochange  | 3/45 (core/17, core/8, core/16) | 2/45 | core/17, core/8 |

**`core/17` and `core/8` are the only issues that lose ground truth across
all three map types.** Every other affected issue (`pandas/38`,
`transformers/5`, `transformers/27`) only loses its ground-truth file from
the *compact* map — the frequency and co-change maps for those same issues
still surface the correct file, since those formats cost far fewer tokens
per file and survive pruning much further down the edit-frequency tail.

### Implication: Argument for a Selective-Probe Tool
This is the clearest evidence yet that flat token-budget pruning is the
wrong lever, not just an implementation detail to tune. The core problem:
handing the model one fixed, pre-truncated map forces a single global
cutoff decided in advance, with no way for the model to trade "more files,
less detail" against "fewer files, more detail" based on what the actual
issue needs. Two concrete symptoms observed above:
- The compact map is by far the most expensive format per file (full
  signatures + structure), so it gets cut earliest and loses ground truth
  most often — even though it's also the most informative format when a
  file *is* included.
- `core/17`/`core/8` need 134k-190k tokens (from the 2026-07-12 min-budget
  analysis above) just to reach one correct file under this frequency
  ordering — no single fixed budget in a realistic range recovers them,
  because the useful signal (which file is relevant) isn't correlated with
  edit frequency for these two issues specifically.

Both symptoms point the same direction: instead of pre-pruning a static
map to fit a token budget, give the model a **tool to query the map
on-demand** — e.g. list files (freq/cochange only, cheap), then request
the full compact-map entry (signatures, docstrings) for specific files it
already suspects are relevant, rather than paying the compact-map token
cost for every file up front. This would let the model spend its context
budget adaptively per issue instead of accepting whatever a fixed
frequency-based prefix happens to include, and should directly fix the
`core/17`/`core/8` failure mode where the answer file is real but
buried too deep in edit-frequency rank to survive any fixed-budget cutoff.

### Status
Finalised at 55k for now as the fixed-budget baseline condition. The
selective-probe tool idea above is a candidate follow-up experimental
condition, not yet designed or implemented.

## 2026-07-12 (cont'd 2)
## Dropped core/17 and core/8, Replaced with core/20 and pandas/26

### Why
Both issues were structurally unprunable without losing the answer: the
min-budget analysis above showed core/17 needing 190,391 tokens and core/8
needing 133,870 tokens just to keep one ground-truth file, an order of
magnitude past any realistic budget, and losing ground truth across all
three map types (compact, freq, cochange) at every budget tested.

### Replacement Selection
- `core/20` (single, tier=large) — from the extra-repo candidate pool
  (`data/issue_pool_extra_repos.csv`), file_type=single, matching core/17's
  role. Base commit `f29e0bf5` (2017-04-25) is much earlier/smaller than
  core/16's — home-assistant's `generated/` dir (the auto-generated lookup
  tables previously always skipped) doesn't exist yet at this commit, so
  `extra_skip_dirs: []`.
- `pandas/26` (extra, tier=large) — from `data/issue_pool_with_loc.csv`,
  file_type=multi. core/8's "multi" role slot is not backfilled within
  core; instead pandas gets a 4th issue. The panel is now intentionally
  asymmetric: core contributes 2 issues (single + flexible), pandas
  contributes 4 (single + multi + flexible + extra). Total stays 45.
- `data/repo_skip_config.yaml` updated to match (core/17, core/8 entries
  removed; core/20, pandas/26 added).

### Regeneration
- `scripts/generate_all_maps.py` gained an `--only repo:idx [...]` filter
  so map generation can target specific issues instead of re-running all
  45 — core alone takes 45-65 minutes per issue on this filesystem (WSL
  `/mnt/c`, slow for repos with many small files), so a full rerun would
  have been wasteful. The stats CSV write was changed from an overwrite to
  a merge (keep untouched rows, replace/add rows for the targeted issues,
  drop rows for issues no longer in issue_selection_final.csv) so partial
  reruns stay consistent.
- The first regeneration attempt was killed by its own timeout mid-checkout,
  leaving `repos/core_full` detached at core/20's commit with a dirty
  working tree (interrupted mid-write, no stash/backup involved since this
  clone is only ever used for automated checkout/archive, never edited by
  hand) — recovered via `git checkout --force dev` back to the resting
  branch identified from the reflog.
- The second attempt completed map generation successfully (core/20 in
  2586s, pandas/26 in 358s) but crashed writing `map_generation_stats.csv`
  — the file was open in a Windows program (this repo lives on `/mnt/c`).
  Rather than repeat the ~45 minute core checkout a third time,
  `scripts/recover_map_stats.py` was added to recompute the stats row
  for already-generated issues directly from the map files on disk plus a
  fast `git archive`-based file/LOC count (no working-tree checkout
  needed), then merge into the stats CSV once the lock was released.
- Full downstream pipeline re-run for the new 45-issue set: no-docstring
  maps, pruned compact maps (30k/50k/55k), pruned freq/cochange maps
  (55k), and all ground-truth-presence checks. All of these read only
  already-generated local files (no checkout), so they ran in seconds.

### Result
The swap fixed the problem it targeted:
- Worst-case `min_tokens_for_one_gt` across all 45 issues dropped from
  190,391 (core/17) to **53,692** (now core/16) — comfortably under the
  55k budget. No issue is structurally unprunable any more.
- At 55k: freq map and co-change map now lose 0/45 ground-truth files
  (previously cochange lost 2, both core). Compact map still loses ground
  truth on 3/45 issues (`pandas/38`, `transformers/5`, `transformers/27`)
  — none of them `core` issues any more.
- `core/20` behaves like a normal large-tier issue (needs pruning in the
  30k-55k range, unlike core/17/core/8's multi-hundred-k requirement).
  `pandas/26` needs no pruning above 30k tokens at all.
- Old `repo_maps/core/17/` and `repo_maps/core/8/` map directories deleted.

### Status
Done. Panel is now: core=2 issues, pandas=4 issues, the other 13 repos
unchanged at 3 issues each = 45 total.

## 2026-07-12 (cont'd 3)
## Harness Rewrite for Multi-Repo, Parallel Workers + a Source-Filter Bug Fix

### Harness Rewrite
`harness/run_trial.py` was hardcoded to a single repo ("requests") and a
flat `results/{model}/task_{n}_{map}_rep{r}.json` layout — rewritten for
the full 15-repo, 45-issue, multi-worker setup:
- `--repo-path` / `--issue-idx` replace `--task`; repo name is derived
  from the repo folder's basename (works regardless of which `worker_N/`
  parent it's nested under), reusing `generate_all_maps.REPO_DIR_MAP`
  (reversed) so the mapping can't drift from the map-generation scripts.
- `--map` choices are now `none, ast_compact, freq, cochange`, each
  loading the finalised no-docstring, 55k-pruned file
  (`compact_map_pruned_55k.txt` / `freq_map_pruned_55k.txt` /
  `cochange_map_pruned_55k.txt`). Missing map file → warns and proceeds
  with no map rather than failing the trial.
- Each map type got its own system-prompt description instead of one
  generic "{map_type} codebase map... lists every class and function"
  string, which was actively wrong for freq/cochange. New descriptions
  explicitly warn the model that (a) the list may not be exhaustive
  (pruning) and (b) appearing in the freq/cochange map is a weak signal,
  not proof of relevance — aimed at preventing over-indexing on
  frequently-edited or co-changed files that are just generic/coupled for
  unrelated reasons.
- Default-branch restore: repo is now restored to a fixed known-good
  branch per repo (`DEFAULT_BRANCH`, keyed by folder basename) at trial
  end, rather than to whatever commit was checked out when the trial
  started. Self-healing against exactly the kind of crash hit earlier
  this session with `core_full` (interrupted mid-checkout, left detached
  at the wrong commit) — a later trial on that worker copy no longer
  inherits a broken prior state.
- Result path: `results/{model}/{repo}/{issue_idx}/{map_type}/rep{n}.json`.
- `issue_selection_final.csv`'s `body` column was blank for 43/45 rows
  (only core/20 and pandas/26, added by hand, had it) — backfilled from
  the pickle so the harness never needs to load the 3.5MB pickle at
  trial-run time, only the lightweight CSV.

### Source-File Filter Bug
Auditing `issue_selection_final.csv` against the generated maps surfaced
a bug in `source_files_only()` (the filter that reduces a raw ground-truth
file list to the Python-source subset used for scoring — per the
methodology, `ground_truth` stores the full raw list and this filter is
meant to be applied at scoring time, consistently). It excluded via
substring match on patterns like `"/tests/"` and `"/examples/"`, both
requiring a leading slash — so a file sitting directly at the top of an
excluded directory (e.g. `tests/caching_ai.py`, `examples/cifar10_cnn.py`,
no other path prefix) silently survived the filter.

Fixed by prepending `/` to the path before matching (`scripts/source_filter.py`,
new single canonical copy — previously duplicated identically in both
`build_issue_pool_with_loc.py` and `build_issue_pool_extra_repos.py`, now
both import it). Wired into `run_trial.py`'s `compute_scores()`, which now
filters both `predicted` and `ground_truth` before computing precision/
recall/F1 — a model isn't penalised on precision for correctly not
predicting a test/example/doc file either. Result JSON keeps both the raw
and filtered lists (`ground_truth` / `ground_truth_scorable`,
`final_files_predicted` / `final_files_predicted_scorable`) for auditability.

**Impact on the 45 selected issues: negligible.** Only `gpt-engineer/12`
is affected (`tests/caching_ai.py` now correctly excluded, 6→5 scorable
ground-truth files) and its `multi` classification is unchanged — no
re-selection needed.

**Impact on the unused candidate pools** (`data/issue_pool_with_loc.csv`,
`data/issue_pool_extra_repos.csv` — issues that passed eligibility but
were never sampled into the 45): 8 issues would now have zero scorable
source files and should have been excluded from the pool entirely (all
of them are example/doc-only issues — `flask/11`, `keras/21`, `keras/24`,
`scikit-learn/0`, `scikit-learn/34`, `transformers/12`, `transformers/28`,
`transformers/29`); 5 more would have their single/multi label change
after dropping non-source entries (`scrapy/4`, `scrapy/45`,
`scikit-learn/4`, `scikit-learn/20`, `transformers/26`). **Not fixed** —
these pool CSVs are not used going forward, and a full rebuild would cost
hours (the build scripts do a real per-issue `git checkout`, and the pool
includes many `core`/`transformers` issues at ~45-65 min each on this
filesystem). Documented here only, in case the pool is ever revisited.

## 2026-07-12 (cont'd 4)
## Harness Validation, Study Archival, and the Batch Runner

### Rewritten Harness: Live Validation
Ran a real single trial end-to-end (`mistral/ministral-3b-latest` against
`requests/7`, `ast_compact` map) to confirm the rewrite actually works,
not just compiles:
- Repo folder → canonical repo name resolution correct.
- Issue lookup (title/body/ground_truth/base_commit) pulled correctly
  from `issue_selection_final.csv`, no pickle dependency at runtime.
- Map loading worked; model referenced map content before falling back to
  `search`.
- `repos/requests_full` was sitting in a leftover detached-HEAD state
  from an earlier session — checkout to the issue's `base_commit` worked
  regardless, and the new default-branch restore logic (restore to a
  fixed known-good branch per repo, not to whatever was checked out
  before the trial started) correctly left the repo cleanly on `main`
  afterward. This is exactly the self-healing behaviour it was designed
  for, confirmed working on a real leftover-bad-state case rather than
  just in theory.
- Scoring correct: `ground_truth`/`predicted` both passed through
  `source_files_only()`, F1 = 1.0, both raw and filtered lists saved in
  the result JSON.
- Result/log paths matched the new nested layout
  (`results/{model}/{repo}/{issue_idx}/{map_type}/rep{n}.json`).
- Cost was $0.00000 (ministral-3b is essentially free) — kept as a
  permanent baseline sanity-check result rather than deleted.

### Archived the Exploratory Study into study_0/
Before any new trials could safely run, the complete pre-rewrite study
output needed separating from what the new harness would start writing
at the same repo-relative paths:
- `results/` (1215 files) → `study_0/results/`
- `logs/` (1229 files, mostly gitignored except 72 stray tracked files)
  → `study_0/logs/`
- `repo_maps/requests/`'s non-numeric entries (loose whole-repo
  `requests_ast_map.json`/`requests_ctags_map*.json`, and the old
  `task_0`/`task_4`/`task_12`/`task_14`/`task_15` directories from the
  pre-rewrite task-indexed harness) → `study_0/repo_maps/requests/`.
  `repo_maps/requests/` now contains only the current numeric issue
  directories (7, 12, 13).
- Root-level `results_all.csv`, `results_summary_devstral_medium_pooled.csv`,
  `results_summary_tables.txt` → `study_0/`.
- Two gotchas hit during the move, both from `.gitignore` patterns with a
  `/` in the middle (e.g. `!results/**/*.json`, `logs/`) being anchored
  to the repo root — they don't apply to the same directory name nested
  under `study_0/`, so files there fell back under the blanket `*.json`
  ignore rule and needed `git add -f` to stay tracked at the new
  location. Also caught (post-commit) that a `git add -A` scoped to only
  the new-side pathspecs misses staging the old-side deletion for paths
  outside those pathspecs — 3 root CSV/txt files were briefly duplicated
  in the tree until a follow-up commit staged their deletion explicitly.

### Batch Runner Rewrite (run_batch.py) + Supporting run_trial.py Changes
`run_batch.py` was rewritten for the full 45-issue × 4-map-condition,
multi-worker setup: loads `issue_selection_final.csv`, builds the trial
list (skip if result exists, skip-with-warning if a non-`none` map file
is missing), worker+rep-seeded shuffle, sequential execution with 900s
timeout / 2 retries / 30s backoff, progress logging, a full batch summary
(tokens incl. cached, cost, stop-reason breakdown, failures), and a saved
batch log at `logs/batch_{worker_id}_{rep}_{model}_{date}.log`.

This required two small additive changes to `run_trial.py` first, since
the spec's `--repos-base`/`--maps-base`/`--results-base` only work if the
trial subprocess actually reads/writes at those same locations:
- `--maps-base`/`--results-base` optional overrides (default: unchanged
  repo-relative behaviour), so the batch runner's skip-logic and the
  actual trial output agree on where things live.
- `total_cached_tokens` added to the metrics, read from litellm's
  normalised `usage.prompt_tokens_details.cached_tokens`. Confirmed via
  two live trials that this is populated correctly in both directions
  (0 when caching didn't apply, 25,472 on a repeat run against the same
  prefix).

Default base paths (`/home/afb225/study1/...`) point at a native Linux
filesystem location that doesn't exist yet on this WSL dev machine — the
plan (not yet executed) is to copy the repos/maps there to avoid the WSL
`/mnt/c` checkout slowness hit repeatedly this session (`core_full`
alone: 45-65 min per checkout). `run_batch.py` is being prepared ahead of
that move, not run against it yet.

**Live end-to-end test of the batch runner**: no real `worker_1..5`
directories exist on this machine yet, so a temporary `worker_1`
directory of symlinks to the already-cloned repos was created under
`/tmp`, and 179 of the 180 possible (issue × map) result slots were
stubbed as "already done" so the batch runner would only actually
execute one real trial. Confirmed: correct skip counts (179 skipped / 1
run), correct worker-path resolution through the symlink, the one real
trial ran through the full harness correctly, and the printed summary
matched the saved batch log file exactly. All test artifacts (symlinks,
stubs, the real trial's result/log, the batch log) cleaned up afterward.

### Status
Harness and batch runner both validated end-to-end on this machine.
Nothing committed yet for this round of changes. Next step when ready:
the native-filesystem move, then real batch runs.

## 2026-07-13
## Fixed the AST Parser Blind Spot, Regenerated All AST Maps

### The Fix
`generate_ast_map.py`'s `extract_file()` had `except SyntaxError: return []`
-- a file that failed to parse was silently treated identically to a file
with no classes/functions at all, no warning anywhere. Audited every
"invisible" file across all 45 issues (945 files, 8.9% of the corpus) by
attempting `ast.parse()` directly: 893 were genuinely empty of top-level
defs (legitimate -- re-export shims like `fastapi/background.py`,
`__init__.py` aggregators), but 52 were real parse failures, concentrated
in three issues from old codebases: `core/16` (1 file), `core/20` (26
files), `pandas/44` (26 files, including pandas' own `core/frame.py`,
`core/series.py`, `core/groupby.py`, `core/indexing.py` -- and
`core/indexing.py` is `pandas/44`'s own ground truth).

Two distinct root causes, both patched as a best-effort fallback (tried
only when the unpatched source fails to parse; preserves line count so
line numbers stay accurate; not a general Python 2->3 translator, just
targets exactly what's in this corpus):
- **Python 2 syntax** (pandas, ~2013): `except X, e:`, `print X`
  statements, `raise X, "msg"`, `123L` long-literal suffixes, leading-zero
  decimal literals (`datetime(2011, 11, 01)`), `ur'...'` string prefixes,
  UTF-8 BOM.
- **`async` reserved keyword** (home-assistant, ~2017): `async` became a
  reserved word in Python 3.7, breaking `from homeassistant.util.async
  import x` / `from .async import x` -- home-assistant had a whole module
  named `async.py` at this era. Renaming `.async` -> `.async_` in import
  paths is safe here since import statements don't themselves produce
  AST records.

Residual: 1 file still fails (`homeassistant/util/async.py` itself, which
does `from asyncio import async` as a bare name plus `ensure_future =
async` -- fixing this generally would require rewriting bare `async`
identifiers, which risks corrupting genuine `async def`/`async with`
elsewhere; not worth the risk for one file that was already invisible
before this fix with no regression). Now logged as a WARNING instead of
silently dropped either way.

### Also Rewrote generate_ast_map.py to Use git archive, Not Checkout
While fixing this, converted the script from "checkout working tree, then
os.walk + open()" to "git archive the package dir straight from git
objects, parse in-memory from a tarfile" -- no working tree is touched at
all. This eliminates the WSL `/mnt/c` slow-checkout cost that has been a
recurring problem all session (core/transformers taking 45-65 min per
checkout). Confirmed on `pandas/44`: 3.7s vs. several minutes before.
Full 45-issue regeneration (this step only) took about 2 minutes total,
vs. an estimated ~1 hour-plus with the old checkout-based approach.

### Regeneration
New `scripts/regenerate_ast_maps.py` regenerates only the AST-derived
artifacts (`ast_map.json`, `compact_map.txt`) for all 45 issues and merges
the updated stats into `map_generation_stats.csv` -- deliberately does
*not* touch `freq_map.txt`/`cochange_map.txt`, since those don't parse
file contents and are unaffected by this fix. Followed by the existing
`generate_nodoc_maps.py`, `generate_pruned_maps.py` (30k/50k/55k), and a
re-run of `check_pruned_ground_truth.py` (all 3 budgets) and
`min_budget_for_gt.py`, since the recovered files change compact-map
composition and pruning outcomes.

Functional changes landed in exactly the 3 affected issues (`core/16`,
`core/20`, `pandas/44`) -- every other issue's `compact_map.txt` is
byte-identical (the corresponding `ast_map.json` shows a diff purely from
record-order differences between the old `os.walk` traversal and the new
sorted-tarfile-member traversal; confirmed identical after sorting both).

**Confirmed fix**: `pandas/44`'s ground truth `pandas/core/indexing.py` --
previously invisible at every budget -- is now present in the full
compact map and survives pruning at all three budgets tested. It no
longer appears in any ground-truth-pruned-away list.

### Status
Done. Not yet committed. The deepseek-v4-flash batch results committed
yesterday were generated against the *old* (buggy) maps for `core/16`,
`core/20`, and `pandas/44` specifically -- worth a re-run of just those
if/when doing the consolidated re-run mentioned in the harness-fix entry
above.

