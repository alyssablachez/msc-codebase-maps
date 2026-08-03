# Model Failure Points: Why Correct Files Go Unfound

A running catalogue of distinct failure modes behind incorrect file identification,
built up issue by issue through direct inspection of trial transcripts and logs
(not aggregate metrics). Each entry names the pattern, the evidence it's grounded
in, and — where relevant — whether it's a map/tool design limitation or a model
reasoning/behavior limitation, since those call for different fixes.

Add to this list as new issues are analyzed; don't prune old entries even if a
later issue seems to contradict one — the point is to build a taxonomy of *modes*,
not a single unified theory.

---

## 1. Stopped one hop short after finding a real, correct thread

**Type:** model behavior (under-exploration)

A trial follows a genuine, productive lead — reads a file that references the
actual fix location indirectly (e.g. a dispatch table pointing at compiled
functions) — but never takes the one additional search/lookup step that would
have closed the gap.

**Evidence:** `pandas/35`, DeepSeek-V4-Flash (`ast_compact`/rep1 and others).
Read `pandas/core/common.py`, which contains `import pandas.algos as algos` and
`_take_2d_axis0_dict = {..., algos.take_2d_axis0_int8_int8, ...}` — a direct,
searchable pointer to the real fix location (`pandas/src/generate_code.py`,
which generates those `algos.take_2d_axis0_*` functions). Across all 144 trials
for this issue, **zero** ever ran a `search` for `"take_2d"`, `"algos"`, or
similar, and none ever called `list_files` on `pandas/src/` at all.

---

## 2. Recency/salience bias overriding stronger earlier evidence

**Type:** model behavior (reasoning)

A trial actually opens and reads the correct ground-truth file directly, then
later encounters a weaker, coincidental piece of evidence for a different file
and submits that instead — effectively forgetting or discounting its own
strongest finding in favor of whatever it saw most recently.

**Evidence:** `pandas/35`, DeepSeek-V4-Flash, `study_1/ast_compact/rep1`. Turn 14:
reads `pandas/src/generate_code.py` (the ground truth) directly, having found it
via a targeted search. Turns 15–21: fails to verify against the compiled
`generated.pyx` (search misses, likely tooling gap). Turn 25: searches
`pandas/core/common.py` for `"writeable"` and gets 3 hits — which turn out to be
in an unrelated `scipy`-interpolation helper function, nothing to do with
`.iloc`. Submits `common.py` anyway. F1 = 0.0 on a trial that had the right
answer in context 11 turns earlier.

---

## 3. Literal-error-text search treated as a strategy, not recognized as futile

**Type:** model behavior (search strategy)

Some models repeatedly search for fragments of the exact exception message
rather than pivoting to code-symbol search, even though that text cannot appear
in the repo (it originates from the runtime/interpreter, not application code).

**Evidence:** `pandas/35`. The error `"buffer source array is read-only"` is
Cython's own internal buffer-protocol error text, confirmed absent from the repo
(`search` for the literal phrase returns "No matches found"). gpt-oss-120B and
especially Nemotron-3-Super's top search-query words for this issue are
dominated by `buffer`/`source`/`array`/`only`/`read` across every map type
(Nemotron: 130–154 total searches per condition, mostly this pattern), versus
DeepSeek-V4-Flash and Ministral-3B, whose top terms are real, present-in-repo
symbol names (`take`, `take_nd`, `_ixs`, `flags`, `writeable`). High search
volume did not correlate with productive search terms.

---

## 4. No mechanism to consult prior/linked issue history

**Type:** map/tool design gap (missing capability, not yet in this research)

An issue explicitly references a prior related issue by number, whose original
report contains information that would have made the fix nearly a one-shot
lookup — but nothing in the harness can retrieve linked/historical issues.

**Evidence:** `pandas/35`'s body opens with "This is picking up #9928 again."
Issue #9928's real traceback (fetched from GitHub for this analysis) names the
exact failing compiled function: `pandas.algos.take_2d_axis1_float64_float64`.
A single search for that name resolves directly to `pandas/src/generate_code.py`
(confirmed: the sibling search for `take_2d_axis0` did exactly this in trial
`ast_compact/rep1`). No trial had access to issue #9928's content at all.

---

## 5. Traceback-following stays within the crash's own call chain, never questions whether the root cause is upstream/disjoint from it

