# Fix Checklist

Known issues found during Study 3, deliberately not fixed immediately
(e.g. batches were actively running against the affected code) --
tracked here so they don't get lost. Check items off and move a short
note to DEVLOG.md once actually fixed.

- [x] **Submit-gate doesn't cover the plain-text "stop" exit path.** Fixed
  2026-07-23 -- see DEVLOG. Original description kept below for context.
  `harness/run_trial_{structural,temporal_frequency,temporal_cochange,
  all_tools}_required.py` only gate the explicit `submit_answer` tool
  call. A model that ends a turn with prose and no tool calls at all
  (`finish_reason == "stop"`, `tool_calls == []`) hits
  `if finish_reason == "stop" or not tc_list: stop_reason = "end_turn";
  break` and exits the main loop immediately, bypassing the gate
  entirely -- then falls into the forced-final-answer extraction, which
  was deliberately left ungated on the assumption the trial was already
  ending regardless either way. That assumption only covered the
  max-turns-exhausted case, not a model choosing to stop early.

  Found via a live gpt-oss trial (`requests/7`, `temporal_cochange_required`,
  worker 5) that ended via `finish_reason=stop` on turn 5 -- happened to
  have already called `lookup_cochange` on turn 3, so the requirement
  was incidentally satisfied that time, but the gate never actually
  checked it on that exit path. On a trial where the model stops early
  *without* having called anything yet, this lets it through completely
  ungated.

  **Fix**: apply the same `gate_satisfied` check at the
  `finish_reason == "stop"` exit point, sharing the same
  `submit_rejections`/`MAX_SUBMIT_REJECTIONS` counter as the
  `submit_answer` gate (so a model alternating between "tries to stop
  early" and "tries to submit early" doesn't get double the pushback
  budget). If not satisfied, inject a message and `continue` instead of
  `break`. Needs a new message constant (`NO_TOOL_CALL_REJECTION_MESSAGE`
  or similar) since `SUBMIT_REJECTION_MESSAGE`'s wording specifically
  references `submit_answer`, which wasn't actually called on this path.

  **Scope check needed once fixed**: count how many already-collected
  required-batch trials ended via `stop_reason == "end_turn"` (i.e. were
  silently ungated) across all 3 models' required batches so far --
  those may need re-running under the corrected gate, not just new
  trials going forward.

- [x] **Malformed tool-call names aren't recovered, undercounting real
  tool usage.** Fixed 2026-07-23 in the four `_required` harnesses only
  -- see DEVLOG. Still present in the voluntary (non-`_required`)
  harnesses and in `scripts/lookup_tools.py`-adjacent dispatch, since
  this fix was scoped to Study 3. Original description kept below for
  context. Mistral occasionally returns a mangled `name` field
  instead of cleanly separating name/arguments -- two shapes seen so
  far in real batch data: `list_files""` (real name plus trailing junk)
  and `lookup_structure{"path": "test_requests.py"}` (arguments JSON
  concatenated onto the name, with `tc.function.arguments` coming back
  empty -- the real arguments only exist inside the mangled name
  string). `execute_tool()`'s exact-match dispatch returns "unknown
  tool" for both, wasting a turn and giving the model nothing useful,
  and in the required-condition harnesses, `if name in
  REQUIRED_LOOKUP_TOOLS` can't recognize either shape as real usage --
  found via a `structural_required`/ministral trial where this directly
  caused a `submit_answer` rejection despite the model clearly intending
  to call `lookup_structure`.

  Unlike the DeepSeek/DeepInfra `tool_choice` rejections already
  documented as accepted residual limitations (2026-07-13), this one is
  recoverable -- the call succeeds and the real intent is sitting in the
  string, it's a parsing problem, not a lost-cause one.

  **Fix**: add a normalization step where `name = tc.function.name` is
  first read (`harness/run_trial*.py`, all variants including the
  `_required` ones), before any dispatch/gate logic. If `name` doesn't
  exactly match a known tool, check whether it starts with one followed
  by `{` (split there, `json.loads()` the remainder as the real
  arguments, since `tc.function.arguments` is unreliable in this exact
  failure mode) or by junk/trailing characters (strip and use the
  recovered name with the original arguments as-is). Falls through to
  the existing "unknown tool" error unchanged if neither pattern
  matches.

  **Why this one's higher-priority than it looks**: it directly
  corrupts the metric Study 3 exists to measure -- some fraction of
  "rejected"/"didn't use the tool" in the required-condition results
  are really "did use the tool, the API just mangled the call."
  `scripts/compare_tool_usage.py`'s `required_malformed_near_miss_trials`
  column already surfaces the scale of this per model/condition; worth
  checking that column before trusting any required-vs-voluntary
  comparison at face value, and re-deriving it once this is fixed.

- [ ] **Malformed-name normalization not applied to the voluntary
  (non-`_required`) harnesses.** The 2026-07-23 fix (see above and
  DEVLOG) only touched `harness/run_trial_{structural,
  temporal_frequency,temporal_cochange,all_tools}_required.py`, since
  that's what Study 3 needed. A scan of the real results tree found
  **1,125** malformed-name instances across *all* conditions, not just
  the required ones -- so voluntary-condition tool-usage rates (Study 2)
  are undercounted by the same mechanism, just not yet fixed there.
  Same fix (`_normalize_tool_call`, `KNOWN_TOOL_NAMES`) should port over
  directly; low risk, mechanical change.
