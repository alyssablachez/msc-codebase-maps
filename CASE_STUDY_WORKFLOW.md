# Case-Study Workflow — Self-Instructions

Written 2026-08-09 ahead of an expected auto-compaction, so the
established workflow/conventions survive context loss. This is a
working reference for me (Claude), not user-facing documentation —
keep it updated as the workflow evolves, don't let it go stale.

## What this project is

MSc research: do codebase "maps" (structural/frequency/co-change
signals) help LLM agents localize the right files for GitHub issues?
Three studies (wholesale map injection / voluntary tool retrieval /
submit-gated tool retrieval) × 4 models × 45 issues × 12 conditions.
Two live tracking artifacts:

- **`data/model_failure_points.md`** — numbered failure-point taxonomy
  (currently up to **entry #53**), plus a "Notes on use" section at the
  end with a running issue list, cross-cutting pattern notes, and
  confirming-instance mentions that *don't* get their own entry.
- **`data/issue_case_study_notes.csv`** — one row per issue (45 total),
  ranked by `rank` (1 = highest mean F1, 45 = lowest). Columns:
  `rank,repo,issue_idx,mean_f1,title,ease_of_connection,common_wrong_file,
  wrong_file_type,precision_or_recall_issue,model_decisiveness_notes,
  efficiency_notes,model_behaviour,notes,best_map_potential`.

## Current state (check live, don't trust this number once stale)

```
python3 -c "
import csv
with open('data/issue_case_study_notes.csv', newline='', encoding='cp1252') as f:
    rows = list(csv.DictReader(f))
unfilled = [r for r in rows if not r['notes'].strip()]
print(f'{len(unfilled)} remaining')
for r in sorted(unfilled, key=lambda r: int(r['rank'])):
    print(f\"  rank {r['rank']:>2}  {r['repo']}/{r['issue_idx']}  F1={r['mean_f1']}\")
"
```

As of writing: **6 remaining** — rank 4 `transformers/25`, rank 5
`rich/1`, rank 6 `scikit-learn/5`, rank 7 `scikit-learn/49`, rank 8
`requests/7`, rank 9 `flask/6`. Workflow has been moving up through
rank order (started around rank 21, working toward rank 1) — but just
follow whatever the user names next ("next issue" / "`<repo>
<issue_idx>`").

**Uncommitted work**: check `git status --short` at the start of every
session — don't assume prior turns' CSV/entry edits were committed.
Only commit when explicitly asked. Last known commits:
`71073441` (scrapy/26, localstack/2, flask/3, localstack/9; #47-50) and
`48217e1f` (run_replication_check.py localstack/2 addition) — several
issues analyzed *after* that point (thefuck/5 #51, rich/8, core/20 #52,
requests/13 #53, core/16, keras/9) may still be sitting uncommitted.

## Per-issue workflow (the established, repeated pattern)

1. **Pull trial data**:
   `python3 scripts/case_study_analysis.py --repo X --issue-idx N --sections files,grid,search,turns`
   (add `--sections touch --touch-file <path>` for touch-vs-kept checks
   on a specific file; `--grid-file` to restrict the grid).

2. **Get the issue text + real fix**: pull `title`/`body`/`ground_truth`
   from `data/issue_selection_final.csv`, then find the matching entry
   in `data/all_issues_with_pr_commit_comment_all_project_0922.pkl`
   (search by `repo_name` + title match) for `pr_html_url`, `loc_way`,
   `file_loc`. **Always check the actual PR/commit diff on the native
   machine** (`/home/afb225/study1/repos/<repo>_full`, `git log`/`git
   show` on the base_commit..HEAD range for the GT file) rather than
   inferring the fix from ground-truth filenames alone — this has
   repeatedly surfaced things ground truth alone hides: reverted PRs
   (#43), docstring-only companion files with zero functional change
   (#45, and the broader "ancillary ground-truth file" pattern:
   `fastapi/9`, `pandas/44`, `requests/12`, `flask/18`), single-line
   fixes, fix relationships that didn't exist before the fix commit
   itself created them (#37), traceback-cascades-into-vendored-code
   (#42).

3. **Diagnose the per-model split**: right/wrong file hit counts,
   search-term quality, touch-vs-kept gaps (`touched` = a `read_file`
   or `lookup_*` call on that path; `kept` = present in
   `final_files_predicted_scorable`), turn counts, `stop_reason`
   (`submitted`/`max_turns`/`end_turn`). **Whenever a model's score is
   surprising, trace the actual transcript directly** (raw JSON, not
   just aggregates) before asserting a cause — this has overturned
   initial hypotheses repeatedly (co-change "helping" that turned out
   to be plain search; a co-change link that looked strong from one
   file's side but was truncated from the other; "empty" submissions
   that were actually a malformed JSON key with the right answer buried
   inside, #53).

4. **Present findings** in the established narrative: bug/fix
   explanation → right/wrong file breakdown → search-term breakdown →
   model-behavior/map-effect diagnosis → ask whether to log + conjecture.

5. **Decide whether it's a new entry, a confirming instance, or nothing
   new** — don't assume, ask if unclear:
   - **New numbered entry**: genuinely novel mechanism not covered by
     an existing entry.
   - **Confirming instance, no new entry**: matches an established
     family exactly (touch-vs-kept commitment gap — #7/#9/#10/#15/#18/
     #23/#28/#44/`scrapy/48`/`rich/8`; DeepSeek forced-answer compliance
     — #50, confirmed again by `flask/3`/`localstack/9`; gpt-oss
     capitalization — #51). Add a one-line mention in "Notes on use"
     near the existing family list, or just note it in the CSV `notes`
     column — user has been directing which treatment each time.
   - **Update an existing entry**: new evidence changes or extends a
     prior claim (e.g. `keras/9` proved #51 wasn't `thefuck`-specific —
     corrected the entry's own framing and reran the check dataset-wide
     rather than leaving the old claim standing).
   - **Nothing notable**: some issues are just clean and ordinary
     (`core/16`) — say so, don't manufacture a finding.

6. **If logging a new entry**: match the existing format exactly —
   `## N. <one descriptive sentence, sometimes with a dash-clause>`,
   then `**Type:**`, `**Evidence:**` (with real numbers/quotes/tables),
   a `**Checked X directly**` transition before any generalization
   claim, `**Practical implication:**` with a conjecture. Then:
   - Bump the `"Thirty-X issues analyzed so far (...)"` line and its
     issue list in "Notes on use" (`grep -n "issues analyzed so far"`).
   - Add a short cross-reference blurb in "Notes on use" if it connects
     to other entries (not mandatory for every entry).

7. **Fill the CSV row**. Match by `(repo, issue_idx)`, not rank.
   **Critical encoding gotchas**:
   - Open with `encoding='cp1252'`, NOT `utf-8` (file has non-UTF8 bytes).
   - Write with `csv.writer(f, lineterminator='\n')` — the default
     `\r\n` corrupts every row's line endings, not just the one you
     changed. Always `git diff --stat` after writing and confirm only
     the intended row(s) changed.
   - `PermissionError` on write = the file is open in Excel/etc. on the
     Windows side. Ask the user to close it and retry — don't work
     around it another way.
   - Established column value vocabularies (reuse, don't invent new
     ones casually): `ease_of_connection` ∈ {quoted, convention,
     traceback-direct, misleading, investigation-required,
     traceback-direct-but-wrong}; `wrong_file_type` ∈ {plausible-sibling,
     none, traceback-direct-but-wrong}; `precision_or_recall_issue` ∈
     {mostly-recall-loss, mostly-precision-loss, n/a-mostly-correct,
     n/a-completely-incorrect}; `best_map_potential` ∈ {none, structural,
     frequency, co-change, or a comma-combo}.

8. **Commit only when explicitly asked.** Case-study data
   (`issue_case_study_notes.csv` + `model_failure_points.md`, sometimes
   + `DEVLOG.md`) commits together; any `scripts/*.py` changes get a
   separate commit. Never add a `Co-Authored-By` line (standing
   instruction). `git commit` on this repo often reports a 2-minute
   shell timeout even when the commit actually succeeded — verify via
   `git log -1` / `git status` rather than assuming failure.

## Standing conventions (don't re-derive)

- **`MAP_TYPE_GROUPS`**: Structural = {ast_compact, structural,
  structural_required}; Frequency = {freq, temporal_frequency,
  temporal_frequency_required}; Co-change = {cochange, temporal_cochange,
  temporal_cochange_required}; All tools = {all_tools,
  all_tools_required}.
- **`MECHANISM_GROUPS`**: baseline = {none}; context = {ast_compact,
  freq, cochange}; tool_free = {structural, temporal_frequency,
  temporal_cochange, all_tools}; tool_required = the four `_required`
  variants.
- `scripts/case_study_analysis.py` already applies `scorable_files()`
  filtering correctly (validated) — use it, don't hand-roll ground
  truth filtering.

## Key established entries (don't rediscover — extend or cross-reference)

- **#34**: dataset-wide garbled non-path `submit_answer` content
  (gpt-oss/DeepSeek concentrated, `_required`-concentrated).
- **#35**: Ministral-exclusive malformed tool-call *names* (call syntax
  jammed into the name field), 84/1620 (5.2%). Updated with a
  "name recovers, arguments stay empty" wrinkle (`localstack/9`).
- **#37**: `pandas/38` — a co-change relationship the fix commit itself
  *creates*, not one that predates it.
- **#38**: `pandas/38` — DeepSeek ignoring its own forced tool_choice.
- **#39**: `gpt-engineer/9` — map/tool presence triples a wrong file's
  inclusion despite real co-change signal not being the actual driver.
- **#40**: `scikit-learn/45` — GT file findable-in-map but conceptually
  irrelevant (docstring-only, from an unrelated giant PR).
- **#41**: `scikit-learn/45` — Ministral's `freq`-context miss,
  statistically confirmed at n=15 (Fisher's exact p=0.0063). Paired
  with `thefuck/20` in "Notes on use" as the same higher-variance-
  Ministral-trait cross-cutting note.
- **#42**: `stable-diffusion-webui/13` — traceback cascades into
  vendored/out-of-scope code; real answer is a ~99.9%-clone sibling
  file never named in the traceback.
- **#43**: `requests/12` — ground truth reflects a merged-then-reverted
  PR (new provenance category).
- **#44**: `requests/12` — gpt-oss touch-vs-kept gap (resolved) +
  DeepSeek's co-change content-gradient (still OPEN — first
  expanded-replication rep complicated it, not confirmed it).
- **#45**: `flask/18` — reporter's own diagnosis exactly right; 2nd GT
  file is pure docstring (3rd instance of the "ancillary ground-truth
  file" pattern — cross-ref `fastapi/9`, `pandas/44`, `requests/12`).
- **#46**: `flask/18` — strongest **directly-traced** (not inferred)
  positive map-content effect in the project: `lookup_structure`
  returns the exact fix line, Nemotron reads that offset next, 5/6
  trials. Mid expanded-replication-check.
- **#47**: `scrapy/26` — DeepSeek pads with a real code-adjacent wrong
  file in 36/36 trials, every condition, zero exceptions.
- **#48**: `scrapy/26` — quantified context-vs-tool efficiency contrast
  (fewer turns, higher output-tokens/turn under context); Nemotron
  explicitly narrates citing "the codebase map."
- **#49**: `localstack/2` — DeepSeek mechanism breakdown; updated once
  #50 was found to note only `ast_compact`'s advantage is
  content-explained (`cochange`'s isn't, despite recovering as well).
- **#50**: dataset-wide (6,480 trials) — `max_turns` recovery is
  near-binary on forced-final-answer **compliance**: gpt-oss 100%,
  DeepSeek 47%, Ministral 25%, Nemotron 19%. `flask/3` and
  `localstack/9` logged as confirming instances, not new entries.
- **#51**: gpt-oss auto-capitalizes the first path segment of its own
  submissions. Originally thought `thefuck`-specific (27/108) —
  **corrected** after `keras/9` found the same bug on an unrelated
  repo; full 45-issue scan: 36/1,620 (2.2%) gpt-oss trials dataset-wide,
  concentrated in exactly 3 of 15 repos (`thefuck` 28/108, `keras`
  5/108, `pandas` 3/144), zero elsewhere, zero for other 3 models.
- **#52**: `core/20` — Ministral localizes to the *exact* fix line, then
  reasons itself out of submitting ("external root cause" wrongly taken
  to mean "no source change needed"). New reasoning-policy category,
  distinct from touch-vs-kept and from malformed-submission bugs.
- **#53**: `requests/13` — Nemotron-exclusive malformed `submit_answer`
  **key** (not just content): `{"[\"files\"]": "..."}` shape, 10/6,480
  dataset-wide; one instance shows XML `<parameter>` tag bleed-through,
  suggesting a template artifact.

## Replication-check program (`scripts/run_replication_check.py`)

Separate track from the CSV/entry workflow above — expanded-rep tests
(n=15/cell) for specific (issue, model, condition) cells that looked
too clean/weird at n=3. Isolated results in
`/home/afb225/study1/replication_check_results` + `_logs` (native
machine), never touched by main-study analysis tooling. **The user runs
the actual batches themselves** in their own terminal(s) — I build/
validate the script, dry-run it, and can run short smoke-test trials
myself via Bash (confirmed working), but I don't run the full batches.

Targets configured so far (check current progress via file counts in
the isolated results dir, or ask):
- `keras/5` — 4 cond, all 4 models — was complete (192/192).
- `localstack/19` — 4 cond, all 4 models — was complete (192/192).
- `gpt-engineer/9` — ALL 12 cond, all 4 models — was in progress
  (283/576) last checked.
- `scikit-learn/45` — 2 cond (`none`/`freq`), Ministral only — complete
  (24/24), fed into #41's statistical confirmation.
- `requests/12` — 4 cond, DeepSeek only — complete (48/48) but stayed
  **open/unresolved** (first new rep contradicted the original
  gradient).
- `flask/18` — 4 cond (`none`/`ast_compact`/`structural`/
  `structural_required`), Nemotron only — launched by user; first
  smoke-test rep already broke the clean pattern on 2/4 conditions.
- `localstack/2` — ALL 12 cond, DeepSeek only — smoke-tested (12/12
  succeeded), launched by user, in progress.

When adding a new target: update the module docstring (new bullet),
`TARGET_ISSUES_CONDITIONS` + (if scoped) `TARGET_ISSUES_MODELS`, dry-run
with `--maps-base repo_maps` (local mirror), then run at least one real
smoke-test trial via native paths before calling it ready — confirm log
isolation stayed clean (`find logs/<model>/<repo>/<issue>` shows
nothing new besides pre-existing 2026-07-13-era `rep0.jsonl` artifacts,
if any) and results landed in the isolated tree.

## Other data gotchas worth remembering

- `data/map_position_metrics.csv` needs `token_offset`/`file_rank` cast
  to `.astype('Int64')` before `to_csv()`, or float-formatting artifacts
  (`10501.0`) reappear across the *whole* file, not just changed rows.
- `thesis_methodology_outline.md` and
  `notebooks/study_comparison_by_map_type.ipynb` are separate, unrelated
  threads — don't touch unless separately asked.