**Type:** model behavior (reasoning) + fundamental limitation of any code-structure map

When a full traceback is available, models search it thoroughly and accurately
— but every search stays inside the set of functions that appear *in* the
traceback, never considering that the actual defect might be causally upstream
of the entire failing call chain (e.g. bad state created earlier, at a time the
traceback never touches).

**Evidence:** `fastapi/17`. Every model's top search terms
(`get_model_name_map`, `get_flat_models_from_fields`, `get_model_definitions`,
`body_predict_predict__post`) are lifted directly and accurately from the
issue's own traceback — a highly productive, well-targeted strategy (up to 182
searches on this vocabulary for DeepSeek-V4-Flash). And yet across every
model/map-type, 119 of 122 wrong-file guesses land on exactly the three files
*in that traceback* (`fastapi/utils.py`, `fastapi/dependencies/utils.py`,
`fastapi/openapi/utils.py`) — never the true fix location, `fastapi/routing.py`,
whose relevant method (`include_router`) is never invoked during the failing
request at all (the bad state is created earlier, at app-setup time). No amount
of traceback-thoroughness reaches a bug like this; it requires abandoning the
traceback as the search boundary.

---

## 6. Retrieved statistical (co-change) evidence outranked by the model's own more "explainable" but wrong theory

**Type:** model behavior (evidence weighting)

The co-change tool is queried, returns the correct file ranked #1, and the
model still submits something else — specifically, something it can construct
a plausible causal story for, even when that story is wrong.

**Evidence:** `fastapi/17`, Co-change condition. In at least 8 trials across 3
models (Ministral ×3, gpt-oss-120B ×2, Nemotron-3-Super ×3), `lookup_cochange`
was called on one of the three "wrong-guess" files and returned `routing.py`
ranked #1 or #2 (e.g. "`fastapi/routing.py (25 co-changes)`" at the top of the
list). Every one of these trials still submitted a different file. Ministral's
`all_tools/rep1` trial (the one case that *did* submit `routing.py` correctly)
did so despite its own final stated reasoning pointing at a *different* file
(`dependencies/utils.py`) — suggesting the submission step isn't always a
faithful readout of the model's own analysis, in either direction.

**Map implication:** the co-change tool returns a bare ranked list of counts
with no explanation of *why* files co-change. A model with a competing,
mechanistically-explainable (if wrong) theory from the traceback appears to
default to what it can explain over what it can't, even when the latter is
correct. Enriching co-change results with the actual commit messages behind the
shared-commit count (turning "25 co-changes" into "...most recently in a commit
titled 'Fix duplicate route entries in include_router'") is an untested but
plausible fix, since it would give the correlational signal a stated mechanism
to compete with the model's own theory on equal footing.

---

## 7. Per-file co-change truncation can structurally hide a real, secondary relationship

**Type:** map/tool design limitation (confirmed data artifact, not model behavior)

The co-change map/tool caps each file's returned partner list (observed: top-3
in the raw map file, top-`k` configurable in the tool but still bounded). A
real, correct relationship can be a file's *rarer* partner's dominant link while
never cracking the *dominant* file's own top-N, making it invisible from the
"obvious" direction.

**Evidence:** `pandas/35`. `generate_code.py`'s own entry lists `common.py` as
its #1 partner (26 shared commits) — but `common.py`'s own top-3 partners are
`frame.py` (161x), `series.py` (130x), `internals.py` (95x), burying
`generate_code.py`'s 26x well outside view. A model querying co-change for
`common.py` (the file it was already examining) would never see
`generate_code.py` surface; the link is only visible by querying
`generate_code.py` itself, which requires already suspecting it exists.
Contrast with `fastapi/17` (failure point #6), where the same tool's per-file
cap did *not* hide the link — `routing.py` happened to be prominent from every
queried direction. Whether the link survives truncation appears to depend on
the underlying co-change graph's shape for that specific file pair, not
anything tunable within a single issue.

---

## 8. Root cause requires information entirely outside the repository (no source-code-derived map can express it)

**Type:** fundamental limitation, not fixable by better maps of the code alone

Some bugs are really "the library should defend against a misuse pattern that
happened in code the study never has access to." No structural, frequency, or
co-change signal computed over the target repo's own source can explain *why*
a defensive fix belongs at a given location, because the necessitating
condition never appears in that repo at all.

**Evidence:** `fastapi/17`. The real GitHub issue thread establishes the actual
trigger: the reporter had declared two `APIRouter` objects with the same
variable name in two different files of *their own application*, both
eventually `include_router()`'d, causing a duplicate `Route` object to silently
enter `self.routes`. That triggering code is not part of the fastapi repository
under study and never was. The fix (`routing.py`, a guard against re-adding an
already-present route) is a defensive measure against a *class* of external
misuse, not a bug reachable by reasoning about fastapi's own internal logic.
The one thing that did work, in the real world, was a human commenter linking
three *other* historical issues reporting the same symptom (see failure point
#4's map-tool gap, and the broader case for an issue-similarity search tool
made in conversation on 2026-08-02) — this is categorically outside anything a
source-code map could ever provide.

---

## 9. Final submission can be disconnected from the trial's own stated reasoning

**Type:** model behavior (unclear cause — possibly a harness/prompting effect)

At least one case shows a model's own final reasoning turn explicitly naming
one file as needing the fix, then submitting a *different* file in the same
turn, with no stated justification for the switch.

**Evidence:** `fastapi/17`, Ministral-3B, `all_tools/rep1`, turn 12: reasoning
text says *"we need to modify the `get_body_field` function [in
`fastapi/dependencies/utils.py`]..."*, immediately followed by
`submit_answer(files=['fastapi/routing.py'])`. This happened to be the *correct*
file (its own diagnosis was wrong), but the mismatch itself — not just the
lucky outcome — is worth tracking, since it suggests submitted answers cannot
always be taken as a faithful proxy for a trial's actual reasoning, in either
direction. Needs more cases before drawing a firm conclusion about cause (turn
budget pressure? a formatting/parsing quirk between reasoning and tool-call
generation?).

---

## 10. Correct file already in context; failure is almost entirely at the commit/decision step, not retrieval

**Type:** model behavior (decision-weighting) — explicitly *not* a map/tool gap

The clearest case yet that having the right file in context is not sufficient.
Retrieval essentially already succeeds, independent of which map (if any) is
available; the bottleneck is a late-stage default toward the file that
literally appears in the crash traceback, overriding whatever was just read.

**Evidence:** `thefuck/20`. `thefuck/shells/fish.py` was read in full (including
the exact lines containing `how_to_configure()`, the true fix location) in 106
of 144 trials — 74%, and this holds even under the **baseline "none"**
condition with no map or tools at all. Despite that, only 3 trials ever
submitted it; the other 103+ read it and still submitted
`thefuck/entrypoints/not_configured.py` (the file where the exception fires) or
nothing. The structural map independently lists `how_to_configure(self) L72`
by name with a line number — confirmed present, confirmed never searched for
by any trial across the whole issue.

**A proposed fix considered and retracted on verification.** Initial read of
the 3 successful trials' reasoning suggested they'd noticed `Fish` doesn't
override `get_history()` the way it overrides other `Generic` methods, and an
"interface-conformance map" (surfacing which base-class methods a subclass
does/doesn't override) was floated as something that could make this kind of
signal explicit rather than requiring a model to reconstruct it by reading two
files side by side. Checking `thefuck/shells/generic.py` directly killed this
idea: `Generic.get_history()` is a deliberate template method that delegates
to three small hooks (`_get_history_file_name`, `_get_history_line`,
`_script_from_history`) — subclasses are *meant* to leave `get_history()`
alone and override the hooks instead, which `Fish` does, correctly, for all
three. There is no missing override; an interface-conformance map would (accurately)
report full conformance and flag nothing. The 3 successful trials' theory
("Fish doesn't properly handle history") was technically wrong even though it
scored correctly at the file level, for the same reason as failure point #9 —
file-level scoring doesn't require correct mechanism, just landing on the file
that happens to own whatever's fish-specific.

**What the bug actually is, and why no code map reaches it:** `Fish`'s Python
code does exactly what it should — read `~/.config/fish/fish_history` and
parse whatever's in it. The real defect is a runtime fact about the **fish
shell binary itself**: commands run via `eval (...)` (the old alias-setup
instructions `how_to_configure()` returned) don't get written to that history
file the way normally-typed commands do. That's external program behavior,
not a structural property of this repository, so no AST/call-graph/co-change/
interface-conformance map computed over the codebase could surface it — there
is nothing in the code to point at. This sits in the same "requires
information outside what any code-structure map can express" bucket as
failure point #8, just via a different route: #8's missing information was in
another (user) codebase; this one's is in the runtime behavior of an external
program neither codebase contains.

---

## 11. Frequency map showed a clear, sizable margin for the correct file — still unused, and the tool version can't even surface it

**Type:** map/tool design limitation + model behavior (evidence weighting)

A second confirmed instance (alongside failure point #6's co-change finding,
same issue) of a map signal that was prominent, correct, and either ignored or
structurally unreachable depending on delivery mechanism.

**Evidence:** `fastapi/17`. In the frequency map (42 files total, ranked by
historical edit count), `fastapi/routing.py` sits at rank 2/42 with 109 edits —
excluding `fastapi/__init__.py` (rank 1, 159 edits, an import-aggregator file
not a plausible fix candidate), `routing.py` is the most-edited real
implementation file in the repo, by a real margin: 53% more edits than
`fastapi/dependencies/utils.py` (71), 95% more than `fastapi/openapi/utils.py`
(56), and 2.6x more than `fastapi/utils.py` (42) — the three files every model
kept wrongly submitting instead. Under **"Map as context"** (`freq` condition),
this entire ranked list is injected directly into the system prompt, so
`routing.py`'s rank and edit count are passively visible without any query —
and models still predominantly submitted one of the three wrong files (Frequency
column, wrong-guesses grid: 37 wrong predictions pooled across models).

**A structural asymmetry with the co-change tool, worth keeping distinct.**
Under **"Map as tool"** (`temporal_frequency`/`temporal_frequency_required`),
checked every trial's `lookup_frequency` calls directly: the tool is a
single-file lookup only (`lookup_frequency(path)` → that file's own edit
count and last-edit date), confirmed from its own tool description in
`harness/run_trial_temporal_frequency.py`: *"Look up how many historical
commits have touched **a file**..."* — it cannot return a ranked list of most-
active files the way `lookup_cochange` returns a ranked list of partners.
Every queried trial called it only on the three wrong-guess files (`utils.py`,
`openapi/utils.py`, `dependencies/utils.py`), never on `routing.py` itself —
which makes sense, since discovering `routing.py`'s high rank via this tool
requires already suspecting `routing.py` enough to query it by name. So unlike
co-change (failure point #6: signal retrieved and ignored), the frequency
*tool* variant never had a chance to surface the signal at all — it's a
narrower, single-file instrument bolted onto a map that was actually built as
a ranked list. The **context** variant doesn't have this limitation (the whole
ranked list is present passively) and still didn't help, which isolates the
"ignored despite being shown" failure mode from the "tool can't show it in the
first place" one within the same issue.

---

## 12. Co-change signal retrieved and correct, again — this time for a second ground-truth file in a multi-file fix

**Type:** model behavior (evidence weighting) — third confirmed instance of #6's pattern

For multi-file ground truth, co-change can point from the *one* file a trial
actually finds toward *another* correct file it would otherwise never reach —
and, consistent with failure points #6 and #11, having that signal delivered
directly did not change the outcome.

**Evidence:** `keras/12` (ground truth: 5 files; see bug/fix explanation
above). Across all 144 trials, **`keras/engine/training.py` was the only
ground-truth file any model ever correctly identified** (27 total hits,
concentrated in DeepSeek-V4-Flash), and the dominant wrong guess by far was
`keras/utils/io_utils.py` (123 of 125 wrong-file predictions — a plausible
name for "HDF5 file I/O" that isn't part of the actual fix at all).
`training.py`'s co-change map entry lists `keras/models.py` as its #1 partner,
33 shared commits, well ahead of `#2 topology.py` (26) — a strong, mutual link
(`models.py`'s own top-3 lists `training.py` back at #2, also 33x). Checked
every Co-change-condition trial's `lookup_cochange` calls directly: in 3
trials (gpt-oss-120B `temporal_cochange_required`/rep1, DeepSeek-V4-Flash
`temporal_cochange_required`/rep1 and rep3), the model queried co-change on
`training.py` and got `keras/models.py (33 co-changes)` back as the top
result. None of the 3 ever added `models.py` to their submission — two kept
`training.py` alone (partial credit, F1=0.286) and one dropped even that.

**Why this one is a clean, low-ambiguity case for the "map already worked"
claim**: unlike failure point #7 (where co-change's per-file truncation could
plausibly have hidden a weaker link), this is a mutual, symmetric, clearly
top-ranked relationship visible from *either* direction, retrieved into
context via the same tool call that also confirmed the trial's own (correct)
`training.py` guess. There's no data-availability excuse here — the same
`lookup_cochange` response that validated one right answer contained the next
one, unused.

**A third case, `localstack/19`** (ground truth: 7 files; see bug/fix
explanation above): `localstack/services/infra.py`'s co-change entry lists
`localstack/constants.py` (30x) and `localstack/plugins.py` (24x) as its top
two partners — both ground-truth files, both a real, dominant-strength link
(not a weak tied-for-third one), and **neither was ever found by any model in
any condition**. `DeepSeek-V4-Flash / temporal_cochange_required / rep1`
queried `lookup_cochange` on both `persistence.py` and `infra.py` directly,
meaning it saw `constants.py (30x)` and `plugins.py (24x)` ranked at the top
of the result — and still submitted only `persistence.py`, `config.py`,
`infra.py`, never adding either. Same issue also has a second, weaker
instance of the pattern worth noting for contrast: `persistence.py`'s
co-change entry lists `services/s3/s3_listener.py` at a modest 4x (tied for
2nd/3rd place, not dominant, and one-directional — `s3_listener.py`'s own
top-3 doesn't list `persistence.py` back), so that link is more like failure
point #7's truncation-hides-a-weak-link story than this entry's core pattern.
The `infra.py` → `constants.py`/`plugins.py` link is the clean case: strong,
retrieved, ignored.

---

## 13. Technically sound diagnosis of a real contributing cause, not extended far enough to reveal it wouldn't actually fix the reported case

**Type:** model behavior (reasoning depth) — a new subtype, distinct from every
prior entry: the file guess here is *not* a shallow name-match or a
traceback-anchoring default, it's a genuine, independently-reasoned piece of
domain engineering that happens not to be what got merged.

Unlike the other entries, this isn't "evidence was available and ignored" or
"the model anchored on the wrong file for a shallow reason." Here the model
did real, correct-as-far-as-it-goes technical reasoning, converged on it
confidently and repeatedly, and never took the next step of checking that
reasoning against the specific numbers given in the issue — which would have
exposed its limits.

**Evidence:** `keras/12`. `keras/utils/io_utils.py` is the dominant wrong
guess (123 of 125 wrong-file predictions) — but it is not a superficial
name-match: `HDF5Matrix`, the exact class named in the issue, is genuinely
defined there in full. 53 of 144 trials (DeepSeek-V4-Flash especially, nearly
every condition) independently traced the real call chain from `training.py`'s
batch-slicing logic into `HDF5Matrix.__getitem__` and correctly identified
that passing a **list** of indices triggers h5py "fancy indexing," which is
genuinely slower than contiguous reads for HDF5-backed data — e.g. (verbatim):
*"This forces h5py to use fancy indexing... element-by-element."* That's a
real mechanism, not a hallucination.

**What none of these trials did**: reconcile that diagnosis against the
issue's own stated workload — 20 million rows, batch size 10,000, and Keras'
`shuffle=True` default. With batch indices drawn uniformly at random across
20M rows, a batch of 10,000 would span nearly the *entire* file, which defeats
the standard mitigation for this exact problem (read one contiguous bounding
slice, then fancy-index in memory) — that trick only pays off when indices
are clustered, and here they're maximally scattered by construction. Had any
trial done that arithmetic, it would have surfaced the real reason the
maintainer's own reply steers toward a different kind of fix entirely
(parallel background prefetching, which hides blocking I/O behind compute
regardless of access pattern, rather than trying to make each read faster) —
see the bug/fix explanation given in conversation on 2026-08-02. No trial's
transcript shows this reconciliation step; the diagnosis stopped at "fancy
indexing is slow," never advancing to "and here's why that specifically
doesn't scale for this reporter's numbers, so a different class of fix is
needed."

**Why this is worth tracking separately**: it shows these models *can*
produce real, defensible engineering analysis when the issue gives them
enough concrete technical detail to reason from (contrast with the other
three issues, which are crash-traceback-following cases) — but confident,
correct-as-far-as-it-goes reasoning stopped short of testing itself against
the problem's own stated constraints, which is what would have been needed to
recognize the fix belonged elsewhere. Also a genuine complication for scoring:
this may be a technically valid alternative diagnosis of the same real
symptom, not a mistake in the usual sense — worth remembering as a caveat on
this issue specifically, separate from the reasoning-depth pattern itself.

---

## 14. Condition-level success correlated with a map, but individual trials show the map wasn't the actual cause

**Type:** methodological caution, not a model-behavior failure — a warning
about reading aggregate tables causally

Aggregate mean-F1-by-condition tables can look like they show a map helping
when the underlying trials tell a completely different story. Worth checking
before citing any condition-level correlation as evidence of map usefulness.

**Evidence:** `yt-dlp/41`. Mean F1 by condition: `none` (baseline) 0.056,
`ast_compact` (structural, context) 0.000, `freq` (frequency, context) 0.167,
`temporal_frequency` (frequency, tool) **0.206** — the best of all 12
conditions — `cochange` (context) 0.100, `temporal_cochange_required` 0.192.
Read as a table, this looks like clear evidence frequency and co-change maps
help substantially over baseline and over structural. Checking the actual
trials behind those numbers tells a different story:
- `gpt-oss-120B / freq(context) / rep3` (perfect, F1=1.0): no reasoning text
  references frequency data at all.
- `Nemotron-3-Super / temporal_frequency(tool) / rep3` (perfect, F1=1.0):
  **`lookup_frequency` is never called once** across the full 28-turn
  transcript. Found `options.py` at turn 5 via plain `read_file`, reached by
  searching literal issue-text strings (`list-auto-subs`, `automatic
  caption`, `list-subs`).
- `Ministral-3B / temporal_frequency(tool) / rep1`: same — no
  `lookup_frequency` call anywhere; found via searching `write-auto-subs`,
  `writeautomaticsub`, `ytdl-raw-options`.
- `gpt-oss-120B / temporal_cochange_required / rep1` (perfect, F1=1.0) — the
  one case that *did* call a map tool (`lookup_cochange` at turn 10) — but
  `options.py` was already read at turn 6 via plain search; the co-change
  call is a confirmatory check on an already-found candidate, not how it was
  discovered.
- One **baseline** trial (`gpt-oss-120B / none / rep1`, no map/tools at all)
  also scored nonzero (F1=0.667) via the identical plain-search strategy,
  showing the map isn't even necessary for this level of success.

**Why this happened here specifically**: `yt-dlp/41` (see the bug/fix
write-up in conversation on 2026-08-02) has no real bug or fix behind it — the
ground truth is a file containing CLI flag *definitions* that the issue's own
text names almost verbatim (`--write-auto-subs`, `--write-subs`), so it's
directly reachable by searching literal issue vocabulary regardless of which
map is or isn't available. That makes this an easy case for the
condition-level noise in a 12-trials-per-cell design to look like signal.
Worth treating any single condition-level correlation table (here or
elsewhere) as a hypothesis to verify against actual trial transcripts before
citing it as evidence a map helped, not as evidence on its own.

---

## 15. Correct file found almost immediately, then discarded for looking too trivial to be a real answer

**Type:** model behavior (reasoning) — a new subtype: not under-exploration,
not a coincidental red herring, not traceback-anchoring, but rejecting a
correct answer because it doesn't *look* like what a "fix" is expected to
look like.

**Evidence:** `fastapi/20` (ground truth: `fastapi/background.py`, which is
one line — `from starlette.background import BackgroundTasks as
BackgroundTasks  # noqa`, a pure re-export with no logic of its own; see the
bug/fix explanation given in conversation on 2026-08-03). Checked every trial
directly: of 144 total, **85 touched `background.py`** (read it or looked it
up via `lookup_structure`/`lookup_frequency`/`lookup_cochange`), and of those
85, only **19 (22%) kept it in their final answer — 66 (78%) read it and
abandoned it anyway.** It's found early, not as an exhausted-search fallback:
DeepSeek-V4-Flash touches it at turn 1-2 in nearly every one of its 36
trials.

A representative walkthrough (`DeepSeek-V4-Flash / structural / rep1`, F1=0.0,
final answer `routing.py`+`applications.py`): turn 2, `lookup_structure` on
`background.py` directly; turn 3, reads the whole (one-line) file; turns 4-6,
searches for `BackgroundTask`/`BackgroundTasks` — the exactly correct concept.
Then 25 more turns (83% of the trial) exploring `routing.py`, `applications.py`,
`middleware/__init__.py`, ASGI `__call__`/`send`, `build_middleware_stack`,
never returning to the file it opened at turn 3.

**The model-level split is the sharpest evidence of a real, stable pattern
rather than noise**: checked touch-vs-kept rates per model across all 144
trials --

| Model | Touched | Kept | Rate |
|---|---:|---:|---:|
| gpt-oss-120B | 21 | 0 | **0%** |
| Nemotron-3-Super | 20 | 0 | **0%** |
| Ministral-3B | 8 | 3 | 37.5% |
| DeepSeek-V4-Flash | 36 | 16 | 44% |

gpt-oss-120B and Nemotron-3-Super touch the correct file a combined 41 times
across this issue and **never once** keep it — a completely consistent
pattern across every map condition for both models, not a fluke on one or two
trials. DeepSeek converts a touch into a kept answer nearly half the time.
Since the file's one-line triviality is identical regardless of condition,
this reads as a stable, model-specific disposition -- gpt-oss-120B and
Nemotron appear to share some prior that "a real fix must contain real logic"
that Ministral and especially DeepSeek don't hold as strongly.

**Map implication**: none of the three map types caused or prevented this --
the abandonment rate is consistent across structural/frequency/co-change and
even baseline. This is a case where the map did its job (or wasn't even
needed, since the file is found via generic exploration in most touches) and
the failure is entirely downstream, in whether the model trusts a minimal
answer.

---

## 16. First candidate case of a map actively helping -- via interpretive framing, not new information

**Type:** positive finding (tentative) -- the first entry in this list where a
map plausibly *helps*, included deliberately alongside all the negative
findings above, since the point of this list is failure modes but a
one-sided list would be misleading about what the maps do overall.

**Evidence:** `localstack/19` (ground truth includes `localstack/utils/
persistence.py` and `localstack/services/infra.py`; issue body is one
sentence: *"We should document our roadmap for extended data persistence...
persistent state is only supported for a few of the services."*).
DeepSeek-V4-Flash's three **baseline** (no map, no tools) trials all submit
the identical wrong answer: `doc/roadmap/README.md` -- a documentation file,
scored 0 by the `scorable_files()` filter regardless of exploration quality.
Checked the transcripts directly: this isn't from failing to explore --
DeepSeek reads `localstack/utils/persistence.py` and `localstack/services/
infra.py` in every one of these baseline trials, the exact two files it
later gets credited for finding under map conditions. It does the right
exploration and then answers the issue's *surface wording* ("document our
roadmap" reads as a documentation task) rather than what the real PR actually
changed (source code). Under structural/frequency/co-change conditions, the
same read-persistence.py-and-infra.py exploration instead ends in a correct
source-file submission -- explored content barely changes, but the framing at
submission time does.

**Proposed mechanism**: a map's presence in the system prompt -- structural,
frequency, or co-change, delivered as context or as a tool description --
puts the codebase's actual files/classes/functions front and center from
turn one. That plausibly anchors the whole trial around "this is a
source-code navigation task," overriding a literal reading of an ambiguous,
documentation-flavored issue title that (in baseline) leads the model to
answer with a documentation file instead. If real, this is a case of a map
helping through *interpretive framing* rather than through supplying
information the model didn't already have access to via ordinary
exploration -- a mechanism distinct from anything else in this list.

**Caveats, stated plainly**: single model (DeepSeek-V4-Flash), single issue,
n=3 baseline reps. Worth checking whether this generalizes -- to other
models on this issue (gpt-oss-120B and Nemotron mostly abstain entirely here
regardless of condition, so they can't show this pattern either way), and to
other issues with similarly ambiguous/documentation-flavored titles -- before
treating it as more than a suggestive first case.

---

## 17. `base_commit` bug: two issues have the fix commit's own hash as their "pre-fix" starting point

**Type:** data/methodology defect (severe) — not a model-behavior finding at
all; every trial run against these two issues explored an already-fixed
codebase, which undermines the entire "find what needs to change" premise
for both. Flagged as an actionable item, not just an observation.

**How it was found**: investigating why search terms for `thefuck/10`
included the real fix's exact, non-obvious vocabulary
(`excluded_search_path_prefixes`, `include_path_in_search`) even though
neither appears anywhere in the issue text. Checked a real trial's actual
`read_file` output (not just the map) for `thefuck/utils.py` — the fix code
was already there, verbatim, at turn 3 of `DeepSeek-V4-Flash / none / rep1`.
Traced this to `base_commit` in `data/issue_selection_final.csv` being
**identical to the real fix commit's own hash**
(`6da0bc557f0fd94ea1397d3a7f508be896cc98d8`) rather than its parent.

**Confirmed the correct value**: the immediate parent,
`1a595f1ba23843823037479d0caede926b0bd752` (2021-04-17, 4 days before the
fix) — verified `include_path_in_search` is genuinely absent from
`thefuck/utils.py` at that commit, unlike at the recorded `base_commit`.

**Systematically audited all 45 issues in `issue_selection_final.csv`** for
the same defect (comparing each row's `base_commit` against the underlying
MULocBench pickle's `commit_html_url` for a matching hash) and found a
**second, independently confirmed case**: `stable-diffusion-webui/5`
("Sort items by date by default"). `base_commit`
(`d9499f4301018ebd2977685d098381aa4111d2ae`) is the actual fix commit, which
touches exactly the 3 ground-truth files
(`modules/shared_options.py`, `modules/ui_extra_networks.py`,
`javascript/extraNetworks.js`). Correct parent:
`16ab17429016a1154b9aa83244cdbfc7ba463d72` ("eslint", same day, just before).

**Root cause**: the underlying MULocBench pickle
(`data/all_issues_with_pr_commit_comment_all_project_0922.pkl`) records
`base_commit` equal to `commit_html_url`'s hash for both of these two
records — the defect appears to originate upstream in that source dataset,
not in this project's own extraction pipeline, which inherited it into
`issue_selection_final.csv` without a check that would catch a
self-referential base/fix commit pair.

**Action item**: re-run all 12 conditions × 4 models × 3 reps for these two
issues (`thefuck/10`, `stable-diffusion-webui/5`) with the corrected
`base_commit` values above before drawing any conclusions from their
existing results — current scores for both are measuring something other
than intended (models exploring already-fixed code, not localizing a real
bug). Worth re-running the same audit query if `issue_selection_final.csv` is
ever regenerated or extended with more issues from the same source pickle.

---

### Notes on use

- Failure points are not mutually exclusive — a single trial can exhibit
  several at once (e.g. `pandas/35`'s DeepSeek trial shows both #1 and #2).
- "Type" tags exist to separate what a better map/tool could plausibly fix
  from what's a model-side reasoning issue, since those need different
  remedies in any recommendations section.
- Eight issues analyzed so far (`pandas/35`, `fastapi/17`, `thefuck/20`,
  `keras/12`, `yt-dlp/41`, `fastapi/20`, `localstack/19`, `thefuck/10`);
  intentionally kept broad and issue-specific rather than prematurely
  generalized — revisit once a handful more issues are logged here to see
  which patterns recur. Entry #17 additionally identified a second affected
  issue (`stable-diffusion-webui/5`) via a full audit of all 45 issues in
  `issue_selection_final.csv`, not from separate deep-dive analysis — that
  issue's own detailed notes/failure entries are still outstanding.
  The co-change-retrieved-and-ignored pattern (#6, #12) has now recurred
  across three separate issues (`fastapi/17`, `keras/12`, `localstack/19` —
  the latter two both folded into entry #12) and is the strongest repeat
  candidate for calling a real, general finding rather than an
  issue-specific quirk. Note
  `yt-dlp/41` and `fastapi/20` both have no genuine bug/fix behind them
  (confirmed via the underlying MULocBench annotation itself, which flags
  both as not really countable — `loc_way: 'comment'`, no linked PR/commit)
  — their entries (#14, #15) are about evaluation methodology and model
  decision-making under a trivial/minimal correct answer, not classic
  bug-localization reasoning failures, and should be read a little
  differently from the other four issues' entries. Entry #16
  (`localstack/19`) is the first entry in this list where a map plausibly
  *helps* rather than fails — kept deliberately alongside the negative
  findings so the list doesn't read as one-sided about what maps do.
