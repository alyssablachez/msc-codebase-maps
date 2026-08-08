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

**A second, noisier variant confirmed on `keras/5`** (see the bug/fix
explanation given in conversation on 2026-08-03): the reported error
there, `"TypeError: float() argument must be a string or a number, not
'dict'"`, is Python's own builtin `float()` message, equally absent from
the repo. But unlike `pandas/35`'s Cython text -- distinctive enough
that a literal-phrase search cleanly returns zero matches -- searching
the single word `float` (what models actually query, not the full
phrase) returns a flood of real, irrelevant hits, since it's a ubiquitous
token in any numerical library. `float` dominates first-search behavior
for gpt-oss-120B (100% of trials), Nemotron-3-Super (88.9%), and
DeepSeek-V4-Flash (75%), tracking closely with final F1 ranking;
Ministral-3B (16.7%) is the outlier and has the best score on this
issue. The failure texture differs from the original case: not an
obvious, immediately-abandoned dead end, but a noisy trap that can
plausibly encourage repeated variations rather than quick abandonment,
since each query looks like it's "finding something."

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

## 18. Correct file touched at a 0% keep rate, including a case that searched the exact right function name and never read it -- and a real, model-consistent gap between delivery mechanisms (not map types)

**Type:** model behavior (decision-weighting) -- most extreme instance yet
of the "retrieval succeeds, commitment fails" pattern (failure points #10,
#15), plus a new, cleanly-isolated finding about *which* delivery mechanism
drives exploration toward the right file.

**Evidence:** `pandas/44` (ground truth: `pandas/core/indexing.py`, a
one-line-ancillary-import file like `fastapi/20`'s `background.py`, and
`pandas/tseries/index.py`, where the real fix -- a missing `elif reso ==
'second'` branch in `DatetimeIndex._partial_date_slice` -- actually lives;
see the bug/fix explanation given in conversation on 2026-08-03). The wrong-
guess grid is dominated by `pandas/core/frame.py` (99 of 111 wrong guesses,
89%) -- the exact file/method (`__getitem__`) named in the issue's own
traceback. **38 of 144 trials touched (read or looked up)
`pandas/tseries/index.py` -- the real fix file -- and 0 of them ever kept
it in the final answer.** A 0% conversion rate, more extreme than
`fastapi/20`'s 22% (failure point #15). Entirely concentrated in
DeepSeek-V4-Flash (30 touches) and Ministral-3B (8); gpt-oss-120B and
Nemotron-3-Super never touch it once.

**Sharper than a simple "read it, discarded it" case**: checked
`DeepSeek-V4-Flash / structural / rep3` in detail. Turn 9 reads
`_get_string_slice()`, which literally calls
`self._partial_date_slice(reso, parsed, ...)` -- the buggy function, by
name, in the code it just read. Turns 10 and 19 read the neighboring
`get_value`/`get_loc` methods. **Turn 24 explicitly searches
`'def _partial_date_slice'` in `pandas/tseries/index.py` and gets a
location hit** -- the model typed the exact correct function name into a
search query. No `read_file` call at that offset follows anywhere in the
remaining 5 turns; the trial pivots back to `indexing.py`/`internals.py`
and submits `frame.py` + `indexing.py` (F1=0.5). This is one hop short of
even failure point #1's pattern (`pandas/35`, which never searched the
right term at all) -- here the right term *was* searched, and the model
still didn't take the one further step of reading what it found.

**Checked whether map type or delivery mechanism explains the touch rate --
it's the mechanism, not the map.** Touch rate by map type is flat and
undifferentiated: Structural 28%, Frequency 31%, Co-change 25%, All tools
21% (10/36, 11/36, 9/36, 5/24) -- no map type stands out. Touch rate by
*delivery mechanism*, pooled across the three individual map types, is a
real, monotonic step: context 22% (8/36) < tool_free 23% (11/48) <
tool_required 33% (16/48). Verified this holds per-model, not just pooled:

| Model | baseline (none) | context | tool_free | tool_required |
|---|---|---|---|---|
| Ministral-3B | 0/3 (0%) | 1/9 (11%) | 2/9 (22%) | 3/9 (33%) |
| DeepSeek-V4-Flash | 3/3 (100%) | 7/9 (78%) | 8/9 (89%) | 9/9 (100%) |

For Ministral, baseline truly is the floor and the progression is fully
monotonic (0% -> 11% -> 22% -> 33%). For DeepSeek it isn't: baseline ties
`tool_required` at 100% and is *higher* than `context` (78%) -- passively
injecting a map into the system prompt appears to make this specific,
already-thorough-explorer model explore *less* broadly than giving it
nothing at all, plausibly by signaling "you already have enough
information," while being required to call a lookup tool restores (but
doesn't exceed) its no-map exploration thoroughness. Baseline is a noisier
comparison than the other three points (n=3 vs. n=9 pooled per model), so
trust the direction more than the exact percentages.

**Bottom line, stated plainly**: Study 3's submit-gate mechanism
demonstrably works at its stated job -- DeepSeek touches the correct file
in 100% of required-condition trials, a perfect 9/9 -- and it does nothing
whatsoever for the decision made once there, since the keep rate is still
0% even at that ceiling. "Make the model look at more things" and "make
the model use what it looked at" are separate problems; the gate only ever
solves the first one.

---

## 19. Identical basename in a different directory creates the most one-sided wrong-guess dominance seen yet

**Type:** model behavior (search/disambiguation) — a new subtype, distinct
from "plausible name match" (#13) and "traceback-named file" (#5, #10):
here the wrong file isn't merely *similarly* named, it has the exact same
filename as the correct one, one directory up.

**Evidence:** `scrapy/48` (ground truth: `scrapy/commands/shell.py` and
`scrapy/utils/url.py` — see the bug/fix explanation given in conversation
on 2026-08-03). `scrapy/shell.py` (the `Shell` class that drives the
interactive console) and `scrapy/commands/shell.py` (the CLI command that
parses `scrapy shell <url>`'s arguments) share an identical basename.
Across all 144 trials, `scrapy/shell.py` was submitted **101 times (70%)**
— the dominant wrong answer by a wide margin — versus 33 (23%) for the
correct `scrapy/commands/shell.py`. This is the most one-sided wrong-guess
concentration recorded in this list to date on a *single* competing file
(contrast `pandas/44`'s `frame.py`, 89% of *wrong guesses* but a
traceback-named file, a different mechanism per #5).

**Why this is worth separating from #13's `keras/utils/io_utils.py`
case**: `io_utils.py` was plausible because it genuinely contains the
class named in the issue (`HDF5Matrix`) — a content-level match. Here
there's no comparable content hook; the two `shell.py` files draw
confusion from the filename match alone, which any tool or map indexing
files by basename-first (or any model skimming a directory listing) is
structurally prone to conflating.

**Revised mitigation** (an earlier draft of this entry proposed "always
show full paths, not basenames" — checked and retracted: every map type
here already displays full relative paths, `scrapy/shell.py` vs.
`scrapy/commands/shell.py` are never truncated to bare basenames
anywhere in the delivered maps, so that alone doesn't explain the
confusion or fix it). What actually distinguishes the two files is
control flow, not naming: `cmdline.py` → `commands/shell.py::run()` is
the true CLI entry point, the first code to touch the raw argument;
`shell.py::fetch()` only runs afterward, once `run()` has already
decided what to do with the URL. A call graph rooted at the actual entry
point — showing which file is reached *first* from where user input
enters the program — would give a structural reason to prefer the
entry-point file over its same-named sibling, something none of
structural/frequency/co-change encode (see entry #21's `best_map_potential`
conclusion for `scrapy/48`, revised in conversation on 2026-08-03: none
of the three existing map types is really the answer for this issue).

---

## 20. Chasing a real symbol whose definition lives outside the repository entirely

**Type:** model behavior (search strategy) — a new subtype, distinct from
#3: #3's searched text (a Cython runtime error message) could never exist
in any repo; here the searched symbol is real, genuinely used, and
findable via `import` — it's just not *defined* in the target repository.

**Evidence:** `scrapy/48`. `scrapy/shell.py`'s `Shell.fetch()` calls
`any_to_uri(request_or_url)`, imported from the external `w3lib` package.
`any_to_uri` dominates search vocabulary across **every single
model×map-type cell** in this issue (683 total hits across all trials,
more than 2x the next-highest term `shell` at 137) — not a map-specific
or model-specific artifact, a constant. Checked one representative trial
in full (`DeepSeek-V4-Flash / none / rep2`, baseline): it reads
`scrapy/utils/url.py` in full at turn 12 and even searches the literal
string `add_http_if_no_scheme` — the real fix's exact function name —
early in the trial. Getting no match (correctly, since the function
doesn't exist pre-fix), it pivots to hunting `any_to_uri`'s definition
instead, escalating across 15+ further searches into `/usr`,
`/usr/local/lib`, `/usr/lib/python2.7`, and site-packages paths, each
returning `"Error executing search: path '...' escapes the repository
root"`. The trial exhausts its turn budget this way and is forced to
submit `['scrapy/shell.py']` alone.

**Map implication**: no map type addresses this — structural, frequency,
and co-change maps are all repo-scoped by construction, so none can
signal "this symbol is external, stop looking for it here." A cheap,
targeted fix would be for the `search` tool itself to short-circuit with
a distinguishing error (e.g. "not found in repository; `any_to_uri` is
imported from `w3lib`, an external dependency") the first time a search
resolves to an import statement rather than a local definition, rather
than the generic no-match/path-escape errors currently returned.

**Counter-example found, 2026-08-04 (`pandas/26`, Nemotron-3-Super,
tool-based conditions)**: this project already has a live version of
the proposed fix, and it doesn't reliably work. `lookup_structure`
returns a genuinely clear, unambiguous message for an unindexed file --
`"Error: no structural data for 'pandas/tslib.pyx' (not a known file in
this package)"` -- and in `all_tools/rep2`, the trial calls
`lookup_structure` on `pandas/tslib.pyx` twice in a row, receiving the
identical error both times, with no behavioral change in between. The
mechanism conjectured above already exists in this harness for the tool
delivery path; getting told a file isn't indexed does not reliably stop
a model from re-querying it. Worth downgrading this entry's fix
conjecture from "untested, plausible" to "tested in a related form,
insufficient on its own" -- an informative error message alone doesn't
substitute for whatever forces a model to actually update on it.

---

## 21. Frequency map's raw edit-count ranking can actively favor the wrong file — and, rarely, the per-trial data confirms a map-type effect rather than debunking it

**Type:** map/tool design limitation (confirmed) + a methodological
counterpoint to #14 — the aggregate/per-trial split for once resolves in
the map's favor, not against it.

**Evidence:** `scrapy/48`. The frequency map ranks `scrapy/shell.py` (58
historical edits, last-edit 2015-09-08) above `scrapy/commands/shell.py`
(23 edits, last-edit 2015-05-09) — both in raw edit-count and in literal
position in the delivered text (`freq_map.txt` line 6 vs. line 37).
Historical edit volume here tracks *how old and busy a file has been*,
not relevance to this issue, and the busier file happens to be the wrong
one. Co-change's ordering runs the other way: `scrapy/commands/shell.py`
appears at line 59 of `cochange_map.txt`, `scrapy/shell.py` not until
line 665. For DeepSeek-V4-Flash specifically this produces a clean,
deterministic split, checked trial-by-trial: **`cochange` → predicts only
`['scrapy/commands/shell.py']` in 3/3 reps (F1=0.6667 each); `freq` →
predicts only `['scrapy/shell.py']` in 3/3 reps (F1=0.0 each).** Every
rep flips identically within each condition — not a majority pattern, a
total one.

**Why this is a useful counterpoint to failure point #14**: #14 warned
that a condition-level correlation (map X looks better than map Y in the
mean-F1 table) often dissolves once individual trials are checked, and
turned out not to be causal for `yt-dlp/41`. This is the reverse finding
on the same kind of check — here, inspecting the individual trials
*confirms* rather than debunks a map-type effect, at least for one model
on one issue. Worth remembering both directions exist: aggregate
differences are a hypothesis to verify, not automatically noise. Not
generalized beyond DeepSeek-V4-Flash on this issue — Nemotron's best
condition on the same issue is `structural_required` (0.611), and
Ministral/gpt-oss show weak/noisy per-condition patterns, so this is a
real but model-specific effect, not evidence frequency maps are
generally worse than co-change maps.

---

## 22. Ground truth requires generalizing a confirmed bug pattern across near-duplicate files, not just finding the reported instance — near-universal failure across the formal model roster, with one exploratory counter-example proving it's achievable

**Type:** new issue category — not a localization failure in the usual
sense (finding *a* file), but a generalization failure (finding *all*
instances of the same latent defect once one is confirmed). Distinct
from every prior entry in this list.

**Evidence:** `transformers/27` (ground truth: 12 files — see the bug/fix
explanation given in conversation on 2026-08-03). The reporter's issue
and traceback describe exactly one symptom: `T5TokenizerFast.
save_vocabulary()` crashes when `self.vocab_file` is `None`. The real PR
(#12806) fixed T5 *and* swept the identical copy-pasted pattern across 11
other sentencepiece-based fast tokenizers plus their shared base class —
none of which the issue text mentions or could be inferred from the
traceback alone. Across all 144 trials (12 conditions x 4 models x 3
reps): **`t5/tokenization_t5_fast.py` found in 144/144 (100%); every one
of the other 11 ground-truth files found in 0/144.** Mean F1 is an
almost perfectly flat ~0.154 for all four models regardless of map
type — precision 1.0, recall 1/12, every time. This is the most
deterministic result recorded in this project: not "models get confused
between plausible files" (the dominant shape in every prior entry) but
"models solve the reported instance and never attempt the swept fix
at all."

**A confirmed near-miss, not just silence**: checked
`DeepSeek-V4-Flash / cochange / rep2` in full. After reading
`t5_fast.py` it explicitly states *"Let me check other fast tokenizers
that might have similar `save_vocabulary` implementations,"* searches
`def save_vocabulary` across `src/transformers/models` (a real GT file,
`mbart50_fast.py`, appears in the hit list), reads several siblings at
the wrong offsets (copied from T5's own line numbers, landing on
unrelated methods), then runs `search "abspath"` and gets back, verbatim:
`mbart50/tokenization_mbart50_fast.py:268: if os.path.abspath(self.
vocab_file) != os.path.abspath(out_vocab_file):` — direct, unambiguous,
search-confirmed proof the identical bug recurs in a second ground-truth
file. It then pivots to unrelated code and submits `t5_fast.py` alone,
dropping a thread it had just confirmed. Sharper than failure point #1
(never searched the right term) or #18 (searched the right term, never
read the result) — here the model found and read direct proof of the
exact thing the task required, and still didn't act on it.

**Touch rate on the other 11 files scales with map richness, but never
converts to a kept answer.** Checked every trial's `read_file`/
`lookup_*` calls against the other 11 GT files directly:

| Map-type group | Touch rate | | Mechanism | Touch rate |
|---|---:|---|---|---:|
| baseline | 1/12 (8.3%) | | baseline | 8.3% |
| Structural | 6/36 (16.7%) | | context | **38.9%** |
| Frequency | 10/36 (27.8%) | | tool_free | 25.0% |
| Co-change | 12/36 (33.3%) | | tool_required | 22.9% |
| All tools | 9/24 (37.5%) | | | |

Map presence roughly doubles-to-quadruples exploration breadth over
baseline, scaling with how much signal is on offer (`All tools` highest).
Delivery-mechanism ordering here is `context > tool_free > tool_required`
— the reverse of `pandas/44`'s finding (failure point #18), plausibly
because context conditions passively list every file up front, so a
model already looking at `t5_fast.py` is more likely to notice the
`*_fast.py` naming pattern while scanning, without ever deciding to call
a lookup tool. **Per-model touch rate is a near-total split**:
DeepSeek-V4-Flash 61.1% (100% under `All tools`, 6/6), gpt-oss-120B
33.3%, Ministral-3B 11.1%, **Nemotron-3-Super 0/36 (0.0%) — every
condition, no exceptions.** For DeepSeek specifically, touch rate is 0%
at baseline and jumps to 58-78% the moment any map is present, even
though DeepSeek already burns near-max turns at baseline too — map
presence, not turn budget, is what triggers the broader look for this
model. None of this breadth ever converts: kept-count for the other 11
files stays 0/144 in every cell, including the 100%-touch DeepSeek/
All-tools cell.

**Counter-example, outside the formal 4-model roster**: an exploratory
run with `claude-haiku-4-5-20251001` (`study_1/exploratory_results/`,
`none` and `cochange` only, 3 reps each — not part of the formal study
and not comparable to the main results table) shows the generalization
step is achievable, not a hard ceiling. Baseline behaves like the study
models (t5_fast.py only, F1≈0.14). Under `cochange`, 2 of 3 reps
generalize sharply: rep1 predicts 17 files, hits **10 of 12** GT files
(F1=**0.6897**, the best score recorded anywhere in this issue by a wide
margin); rep3 hits 10/12 (F1=0.526); rep2 reverts to 2 files (F1=0.143,
the instinct doesn't fire every time even for this model). The rep1
transcript shows the exact step every study-model trial stopped short
of: turn 2, immediately after reading `t5_fast.py`, *"Now let me check
if there are other similar fast tokenizer files that might have the same
issue"* — broadens to `search "save_vocabulary"` across
`src/transformers/models`, then methodically reads and explicitly
confirms the pattern in five separate siblings ("This has the same
issue!" / "Same issue."), including checking a negative control
(`gpt2_fast.py`, which has no vocab file and correctly isn't flagged) to
reason about *which* tokenizers are actually susceptible. Submits 17
files, imperfect (7 aren't in the true ground truth) but the only trial
in the entire issue that turns "the bug recurs" into a broader answer
rather than an abandoned observation.

**Why this matters for the project's overall claims**: every other
"maps didn't help" finding in this list is compatible with "the model
just isn't capable of that leap yet" being false in general — this issue
is the cleanest test of that question this project has, since one
exploratory data point shows the leap is achievable given the right
model, even if none of the four formally-studied models make it. Worth
treating as a capability-ceiling question (does the model's own
reasoning support pattern generalization at all) layered on top of, not
instead of, the map-effectiveness question this project's main models
were chosen to answer.

---

## 23. Widest per-model split recorded (0% to 100%), and the sharpest touch-vs-kept gap yet -- a case where the submit-gate mechanism demonstrably doesn't touch the actual bottleneck

**Type:** model behavior (decision-weighting) -- the most extreme instance
of the "retrieval succeeds, commitment fails" pattern (#9, #10, #15,
#18, #21, #22) found so far, plus new evidence about which failures
Study 3's submit-gate can and can't fix.

**Evidence:** `gpt-engineer/11` (ground truth: single file
`gpt_engineer/core/diff.py`; see the bug/fix explanation given in
conversation on 2026-08-03 -- note the real PR only fixes the *silent*
part of "failing silently," leaving the underlying partial-application
behavior the reporter actually objected to unchanged). Per-model success
rate is a near-total, almost binary split: **DeepSeek-V4-Flash 33/33
(100% -- every condition, including baseline), gpt-oss-120B 0/36 (0% --
every condition, no exceptions), Nemotron-3-Super 2/33 (6%),
Ministral-3B 8/33 (24%).** Both extremes are ceiling/floor effects: no
map type or delivery mechanism can move DeepSeek's or gpt-oss's number,
because it's already fixed at the boundary in every cell.

**gpt-oss-120B reads `diff.py` in 26/36 trials (72%) and keeps it in the
final answer 0/36 times** -- the most extreme touch-vs-kept gap recorded
in this project (previous record: `fastapi/20`'s 0% for this same
model, but off a much lower 21-touch base rate; here it's nearly
three-quarters of all trials). Checked one trial in full detail
(`ast_compact/rep2`): reads `diff.py` in its entirety (418 lines),
confirms `class Diff:` via search, then spends 15 further turns
re-reading `steps.py` and `chat_to_files.py` in loops (several
exact-duplicate reads of identical line ranges) before producing **two
different final answers that disagree with each other**: its own
closing reasoning text reads `["gpt_engineer/core/default/steps.py"]`,
but the actual `submit_answer` tool call, on a separate later "final"
turn, names `chat_to_files.py` instead. Neither is correct, and unlike
failure point #9 (reasoning names one file, submission uses another) the
disconnect here is between two different *submitted* answers -- an even
sharper instance of the same underlying pattern.

**Turn count rules out under-exploration as the explanation.**
gpt-oss-120B averages the *most* assistant turns of any model on this
issue (13.0, vs. 9.9-11.5 for the other three) despite scoring zero --
consistent with its 72% touch rate, it is not failing from insufficient
looking.

**Mechanism breakdown shows the submit-gate helps exactly one model, and
does nothing for the model that most needs help:**

| Model | baseline | context | tool_free | tool_required |
|---|---|---|---|---|
| DeepSeek-V4-Flash | 3/3 | 9/9 | 12/12 | 12/12 |
| gpt-oss-120B | 0/3 | 0/9 | 0/12 | 0/12 |
| Nemotron-3-Super | 0/3 | 0/9 | 1/12 | 1/12 |
| Ministral-3B | 0/3 | 1/9 (11%) | 2/12 (17%) | 5/12 (42%) |

Ministral shows a real, monotonic gate effect matching `pandas/44`'s
finding (failure point #18): baseline 0% -> tool_required 42%. For
gpt-oss, `tool_required` -- the condition designed specifically to force
more exploration before answering -- produces the identical 0% as
baseline. This is direct, clean evidence that Study 3's gate mechanism
targets *one specific* failure mode (under-exploration) and is
structurally incapable of fixing the other (already-explored,
won't-commit) even when both failure modes reduce to the same F1 score.

**Map implication**: none. Search vocabulary was already on-target for
every model, including gpt-oss (`apply_diffs`, `validate_and_correct`
-- the literal function name in `diff.py` -- `salvage_correct_hunks`),
and DeepSeek solves the issue from baseline with no map present at all.
This is not an information-availability gap; nothing tested in this
project (structural, frequency, co-change, or the submit-gate mechanism)
addresses a pure commit-to-a-finding failure once the finding has
already been made.

---

## 24. Submit-gate mechanism trades exploration breadth for single-answer confidence -- helps single-file ground truth, actively hurts multi-file ground truth that needs a combination

**Type:** map/tool design limitation (confirmed) -- a genuine
complication of the Study 3 submit-gate finding from failure points #18
and #23, not a simple extension of it. Those two entries showed the
gate reliably *increases* success; this issue shows the same mechanism
*decreasing* it, and the reason is structural, not model-specific.

**Evidence:** `rich/12` (ground truth: 4 files -- `markdown.py` (the
obviously-relevant file, contains the buggy `"default"` lexer-name
fallback), `syntax.py` (the actual fix mechanism, a new `default_lexer`
fallback property), plus `console.py` and `text.py` (docstring-only,
essentially unfindable by design); see the bug/fix explanation given in
conversation on 2026-08-03). `syntax.py`'s touch rate is already
near-ceiling in every condition -- DeepSeek-V4-Flash reads it in
**literally 100% of trials (36/36) regardless of mechanism**, Ministral
11/12-12/12 under tool_free/tool_required, Nemotron 10/12-12/12 -- so
this is not an under-exploration case at all. Despite that, kept rate
stays low everywhere, and for three of four models, moving from
`tool_free` to `tool_required` -- the more forceful mechanism -- makes
the keep rate on `syntax.py` *worse*, not better: DeepSeek 2/12 -> 0/12,
Ministral 4/12 -> 1/12, Nemotron 2/12 -> 0/12. This is the opposite
direction from `pandas/44` (#18) and `gpt-engineer/11` (#23), where the
same gate reliably raised success rates.

**Root cause, checked directly**: mean number of files predicted per
trial, and how often both `markdown.py` and `syntax.py` land in the same
answer together, by mechanism:

| Mechanism | mean files predicted | both GT files kept together |
|---|---:|---:|
| baseline | 1.00 | 1/12 |
| context | 1.14 | 2/36 |
| tool_free | 1.12 | 5/48 |
| tool_required | **0.98** | **0/48** |

`tool_required` has the lowest answer breadth of any mechanism (below
1.0 -- some trials submit nothing scorable at all) and is the only
mechanism where the two real ground-truth files are never submitted
together, in 48 trials. The gate appears to push toward a single,
maximally-confident answer rather than a broader one -- which is exactly
why it helped on `gpt-engineer/11`'s single-file ground truth (forcing
commitment to the one right answer) and why it hurts here: full credit
requires *combining* the obvious file with the less-obvious mechanism
file, and a mechanism that narrows toward one confident pick works
against that regardless of which file gets picked.

**Why this matters beyond this one issue**: it reframes the submit-gate
not as a uniformly positive intervention but as one with a real
trade-off axis -- single-file/single-candidate issues benefit from
forced commitment, multi-file issues requiring a *combination* of a
salient file and a non-salient one are structurally disadvantaged by the
same mechanism. Worth checking against other multi-file issues in this
list (`localstack/19`, `keras/12`, `transformers/27`) to see whether this
breadth-narrowing effect recurs, since all three also involve combining
an obvious file with a much-less-obvious one.

---

## 25. Map presence can silently change first-move behavior without ever being narrated -- and the effect is both model-specific and map-type-specific

**Type:** methodological finding + model behavior -- addresses a real
gap in every prior entry's evidentiary standard. All previous "did the
model use the map" checks in this list relied on explicit textual
citation or an observable tool call; this entry shows that standard
under-detects usage for context-delivered maps, where a model can act on
injected information without ever narrating that it did.

**Evidence:** `keras/5` (ground truth: `keras/engine/saving.py`; see
the bug/fix explanation given in conversation on 2026-08-03). Checked
each model's literal first tool call across `none` (baseline) vs.
`ast_compact`/`freq`/`cochange` (all three maps delivered as context):

| Model | baseline | ast_compact | freq | cochange |
|---|---|---|---|---|
| DeepSeek-V4-Flash | blind explore (3/3) | **direct-read saving.py (3/3)** | mixed | mixed |
| Nemotron-3-Super | blind explore (3/3) | **direct-read saving.py (3/3)** | blind explore (3/3) | blind explore (3/3) |
| Ministral-3B | search | search | float-trap (3/3) | search |
| gpt-oss-120B | explore/search | **float-trap (3/3)** | mixed | mostly float-trap |

DeepSeek and Nemotron both flip from 100% blind-exploration at baseline
to 100% direct `read_file` on the ground-truth file as their literal
first action under `ast_compact` -- zero search calls, immediate and
total -- with no reasoning text ever mentioning the structural map. This
is only explicable by the map's injected content (`ast_compact`
literally lists `get_json_type(obj) L61`, `save_model(...)`,
`load_model(...)` under the file's entry): a model that opens by reading
the exact right file, unprompted by any search, is acting on something
already sitting in its context window.

**The effect is map-type-specific, not just model-specific.**
`freq` and `cochange` -- which deliver only numbers (edit counts,
co-change counts) rather than actual symbol/file names -- do **not**
produce the same flip for either DeepSeek or Nemotron, both of whom
mostly stay at blind-explore under those two conditions. Naming
concrete symbols appears to be what triggers the silent jump; a bare
ranked-list-of-counts does not.

**Ministral shows the effect 0% of the time** -- it always searches
first regardless of condition, never jumping straight to the file even
under `ast_compact`.

**gpt-oss-120B shows the effect inverted -- a genuine harm, not a
non-help.** At baseline it doesn't open with the literal-error-text
search (`float`) at all. Under `ast_compact` specifically, it does so in
100% of trials -- worse than having no map. One untested, plausible
mechanism: a denser system prompt (map content plus issue text) gives
more material to skim past before acting, and this model defaults to
anchoring on the issue's own error text rather than parsing the map's
symbol list -- the opposite of the intended effect. Worth flagging as a
real cost of structural-map-as-context delivery for this model, not
merely an absence of benefit.

**Even the clean, silent, unambiguous form of context usage still
mostly fails to convert.** Nemotron's `ast_compact`/rep1 reads
`saving.py` first and still submits `optimizers.py`; DeepSeek does the
same in 2 of its 3 `ast_compact` trials. This sharpens rather than
undercuts the commitment-gap thesis running through this whole list
(#9, #10, #15, #18, #21, #22, #23, #24): even when map usage is about
as unambiguous as it can get -- immediate, total, zero-search -- the
downstream decision to keep the finding is a separate, largely
unaffected problem.

---

## 26. First case with two scorable ground-truth files at a genuine 0% find rate -- and a real, if partial, co-change signal for the pair sitting unused

**Type:** model behavior (evidence weighting), re-analyzed with the
corrected data -- the first entry in this list computed from
`thefuck/10`'s valid re-run (see entry #17's original bug and the
2026-08-03 correction/sync note in "Notes on use" below; any earlier
discussion of this issue predates the fix and should not be cited).

**Evidence:** `thefuck/10` (ground truth: `thefuck/utils.py`,
`thefuck/conf.py`, `thefuck/const.py`; see the bug/fix explanation
given in conversation on 2026-08-03 -- `get_all_executables()`'s `$PATH`
scan is genuinely slow, and the fix adds an opt-out setting rather than
speeding up the scan itself, split across a filter function in
`utils.py` and settings-plumbing in `conf.py`/`const.py`). Across all
144 trials: `utils.py` found in 44 (31%); **`conf.py` and `const.py`
found in 0/144 each** -- the first pair of scorable, in-scope
ground-truth files in this project found *zero* times, not just rarely
(compare `rich/12`'s `console.py`/`text.py`, each found once).

**Dominant wrong guess is a strongly "quoted" pull**:
`thefuck/rules/missing_space_before_subcommand.py` (104/144, 72%) is
the exact rule named verbatim in the issue's own debug output (`DEBUG:
Trying rule: missing_space_before_subcommand; took: 0:00:08.341279`) --
the caller of the slow function, not the file that needs to change.

**`conf.py`/`const.py` are touched occasionally (11-14% of trials) but
converted to a kept answer 0% of the time** -- lower base rate than
most touch-vs-kept cases in this list, but the same 0% conversion
pattern. Checked the actual delivered (truncated top-3) co-change text
for the pair that's found (`utils.py`) against the pair that's missing
(`conf.py`):
```
thefuck/utils.py → thefuck/conf.py (9x)   [rank 2 of 3]
thefuck/conf.py  → thefuck/utils.py (9x)  [rank 2 of 3, mutual]
thefuck/const.py → thefuck/conf.py (6x)   [rank 1 of 3]
```
A real, mutual, top-3 co-change link exists between the one
ground-truth file models do find and the ones they don't -- weaker than
`rich/12`'s case (not the entire top-3, and `const.py`'s link only runs
one direction: `conf.py`'s own top-3 doesn't list `const.py` back,
edged out by `types.py`/`utils.py`/`corrector.py`), but genuine, not
noise, and sitting directly in context every time `utils.py` is found.
Consistent with the recurring co-change-available-but-unused pattern
(#6, #12, #21, #24), just at this issue's much lower `utils.py` base
find rate (31%) than those cases' higher-frequency ones.

**Per-model split**: gpt-oss-120B is the clear floor (F1=0.0139, 0/3
baseline through 0/12 `tool_required` on `utils.py`'s keep rate --
never converts a touch into a kept answer in any condition).
DeepSeek-V4-Flash is the strongest converter, especially under
`context` (7/9 kept, 78%). Mean F1 by model: DeepSeek 0.2209, Ministral
0.2056, Nemotron 0.1083, gpt-oss 0.0139.

---

## 27. A perfect condition-level score dissolves into a search-strategy coincidence -- and the strategy that actually worked was a domain-convention search, not anything map-derived

**Type:** methodological caution (third confirming instance of failure
point #14's pattern) + a genuinely new, positive finding about *what
kind of search* succeeds when neither traceback nor map relationship is
available.

**Evidence:** `stable-diffusion-webui/5` (ground truth:
`ui_extra_networks.py`, `shared_options.py`; see the bug/fix
explanation given in conversation on 2026-08-03 -- a one-sentence
feature request with zero technical detail, no code names, no error
text). `shared_options.py` is found by only one model at all
(DeepSeek-V4-Flash, 10/144 overall; the other three models: 0/108
combined). Broken down by exact condition, DeepSeek's `cochange`
(map-as-context) trials are a perfect 3/3 -- looks like a clean
co-change win at a glance.

**Checked the actual delivered co-change data first, and it doesn't
support that reading.** `ui_extra_networks.py`'s top-3 partners
(`ui_extra_networks_checkpoints.py`, `shared.py`,
`ui_extra_networks_hypernets.py`) and `shared_options.py`'s top-3
(`sd_samplers_common.py`, `processing.py`, `sd_samplers_kdiffusion.py`)
never mention each other in either direction -- there is no co-change
link between the two ground-truth files for this map to have surfaced.

**Checked the actual transcript instead.** No `lookup_cochange` call
(Study 1 context conditions have no tools to call). The real path: after
reading `ui_extra_networks.py` and noticing the new UI elements should
trigger a settings-reload, the trial searches for `needs_reload_ui` --
a decorator already used on other, unrelated settings in
`shared_options.py` -- across `modules`, which surfaces the file
directly. A genuinely resourceful piece of reasoning: recognizing a
*codebase convention* (a decorator marking settings that need a UI
reload) as a bridge from one known-relevant file to another, unrelated
by any map signal, entirely independent of co-change data.

**Confirmed this isn't map-dependent**: checked `ast_compact` (0/3
kept) directly -- DeepSeek never tries the `needs_reload_ui` search in
any of those 3 reps, despite touching `shared_options.py` by other
means in 2 of them. What determines success looks like whether a given
trial happens to try this specific search, not which map condition it's
running under -- the same shape as `yt-dlp/41`'s original debunked
correlation (#14), now recurring for a third time (also `keras/5`,
conversation on 2026-08-03).

**Why the positive half is worth keeping despite the negative
methodological point**: this is the first case in this list where the
winning strategy for an issue with *no* traceback, *no* quoted
vocabulary, and *no* map relationship between its ground-truth files is
a search for a shared code-convention marker rather than a shared
data-relationship. No map type tested in this project encodes "which
settings share a decorator/convention" as a queryable signal -- it's a
different kind of relationship entirely from AST structure, edit
frequency, or co-change history, and worth flagging as a candidate
signal type distinct from anything else conjectured in this list so
far.

---

## 28. Two ground-truth files never explored even once -- a clean natural experiment distinguishing "truncation hides a real signal" from "the signal itself is too weak to survive any list length"

**Type:** map/tool design limitation (confirmed, two-part) -- a
concrete, quantified extension of failure point #7's per-file co-change
truncation finding, using two ground-truth files from the same issue as
a controlled contrast.

**Evidence:** `gpt-engineer/12` (ground truth, scorable: `chat_to_files.py`,
`steps.py`, `file_selector.py`, `files_dict.py`; see the bug/fix
explanation given in conversation on 2026-08-03 -- the real PR is a full
architectural rewrite of the edit-parsing pipeline, not a targeted
patch, triggered by an inline traceback naming `chat_to_files.py`'s
functions directly). Unlike every other issue in this list, wrong
guesses are essentially absent: of 144 trials, 107 predict exactly one
scorable file, 31 predict exactly two, 6 predict zero -- almost no
trial ever substitutes a plausible-but-wrong file, they simply stop
once they run out of ideas. `chat_to_files.py` is found in 130/144
(90%); `steps.py` in 39/144 (27%, almost entirely DeepSeek-V4-Flash,
8-9/9 per condition); **`file_selector.py` and `files_dict.py` are
found in 0/144 each, and -- checked directly -- touched (read or
looked up) in 0/144 each, across every mechanism including baseline.**
This is not a touch-vs-kept case (#9, #10, #15, #18, #21, #22, #23,
#24, #26, #27) -- it's total non-exploration, the first clean instance
of that shape in this list.

**The co-change data explains why, and splits into two distinct
sub-cases worth telling apart.** Checked the actual delivered
(truncated top-3) co-change text: `chat_to_files.py`'s top-3 is
`steps.py` (10x), `base_agent.py` (8x), `cli_agent.py` (7x); `steps.py`'s
top-3 is `custom_steps.py` (21x), `cli_agent.py` (20x), `main.py`
(14x). `file_selector.py` co-changes with `steps.py` at **10x -- the
same strength as `chat_to_files.py`'s own link to `steps.py`** -- but
is edged out of the delivered top-3 by three non-ground-truth files
with higher counts. This is failure point #7's mechanism, concretely
quantified: a real, dominant-strength relationship, hidden purely by
list length, not signal weakness -- fixable by a longer list.
`files_dict.py` is a genuinely different case: checked its full,
untruncated 21-partner list directly, and it does have real links to
all three other ground-truth files (`chat_to_files.py` 3x,
`file_selector.py` 2x, `steps.py` 2x) -- but weak enough to sit around
rank 7-15 of 21 even without any truncation at all. No amount of
list-length increase would have reliably surfaced this one; the signal
itself is too faint relative to the file's other, unrelated co-change
partners.

**`steps.py`'s DeepSeek-specific success is not map-dependent** --
touched and kept at or near 100% even at baseline (3/3 touched, 3/3
kept), tracking to the traceback-derived search term
`improve_existing_code` (the function that calls into `steps.py`) that
DeepSeek searches consistently and the other three models search far
less reliably. The one dip is under `tool_free` (7/12 kept, 58%,
vs. 100% under both `context` and `tool_required`) -- an unusual
mechanism ordering where voluntary tool access underperforms both
passive context and the forced gate.

**Practical implication**: this is the cleanest evidence yet for a
graduated fix to co-change delivery -- lengthening the truncated list
(or biasing it toward other ground-truth-scope files when known, though
that's not available at inference time) would plausibly have helped
`file_selector.py` specifically, while `files_dict.py` would need a
fundamentally stronger signal than co-change can provide at all, not
just a longer list of the same signal.

---

## 29. A strong, mutual, prominently-delivered co-change link between the found file and its missing partner -- fourth confirmed instance, and the strongest-magnitude case yet

**Type:** model behavior (evidence weighting) -- fourth confirmed
instance of the co-change-retrieved-and-ignored pattern (#6, #12, #21,
#24, #26), and notably the strongest individual link count seen in any
of them.

**Evidence:** `yt-dlp/45` (ground truth: `yt_dlp/__init__.py`,
`yt_dlp/YoutubeDL.py`; see the bug/fix explanation given in conversation
on 2026-08-03 -- flagged as another no-real-fix "comment"-sourced issue
like `yt-dlp/41`/`fastapi/20`, `loc_way='comment'`, no linked PR/commit;
the real explanation is almost certainly a maintainer pointing out that
the reporter's own script sets the wrong option key, `cookies` instead
of the actual internal name `cookiefile` -- confirmed as the likely
answer since `cookiefile` is itself a heavily-searched term across
every model, up to 70 hits in a single condition). `YoutubeDL.py` found
in 98/144 (68%); `__init__.py` found in 3/144 (2%).

**The co-change link between them is not weak or truncated -- it's
prominent and mutual, the strongest raw count seen in any instance of
this pattern so far**: `__init__.py`'s delivered top-3 lists
`YoutubeDL.py` at 99x (rank 2 of 3); `YoutubeDL.py`'s delivered top-3
lists `__init__.py` back at 99x (rank 3 of 3). Frequency reinforces
this further rather than competing with it: `YoutubeDL.py` is the
single most-edited file in the entire 1071-file repo (rank 1, 552
edits), `__init__.py` sits at rank 7 (168 edits) -- both prominent by
either signal, delivered together, and still only one half of the pair
ever gets kept.

**Mechanism check**: `__init__.py` touch rate scales the usual way with
mechanism strength (baseline 8% -> context 22% -> tool_free 15% ->
tool_required 33%, roughly 4x baseline under the gate) -- exploration
increases as expected, conversion still doesn't follow.

**Read this one with the no-real-fix caveat in mind** (see `yt-dlp/41`,
failure points #14-#15): since there's no actual code change behind
this issue, "the model should have found `__init__.py`" is a claim
about matching an annotator's inference from a comment, not about
localizing a real defect -- worth logging for the co-change pattern
itself (which recurs regardless), but not treated as equally strong
evidence as the PR-linked cases (`fastapi/17`, `keras/12`,
`localstack/19`, `gpt-engineer/12`) when arguing the pattern is general.

---

## 30. A traceback anchor so direct it caps exploration before a near-perfect co-change signal ever gets a chance to matter

**Type:** model behavior (under-exploration) -- distinct from the
touch-vs-kept shape running through most of this list (#9, #10, #15,
#18, #21, #22, #23, #24, #26, #27, #29): here the bottleneck isn't a
commitment failure after finding the missing files, it's that almost no
trial ever looks at them at all, because the traceback's own target
already looks like a complete answer.

**Evidence:** `fastapi/9` (ground truth, scorable: `routing.py`,
`openapi/utils.py`, `applications.py`; see the bug/fix explanation
given in conversation on 2026-08-03 -- `response_class(content=...)`
breaks for any response class whose first parameter isn't literally
named `content`, e.g. `RedirectResponse`'s `url`; fixed by passing the
value positionally). The traceback names the exact crashing line in
`routing.py`. Results: `routing.py` found in **141/144 (98%)**;
`openapi/utils.py` and `applications.py` found in **0/144 each**. Zero
wrong guesses across all 144 trials -- 141 trials predict exactly one
file, 3 predict zero, not a single trial predicts more than one. Mean
F1 is the tightest model-to-model spread found in this project (0.4861,
0.4861, 0.4861, 0.5000) -- a clear ceiling effect from a connection
direct enough that essentially any model reaches it and none look
further.

**Only 11/144 trials ever even touch `openapi/utils.py` or
`applications.py`** -- not a touch-vs-kept story, near-total
non-exploration. Checked by mechanism: baseline 0/12 (0%) -> context
3/36 (8%) -> tool_free 3/48 (6%) -> tool_required 5/48 (10%) -- even the
submit-gate barely moves it, a much weaker mechanism effect than #18/#23
found elsewhere. **Of the 11 trials that do touch either file, 0 ever
keep it** -- the same 0% conversion as the rest of this list, just off
a far smaller exploration base.

**The co-change signal is the strongest, most complete version of this
pattern found in this project.** `routing.py`'s delivered top-3:
```
fastapi/routing.py
→ fastapi/applications.py (33x)
→ fastapi/dependencies/utils.py (23x)
→ fastapi/openapi/utils.py (22x)
```
Both missing ground-truth files sit in the top-3, delivered directly
alongside the file 98% of trials already find, and the relationship is
mutual in both directions (`applications.py`'s own top partner is
`routing.py` at 33x; `openapi/utils.py`'s own #2 partner is `routing.py`
at 22x). Sixth confirmed instance of the co-change-retrieved-and-ignored
pattern (#6, #12, #21, #24, #26, #29) -- but the mechanism producing the
non-use is different here: it's not that the signal was seen and
discounted, it's that almost no trial's exploration ever reaches far
enough to encounter it, because the traceback alone already looks like
a finished job.

**Implication distinct from every other entry in this list**: a
stronger or more prominent co-change signal would not help here, since
the bottleneck is upstream of ever consulting it. What might help is
something that signals "this traceback-named file is not the whole
fix" before the model stops looking -- e.g. an explicit note when a
found file has unusually strong co-change partners that were never
retrieved, or a harness-level nudge that a single-file answer to a
multi-file ground truth issue warrants one more verification pass. Nothing
tested in this project does either.

---

## 31. Chasing the file that genuinely contains the real implementation, correctly, until the turn budget runs out before ever submitting anything -- because that file sits outside the study's own scoring boundary

**Type:** methodological artifact (confirmed) + model behavior
(turn-budget exhaustion) -- distinct from every prior "chasing the
wrong thing" entry (#1, #3, `keras/5`'s recurrence of #3): in those
cases the chased target was either absent from the repo or a coincidental
distraction. Here the chased target is real, substantial, and
*correctly identified as central to the actual fix* -- it's simply
outside the file-extension boundary this study's `scorable_files()`
filter scores against.

**Evidence:** `pandas/26` (ground truth, scorable: `pandas/core/
generic.py`, `pandas/tseries/index.py`; see the bug/fix explanation
given in conversation on 2026-08-04 -- `tz_localize`'s old boolean-only
`infer_dst` parameter is replaced by a generalized `ambiguous` parameter
that also accepts a per-row boolean array, letting a caller supply
known DST flags directly instead of only inferring or raising). Mean F1
inverts this project's usual model ranking sharply: gpt-oss-120B 0.8435
(best), Ministral-3B 0.6945, Nemotron-3-Super 0.4167,
**DeepSeek-V4-Flash 0.1833 (worst)** -- DeepSeek is normally this
project's strongest model.

**`tz_localize_to_utc` dominates every model's search vocabulary**
(57-169 hits per cell) -- not a coincidental distraction like prior
"chasing" entries, but a real, substantial part of this specific fix:
checked the actual PR and `pandas/tslib.pyx` (the Cython implementation)
receives a 152-line change in the same commit, including the identical
parameter rename and the actual array-handling logic for `ambiguous` --
more changed lines than either scorable ground-truth file. **Confirmed
`.pyx` files are genuinely normal, hand-edited source in this codebase,
not generated artifacts**: `tslib.pyx` has 120 commits before this
issue's `base_commit` alone, with ordinary contributor commit messages
(`BUG: Timestamp cannot parse nanosecond from string`, `API:
Timestamp.tz_localize and tz_convert raises TypeError`, `ENH:
tz_localize(None) allows to reset tz`) -- real logic, not boilerplate.
It's simply excluded from `ground_truth_scorable` because this study's
`scorable_files()` filter is `.py`-only (the same mechanism that
excludes `.js`/test/docs files elsewhere in this list), presumably
because the structural/AST maps can't parse Cython syntax.

**DeepSeek is the model most drawn to this real-but-unscored file, and
it costs it severely.** Checked its raw (unfiltered, pre-scoring-filter)
predictions across all 36 trials: it submits `pandas/tslib.pyx` in 7 --
a correct, sophisticated identification of where the fix's actual
implementation lives. But **29 of 36 trials (81%) submit nothing at all
scorable or otherwise** -- checked one directly (`none`/`rep1`):
`hit_turn_cap: True`, `stop_reason: "max_turns"`, and its literal last
action before running out of its 30-turn budget is another `search
"tz_localize_to_utc"` call. It never reaches `submit_answer`. This is
the most extreme version of the "chase the underlying implementation"
pattern found in this project -- not wasted-but-recovered effort, a
complete failure to submit anything in the large majority of trials.

**gpt-oss searches the same term almost as heavily (57-89/cell) but
converts far better** -- it also searches `is_dst` consistently
(20-31/cell, a term straight from the new parameter's docstring),
suggesting it balances checking the Cython source against actually
committing to the two Python wrapper files, rather than getting stuck
purely chasing the implementation the way DeepSeek does.

**Why this is worth treating as a methodological finding, not just a
DeepSeek weakness**: DeepSeek's technical instinct here was arguably
*more* correct than the models that scored better -- it identified the
file containing the actual algorithmic change, which happens to sit
outside an extension-based scoring boundary chosen for map-tooling
reasons unrelated to code relevance. This is a genuine limitation of
`scorable_files()`'s `.py`-only scope for any repo (like pandas, at
this era) where core logic legitimately lives in compiled-extension
source files -- worth flagging as a scope caveat when interpreting any
cross-model comparison on Cython-heavy issues, separate from whatever
conjecture follows about turn-budget management.

---

## 32. Map presence doesn't stop a model from falling into an unproductive search loop -- it helps by getting the real answer "banked" before the loop consumes the turn budget, which only sometimes translates into an actual submission

**Type:** model behavior (turn-budget dynamics) -- a mechanism-level
finding for *why* map presence sometimes rescues a trial from the same
Nemotron/`pandas/26` context as entry #31, distinct from that entry's
own focus (the `.pyx` scoring boundary). Checked directly rather than
inferred from aggregate numbers, per this project's established
standard (see failure point #14).

**Evidence:** `pandas/26`, Nemotron-3-Super, whose mean F1 on this
issue swings from **0.000 at baseline** (0/3) to **0.667 under context**
(`ast_compact`/`freq`/`cochange` pooled) to 0.361/0.389 under
`tool_free`/`tool_required` -- a large aggregate effect that could
easily be misread as "the map prevented the search-loop trap." Checked
several transcripts directly and it doesn't: **Nemotron falls into the
same obsessive `tz_localize_to_utc` re-search loop as entry #31's
DeepSeek case, at similar or even higher proportional rates, under
every condition including context.** One baseline trial spends 13 of
30 turns (43%) on `tslib.pyx` alone and hits `max_turns` never having
called `submit_answer`.

**What actually differs is *when* the real ground-truth file gets
read, and whether that's early enough to survive being "banked" before
the loop eats the rest of the budget.** In a successful `freq` trial,
`pandas/tseries/index.py` is read as the 3rd action -- then the trial
spends the remaining ~27 turns on the same repeated `tz_localize_to_utc`
search pattern as baseline, and its final action at turn 30 is
`submit_answer(files=["generic.py", "index.py", "tslib.pyx"])`,
bundling the early find together with the never-resolved Cython chase.
**But early discovery alone doesn't guarantee success**: checked a
*failed* `cochange` trial and `index.py` is read just as early (2nd
action) -- yet this trial never calls `submit_answer` at all, hitting
`max_turns` with empty final content after the identical obsessive
search pattern consumes the rest of its budget.

**The mechanism is closer to raising the odds of a late accidental
submission than to preventing the underlying trap.** Map presence gets
the correct file into the trial's working context earlier, which
plausibly leaves more "slack" turns for the model to eventually break
off its search loop and call `submit_answer` before the hard cutoff --
but it's stochastic per trial, not a reliable guarantee, since the
counter-example above found the file at essentially the same turn and
still ran out the clock with no submission at all.

**Distinct implication from entry #31's methodological framing**: even
if `scorable_files()` were extended to include `.pyx` files (that
entry's conjecture), this specific failure mode -- burning the turn
budget on a single repeated search until the trial times out with no
submission -- would still cost real credit on any issue with a similarly
strong non-file-specific attractor term. The harness-level fix
conjectured in entry #31 (a diminishing-returns check on repeated
near-identical search queries, or a forced interim "submit your current
best guess" once turns run low) is the more directly actionable lever
for *this* mechanism specifically, independent of the scoring-boundary
question.

**Follow-up, checked at the turn level (2026-08-04): the "early
banking" mechanism explains context's jump cleanly but does *not*
explain `tool_free`/`tool_required`'s improvement over baseline**,
which needs a different (currently unconfirmed) explanation:

| Mechanism | mean turn `index.py` first touched | ever submits anything |
|---|---:|---:|
| baseline | 5.7 | 0/3 (0%) |
| context | **2.3** | 8/9 (89%) |
| tool_free | 5.7 (identical to baseline) | 6/12 (50%) |
| tool_required | 4.9 | 6/12 (50%) |

`tool_free`'s mean first-touch turn is exactly the same as baseline's,
yet its submission rate is far higher (50% vs 0%) -- so unlike context,
something other than "found the file sooner" is driving the
improvement. Two honest, unverified candidates rather than a confirmed
mechanism: (1) `baseline`'s n=3 is small enough that 0% could partly be
an unlucky sample rather than a robust floor, and (2) a
`lookup_structure` call returns a condensed structural summary rather
than a full file body, which is cheaper to process per-turn than
`read_file` and could leave more effective turns for the
search-loop-then-submit cycle without changing when the first touch
happens -- not directly verified. Flagged explicitly as an open
question rather than folded into the "map presence helps via early
banking" claim above, since the data for tool conditions doesn't
actually support that mechanism.

---

## 33. A single file's co-change links split cleanly into "genuinely absent" and "real but directionally hidden" -- worth distinguishing rather than treating a low find-rate as one uniform kind of failure

**Type:** map/tool design limitation (mixed) -- refines every prior
co-change-ignored entry (#6, #12, #21, #24, #26, #29, #30) by checking
*all* of one file's potential ground-truth-pair links at once, rather
than one link in isolation. The mix within a single file is the new
observation: this project has separately documented "signal never
existed" (part of failure point #12's `localstack/19` case) and "signal
existed and was ignored" (every other instance) as different issues'
findings; here both happen for the same file simultaneously.

**Evidence:** `transformers/5` (ground truth, scorable: `dummy_pt_objects.py`,
`dummy_tf_objects.py`, `__init__.py`, `modeling_tf_auto.py`,
`convert_pytorch_checkpoint_to_tf2.py`; see the bug/fix explanation
given in conversation on 2026-08-04 -- a "what else do I need to
change" contribution-checklist issue, PR-linked). `dummy_pt_objects.py`
is found in 1/144 trials, far below its four sibling files (50-63%).
Checked `data/cochange_pair_metrics.csv`'s all 10 pairs among the 5
files directly:

| Pair with `dummy_pt_objects.py` | co-change count | rank |
|---|---:|---|
| ↔ `dummy_tf_objects.py` (its most "obvious" pairing) | 1 | 120/121, 22/22 (dead last, both directions) |
| ↔ `__init__.py` | 11 | **1/121**, 13/257 |
| ↔ `modeling_tf_auto.py` | **0** | never co-changed |
| ↔ `convert_pytorch_checkpoint_to_tf2.py` | **0** | never co-changed |

**Two of the four links are genuinely, literally absent** -- no map
type computed from this repo's history could have surfaced them,
categorically different from this list's other co-change findings.
**The `__init__.py` link is `dummy_pt_objects.py`'s single strongest
relationship of any kind** -- its #1 partner out of 121 (11x, vs. 4x
for the runner-up) -- but a second correction (2026-08-04, pushed back
on by the user before being checked) downgrades this from "strong,
correctly-delivered signal" to a directional-truncation case, the same
mechanism as failure point #7. **Checked `__init__.py`'s own delivered
top-3 entry directly -- the direction 91/144 trials actually
approach this from, since that's the file they read -- and
`dummy_pt_objects.py` isn't in it at all**:
```
src/transformers/__init__.py
→ src/transformers/modeling_auto.py (52x)
→ src/transformers/tokenization_auto.py (26x)
→ src/transformers/configuration_auto.py (25x)
```
`dummy_pt_objects.py`'s 11x doesn't crack the top-3 from this side --
it sits at rank 13/257, nearly 5x below the weakest of the three shown
partners. The link is only visible by querying *from*
`dummy_pt_objects.py`'s own entry, which requires already suspecting
it matters -- a chicken-and-egg problem, and since `dummy_pt_objects.py`
is touched in 1/144 trials, essentially nobody ever queries from that
side. 11 shared commits is also genuinely weaker in absolute terms than
this project's clearer "strong, ignored" cases (`yt-dlp/45`'s 99x,
`fastapi/9`'s 33x, `scrapy/48`'s 46-99x range) -- this entry's earlier
"strong but ignored" framing overstated it by only checking one
direction.

**Correction after checking touch rate directly, 2026-08-04: this is
not a touch-vs-kept case at all.** `dummy_pt_objects.py` is read or
looked up in exactly **1 of 144 trials** (DeepSeek, `tool_required`) --
and even that one trial doesn't keep it. Every other model x mechanism
cell is a flat 0/9 or 0/12. So the accurate description isn't "the
signal was seen and discounted" (this list's usual commitment-gap
shape, #9/#10/#15/#18/#21/#22/#23/#24/#26/#27/#29/#30) -- it's that the
file is essentially never engaged with at all, closer to
`gpt-engineer/12`'s `file_selector.py`/`files_dict.py` total
non-exploration (#28). Models reading `__init__.py` in the majority of
trials apparently don't act on its co-change context naming
`dummy_pt_objects.py` as the #1 partner, rather than reading it and
rejecting it. One anomaly worth flagging separately: a single Ministral
trial (`context`) *keeps* `dummy_pt_objects.py` in its final answer
with **zero** recorded touch of it anywhere in the transcript -- a
name-only guess (plausibly from a directory listing or the passively
injected map text) rather than a reasoned inclusion, not a genuine
counter-example to the non-exploration finding.

**The intuitively "obvious" pairing turns out to be the weakest
link, not the strongest**: a developer reasoning by symmetry would
expect `dummy_pt_objects.py` and `dummy_tf_objects.py` (mirror-image
dummy stubs for the two frameworks, usually added together for a new
model) to co-change heavily -- instead they're each other's *least*
prominent partner (rank dead-last both directions, 1 shared commit).
Historical co-edit patterns don't track conceptual symmetry the way a
human's mental model of "these two files obviously go together" would
predict.

**Practical implication**: when auditing any co-change-ignored claim
going forward, check the full set of a file's potential ground-truth
partners *and both query directions* before calling a link "strong and
ignored" -- a low aggregate find-rate can conflate "the map had
nothing to offer" (unfixable, two of the four links here), "the map's
signal is real but only visible from a direction nobody queries"
(failure point #7's truncation mechanism, this issue's `__init__.py`
link), and "the map had a strong, correctly-delivered signal that got
ignored anyway" (the recurring pattern documented elsewhere in this
list, e.g. `yt-dlp/45`, `fastapi/9`) within the same
file, and the fix each half calls for is different.

---

## 34. Final `submit_answer` calls occasionally contain malformed, non-path "filenames" -- a real, dataset-wide, low-rate formatting failure concentrated in gpt-oss-120B and gated conditions

**Type:** model/harness interaction bug (confirmed, rare) -- an even
more severe variant of failure point #9 (submission disconnected from
stated reasoning): here the disconnect isn't between two different
plausible files, it's between coherent reasoning and outright garbage.

**Evidence:** `transformers/5`, `gpt-oss-120B`, `structural_required`/
rep2 (flagged directly by the user while reviewing trials). The
transcript shows genuinely productive exploration -- reads `__init__.py`,
`modeling_dpr.py`, `modeling_tf_auto.py`, and `dummy_tf_objects.py`,
touching 3 of the 5 real ground-truth files -- and its own final
reasoning text is a correctly-annotated candidate list (`["src/
transformers/modeling_tf_dpr.py", // new TensorFlow implementation of
DPR (must be added), "src/transformers/__init__.py", // import the new
TF-DPR classes...`, using JavaScript-style `//` comments inside what
needed to be valid JSON). The actual recorded `submit_answer` call,
however, is:
```json
{"files": ["BERT", "BERT", "."]}
```
No relationship to the reasoning that immediately preceded it.

**Checked whether this is a one-off**: scanned all 6,480 trials across
every issue in this project for final answers containing non-path,
non-`.py`-suffixed, implausibly-short strings (excluding the
`['[]']` empty-answer parsing quirk and legitimate short filenames like
`pyproject.toml`, both of which are benign and not part of this
pattern). Found **8 confirmed instances** (0.12% of all trials) -- rare,
but real and reproducible, not a single fluke:

| Issue | Model | Condition | Malformed output |
|---|---|---|---|
| `gpt-engineer/9` | gpt-oss | freq | `["GPT doesn't need any modifications"]` |
| `yt-dlp/45` | DeepSeek | temporal_frequency | `['cookies']` |
| `yt-dlp/45` | DeepSeek | all_tools_required | `['cookies']` |
| `scikit-learn/49` | gpt-oss | temporal_cochange | raw whitespace garbage |
| `thefuck/5` | gpt-oss | temporal_frequency | `['text']` |
| `pandas/38` | DeepSeek | structural_required | `['pivot_table']` |
| `rich/1` | gpt-oss | structural_required | `['user-provided-not-found']` |
| `transformers/5` | gpt-oss | structural_required | `['BERT', 'BERT', '.']` |

**Two real, non-random skews in this small set**: gpt-oss-120B accounts
for 5 of 8 (DeepSeek the other 3; Ministral and Nemotron, zero), and 5
of 8 sit under `_required`/gated conditions specifically. Checked
`rich/1` directly to rule out a harness-injected placeholder leaking
into the recorded data -- it's genuinely the model's own tool call,
`submit_answer(files=["user-provided-not-found"])`, reading like an
attempt to say "the referenced thing wasn't found" formatted as if it
were a literal filename, rather than an empty answer or an explanation.

**Likely mechanism**: when a model is forced into producing a
`submit_answer` call (especially under the required-tool gate, where
the harness's own tiered tool-choice fallback is documented elsewhere
in this project's history as needing a fix once already) without a
confident real answer ready, it occasionally emits a natural-language
fragment, a bare word, or a placeholder string as a "filename" instead
of either a genuine file path or an honest empty list. This is a
harness/prompting robustness gap, not a localization reasoning failure
-- worth a defensive fix at the scoring/parsing layer (reject or flag
predictions that don't look like plausible file paths, rather than
silently scoring them as simple wrong guesses) independent of anything
about maps.

---

## 35. Ministral-3B alone generates malformed tool-call names in ~1 of every 20 trials -- a confound on top of, not just alongside, its usual weakest-model ranking

**Type:** model/harness interaction bug (confirmed, systemic) --
distinct from entry #34's malformed-*final-answer* pattern: this is a
malformed *tool call* problem, occurring throughout a trial rather than
only at submission, and it's exclusive to one model rather than spread
across several.

**Evidence:** first spotted directly by the user in `transformers/5`,
`Ministral-3B`, `structural` (Study 2, tool_free) -- all 3 reps never
touch a single ground-truth file. Checked each individually:
- **rep1**: never calls a tool at all. Reasons purely from the issue
  text's own casually-written bare filenames (`__init__.py`,
  `convert_pytorch_checkpoint_to_tf2.py`, no `src/transformers/`
  prefix), and submits those exact bare strings. A real `submit_answer`
  call is made, but every path is wrong (missing the real prefix), so
  `final_files_predicted_scorable` ends up empty despite a genuine
  submission having happened.
- **rep2**: every tool call has the form `list_files("modeling_tf_dpr.py")`
  or `lookup_structure("modeling_tf_dpr.py")` as the literal *name*
  string, with empty `{}` arguments -- Python-call syntax jammed into
  the name field instead of using the separate `arguments` field. All
  ~26 tool calls in the trial fail with `"Error: unknown tool '...'"`.
- **rep3**: same underlying bug, different manifestation --
  `list_files{"path": "transformers"}` as the name, again with empty
  arguments. Same total-failure result.

**Confirmed this is not a one-off**: scanned all 1,620 Ministral-3B
trials across every issue in this project for any tool-call name
containing `(`, `{`, or `"` (characters that can never legitimately
appear in a real tool name). **84/1,620 trials (5.2%) affected.**
Checked the same scan against the other three models: **0/1,620 for
gpt-oss-120B, DeepSeek-V4-Flash, and Nemotron-3-Super each** -- this is
exclusively a Ministral-3B phenomenon, not a shared harness bug.

**Clusters by delivery mechanism, not randomly**:

| Mechanism | Malformed-name rate |
|---|---:|
| baseline | 7.4% (10/135) |
| context | **2.5%** (10/405) |
| tool_free | **7.4%** (40/540) |
| tool_required | 4.4% (24/540) |

By exact condition, the two richest tool surfaces are the worst --
`all_tools` and `structural` (Study 2, voluntary) both sit at 9.6% --
while the simplest, most constrained conditions are the best: `freq`
(context-only, 0.7%) and `temporal_frequency_required`/`ast_compact`
(1.5% each). Context conditions (no tool-calling decision beyond
`read_file`/`search`/`list_files`) are consistently the safest;
`tool_free` conditions, which offer the broadest menu of optional
tools including multiple `lookup_*` variants, are consistently the
worst; `tool_required` sits in between, plausibly because the gate's
single forced call is a narrower, more constrained target than
`tool_free`'s freely-chosen mix. The pattern reads as "more tool-name
surface area to get wrong -> more malformation," not as a mechanism
this project's existing map/gate framing was designed to explain.

**Why this matters beyond one model's score**: when a malformed-name
trial occurs, every subsequent tool call in it typically repeats the
same broken pattern (confirmed directly in rep2/rep3 above) -- the
entire trial's exploration is wasted, not just one call. Since
Ministral is already this project's most consistent low-scorer across
many issues, any claim that Ministral is "weakest at localization"
should be read with this confound in mind: some non-trivial fraction of
its measured weakness (at least 5.2% of trials, likely more once
partial/single-call malformations too subtle for this exact-character
scan are counted) is a tool-calling format bug, not evidence about its
reasoning or map-usage ability specifically.

---

## 36. Baseline underperforms even on files named verbatim in the issue body -- for three of four models, any map or tool condition recovers them, not a specific type

**Type:** map/tool design benefit (map-agnostic) -- a fourth instance
of failure point #16's "presence changes framing, not new information"
pattern, but the cleanest yet: it holds for 3 of 4 models
simultaneously on the same issue, and splits cleanly against a
same-issue control (two sibling files already at or near ceiling from
baseline alone).

**Evidence:** `transformers/5` -- the issue body itself names 3 of the
5 scorable ground-truth files verbatim in one sentence (`__init__.py`,
`convert_pytorch_checkpoint_to_tf2.py`, `utils/dummy_tf_objects.py`),
plus `modeling_tf_dpr.py` (not scorable ground truth, but the file the
reporter says they already wrote). Split the 5 files by baseline
(no map, no tools) kept-rate:

| File | Named in issue body? | Baseline kept rate (all 4 models) |
|---|---|---|
| `__init__.py` | yes | 11/12 (92%) |
| `modeling_tf_auto.py` | no (implied -- needs sweeping in for TF-Auto support) | 8/12 (67%) |
| `convert_pytorch_checkpoint_to_tf2.py` | **yes** | 5/12 (42%) |
| `utils/dummy_tf_objects.py` | **yes** | 5/12 (42%) |
| `utils/dummy_pt_objects.py` | no | 0/12 (0%) |

The two under-performing *named* files split further by model. Checked
`data/issue_case_study_notes.csv`-style touch/kept tables per model,
baseline through `tool_required`, for both:

| Model | `convert_pytorch...py` baseline kept | ...context | ...tool_free | ...tool_required |
|---|---:|---:|---:|---:|
| Ministral-3B | 0/3 | 3/9 | 7/12 | 6/12 |
| gpt-oss-120B | 1/3 | 4/9 | 5/12 | 3/12 |
| Nemotron-3-Super | 2/3 | 5/9 | 4/12 | 6/12 |
| DeepSeek-V4-Flash | **2/3** | 9/9 | 12/12 | 10/12 |

(`dummy_tf_objects.py` shows the same shape: Ministral 0/3→2/9→3/12,
gpt-oss 1/3→5/9→6/12, Nemotron 2/3→4/9→5/12, DeepSeek 2/3→9/9→11/12.)

**Three of four models jump substantially the moment any map or tool
condition is present** -- context alone is enough; it doesn't need to
be a specific map type, and it doesn't need to be a tool the model
actually calls (context conditions require no tool-calling decision at
all). DeepSeek is the exception, already near-ceiling at baseline for
both files. This mirrors, at a smaller scale, `localstack/19`'s entry
#16 finding (map presence anchoring interpretation toward "this is a
code task"), but here the effect is sharper because the correct
filenames are already sitting in the prompt in plain text -- recovering
them shouldn't need any information a map or tool could add. The
paired `touched` counts (mostly low or zero at baseline, rising with
condition) suggest models aren't confidently echoing the issue body's
own quoted filenames without some form of external validation first --
practically, a name floating in a casually-worded feature request
doesn't get trusted as a real repo path until either the model reads it
directly or a map lists it independently.

**Practical implication**: this is a case where a map's real value
isn't retrieval (the information was already in the prompt) but
confidence -- corroborating a filename the model already has reason to
suspect is real. A cheap, targeted intervention worth testing: a
system-prompt instruction to treat any `backtick`-quoted or
code-formatted path mentioned in the issue body as a candidate file
worth including even without independent confirmation, rather than
requiring a map/tool source to "count" it as validated.

---

## 37. A ground-truth file made unreachable by three independent mechanisms at once -- pruned out, positionally buried, and a relationship the fix itself creates, not one any pre-fix signal could have anticipated

**Type:** map/tool design limitation (structural blind spot + genuine
absence + positional burial, combined) -- distinct from every prior
"unreachable file" entry in this list because all three failure
mechanisms stack on the same file simultaneously, rather than one
mechanism explaining the miss on its own. Also distinct in a second
way, confirmed by reading the actual fix commit directly (2026-08-06,
not just inferred from ground truth): this isn't a case of a real,
pre-existing relationship the maps failed to surface -- the
relationship the models would have needed to find *did not exist until
the fix commit created it*.

**Evidence:** `pandas/38` (ground truth, scorable: `pivot.py`,
`util/_exceptions.py`). `pivot.py` found in 128/144 (89%);
`_exceptions.py` found in **0/144**, and confirmed touched (read/looked
up) in 0/144 too -- total non-exploration, not a touch-vs-kept case,
same shape as `gpt-engineer/12`'s `file_selector.py`/`files_dict.py`
(#28) and half of `transformers/5`'s `dummy_pt_objects.py` (#33).
Checked all three map types directly for why:

| Map type | `_exceptions.py` status |
|---|---|
| Structural | `pruned_out` -- never made the token budget at all |
| Frequency | `found`, but rank 200/294 (68% through the list) |
| Co-change | `found`, but rank 289/294 (98.3% through -- second-to-last file in the whole list) |
| Co-change (relationship) | `pivot.py`↔`_exceptions.py`: **0 shared commits, ever**, `never_cochanged` in both directions |

**Checked the real PR directly (#49615, commit `ab89c53f48`) to
understand the actual connection, not just its absence.** `_exceptions.py`
is pandas' small toolkit for rewriting exception/warning *messages*
specifically (pre-fix, it held exactly two functions: `rewrite_exception`,
which find/replaces text in a caught exception's message and re-raises;
and `find_stack_level`, used to attribute a warning's stacklevel
correctly). The fix adds a third, `rewrite_warning()` -- a direct sibling
of the existing `rewrite_exception`, same pattern applied to
`warnings.warn()` output instead of a raised exception. `pivot.py` is
the *only* caller anywhere in the codebase: it wraps the exact line that
triggers the confusing `FutureWarning` (`grouped.agg(aggfunc)`) in
`rewrite_warning(...)`, replacing the generic `numeric_only` deprecation
message with a `pivot_table`-specific one. **Checked both directions of
the import graph, before and after the fix**: `pivot.py` had zero
imports from `_exceptions.py` at `base_commit` (confirmed directly --
no reference at all), and `_exceptions.py` never references `pivot.py`,
before or after. The `from pandas.util._exceptions import rewrite_warning`
line, and the function it imports, are both introduced by this exact
commit -- there is no earlier state in which the connection existed for
any signal to have captured.

**This rules out even a smarter, not-yet-implemented map type, not just
the three studied here.** `scrapy/48` (#21) conjectured a call/import-
graph signal as a fourth map type worth building. Checked whether it
would have helped here: no -- since no import existed pre-fix in either
direction, an import-graph map computed from the codebase's state before
the fix would have shown nothing to find, for the identical reason
co-change shows nothing (both are backward-looking over a relationship
that doesn't yet exist).

**The real fix is also a completely different mechanism than every
model hypothesized**, worth noting since it bears directly on #38's
DeepSeek trace on this same issue: no model's exploration (including the
~29-turn dive into `groupby.py`/`generic.py`/`apply.py`'s internal
aggregation-dispatch chain) was ever chasing the right kind of fix. Every
model investigated *threading a `numeric_only` parameter through*
`pivot_table` -- a reasonable reading of the issue's own request, but not
what the maintainers actually did. The real fix doesn't expose the
parameter at all; it intercepts and rewrites the warning message. No
amount of additional turns tracing the aggregation call chain would have
led anywhere near `_exceptions.py`, because that file has nothing to do
with the mechanism every model was (reasonably) investigating.

**No single fix closes this gap.** Frequency and co-change *do*
technically list `_exceptions.py`, but so deep into a long tail (68% and
98% through) that reaching it requires reading past hundreds of other
files first -- practically equivalent to not being listed, for any model
with a finite attention/budget. Structural's blind spot is pure
token-budget pruning here (`pruned_out`), not the zero-AST-content
exclusion mechanism (`_exceptions.py` does contain real functions).

**Practical implication:** the cleanest example yet of a file that no
*content* change to any current or plausible future map type would
fix -- not because of a truncation, ranking, or structural limitation in
isolation (each has a targeted fix conjecture elsewhere in this list),
but because the file's relevance to this issue is a fact the fix commit
itself creates, not one reflected anywhere in the codebase's prior
state. The only thing that could plausibly have pointed a model there is
the domain-convention reasoning a human reviewer would use -- noticing
`_exceptions.py`'s existing `rewrite_exception` pattern and inferring a
warnings-side sibling might belong nearby -- which is a conceptual leap,
not a retrievable signal. Worth citing as the boundary case for "how far
map-based retrieval alone can go," including hypothetical richer map
types, not just the three actually studied here.

---

## 38. A forced final-answer call can ignore its own tool-choice constraint -- a third flavor of non-compliant submission, and evidence the failure is commitment, not discovery

**Type:** model/harness interaction bug (confirmed) + model behavioral
trait -- distinct from entry #34 (garbled non-path strings inside an
otherwise-compliant `submit_answer` call) and entry #35 (Ministral's
malformed tool-call *names*): here the forced call is well-formed, but
the model uses it to call a *different* tool entirely, ignoring the
constraint rather than mangling the resulting content.

**Evidence:** `pandas/38`, DeepSeek-V4-Flash. DeepSeek hits `max_turns`
in 27/36 trials (75%) on this issue -- checked whether this is
map/condition-specific and found it isn't: it happens in every one of
the 12 conditions, including `none` (baseline, 3/3), confirming it's a
model trait (chasing full mechanistic understanding of the bug rather
than stopping once enough is known), not something any map causes or
fixes -- a third documented instance of this DeepSeek pattern on a
pandas issue specifically, after `pandas/26` (#31) and `pandas/44`
(#18).

Within that turn-exhaustion, one condition stood out: `cochange` scores
F1=0.0 in all 3/3 reps, while `none` and `temporal_frequency` (both
also near-100% `max_turns`) still salvage a real partial answer
(F1≈0.5-0.67) via the forced-final-answer mechanism. **Checked the raw
API response logs directly, not just the aggregate scores**, for the
actual forced "final_answer"-labeled call in each condition:

- `none`/rep1, `temporal_frequency`/rep1: the forced call returns
  `submit_answer(['pivot.py', 'frame.py'])` -- compliant, produces a
  real (partial-credit) answer.
- `cochange`/rep1, 2, 3 (all three reps checked): the forced call
  instead returns **`read_file`** on an unrelated internals file
  (`apply.py`, `frame.py`) -- the model simply keeps exploring rather
  than submitting, even under the constraint meant to force a final
  answer. With no compliant call to recover a prediction from, the
  trial ends with an empty submission.

**This sharpens, rather than softens, the turn-exhaustion story.**
Checked how close each `cochange` trial actually was to a correct
answer: all 3 reps read `pivot.py` (the correct, primary fix file) as
their literal **first action, turn 1** -- not a late discovery. One rep
(rep2) even re-searched `pivot.py` again on turn 29, one turn before
the trial ended. The following ~28-29 turns in every rep were spent
drilling into unrelated call-chain internals (`apply.py`, `groupby.py`,
`generic.py`), never converging back to a submission, and never once
touching the unreachable second file (`_exceptions.py`, see #37) either
-- the extra exploration bought nothing, for either file. This is not
"ran out of time before finding the answer" -- the answer was found and
read immediately, and every subsequent turn moved further from
submitting it, not closer.

**Practical implication:** two separate, stackable fixes worth testing,
neither map-content-related. (1) A harness-level fix for the compliance
gap itself -- if a forced tool_choice is meant to guarantee a specific
tool call (`submit_answer`), the harness should validate the returned
call's tool name and retry/escalate rather than silently accepting
whatever tool the model chose (mirrors Study 3's own submit-gate
validation logic, just applied to the *forced*-answer path instead of
the voluntary one). (2) A prompt-level nudge for the underlying
disposition -- an explicit instruction that once a file plausibly
answering the issue has been found and read, further exploration should
justify itself against the turn budget already spent, rather than
defaulting to continued investigation. Same class of fix already
conjectured for `pandas/26` (#31) and `pandas/44` (#18); this issue is
the third data point for it.

---

## 39. Map/tool presence roughly triples wrong-file inclusion on a single-file ground truth -- negative in every condition tested, across all three studies, the single worst-performing row in Study 1's own ranking

**Type:** map/tool design harm (confirmed, dataset-extreme) -- distinct
from every "map presence helps via framing" entry in this list (#16,
#36): here presence measurably *hurts*, consistently, and the
magnitude is large enough to stand out from the rest of the dataset,
not just a single condition's noisy dip.

**Evidence:** `gpt-engineer/9` (single-file ground truth: `ai.py`).
Checked `data/issue_map_effect_ranking.csv` / `_study2.csv` /
`_study3.csv` directly: **all 11 non-baseline conditions tested across
all three studies show a negative pooled_mean_delta_f1** -- no
exceptions. Study 1's `temporal_cochange` (Δ=−0.222) is the single
worst-performing (issue, condition) row in the *entire* Study 1 ranking
table (rank 0 of 135); `structural` (Δ=−0.195) is second-worst. Study
2's `temporal_cochange` (Δ=−0.347) is an even larger-magnitude drop.
Study 3's `all_tools_required` (Δ=−0.194) is the largest drop of that
study's four gated conditions.

**Mechanism, checked directly rather than inferred from the ranking
alone:** `main.py` (the CLI entry point, a plausible-looking but wrong
guess) is included in the final answer at 17% under baseline, rising to
42-58% under every map type (Structural 47%, Frequency 42%, Co-change
50%, All tools 58%) and, checked separately, every delivery mechanism
(context 53%, tool_free 42%, tool_required 52%) -- roughly a 2.5-3x
jump that's flat across both axes, not concentrated in one map type or
one mechanism.

**A genuine, strong co-change relationship exists here -- initially
looked causal, checked directly, does not hold up.** `ai.py`'s
untruncated co-change list has `main.py` as its #1 partner (12x, out of
28 partners) -- a real, strong, delivered-in-full signal (not truncated
away the way most of this list's co-change findings involve). The
obvious hypothesis: models are reading this relationship and
over-applying it. **Checked whether trials that padded with `main.py`
actually used the co-change tool**: for gpt-oss, only 2/20 tool-based
padding trials ever called `lookup_cochange` at all; for DeepSeek,
6/17 (35%, still a minority). Most of the over-inclusion happens
without the co-change tool ever being touched -- ruling out a
co-change-specific causal story. The flat rate across all four map
*types* (including `freq`/`structural`, which have no co-change
relationship to `main.py` to leverage) independently confirms this: a
genuinely co-change-driven effect would show co-change standing out
from the others, and it doesn't. Best-supported reading: `main.py` is
independently a plausible guess on its own (real CLI entry point for
the `--azure` flag the issue references), and *any* map/tool presence
raises confidence in already-plausible-looking files generally -- the
same family as #16/#36's presence-as-framing effect, but here the
"boosted" file happens to be wrong rather than right.

**A second wrong-file attractor, `token_usage.py` (31/144 wrong-guess
hits), is unrelated to any map effect** -- its inclusion rate is flat-
to-declining under every map type (33% baseline vs. 17-29% under maps)
and traces directly to `ai.py`'s own source, which imports and uses
`TokenUsageLog` throughout the class -- models reading `ai.py` in full
see the import and plausibly, over-cautiously, tag it along. Worth
separating from the `main.py` finding since the two wrong files have
different causes despite superficially similar symptoms.

**A sharp, model-specific decisiveness split explains most of the
per-model variance**: Ministral-3B submits `ai.py` *alone* in 31/36
trials (86%, F1=0.898 -- the best score of any model on this issue, a
reversal of its usual weakest-model role in this project) and never
once includes `token_usage.py`. DeepSeek-V4-Flash submits `ai.py` alone
in **0/36** trials -- always pads with at least one wrong file
(F1=0.445). gpt-oss and Nemotron sit in between (5/36 and 12/36 exact,
respectively). This split holds regardless of mechanism: checked
DeepSeek's mean files-predicted by mechanism specifically (baseline
2.00, context 2.00, tool_free 1.50, tool_required 2.00) -- Study 3's
submit-gate, which reliably narrows answer breadth for single-file
ground truth elsewhere in this list (#18, #23, #24), does **not**
reduce DeepSeek's padding on this issue at all.

**The real fix bears no resemblance to what any model hypothesized.**
Checked the actual merged PR (#1170) directly: the true fix is a
one-line change to a default `OPENAI_API_VERSION` string in `ai.py` --
unrelated to the issue's own "deployment name mixing with model name"
framing, which is a real but incidental symptom, not the bug. No
model's search trajectory (in this case-study's earlier turn-by-turn
trace) was ever chasing the right mechanism.

**Practical implication:** a genuine counter-example to treating "richer
map/tool signal" as an unambiguous good, worth citing alongside
`keras/5`-style false positives as the other direction of the same
caution -- here the effect is real (not noise, not a discovery
artifact) but actively harmful, and it stems from correctly-delivered,
strong signal being over-applied by models that already have a
decisiveness problem, not from any map defect. Fix conjecture: for
single-file (or otherwise narrow) ground truth specifically, a
prompt-level caution against including a merely well-connected file
without independent evidence it's actually implicated -- distinguishing
"this file often changes alongside the true fix" from "this file is
part of the fix" -- since the current framing appears to blur the two
for models already prone to hedging. An expanded-replication check
(all 12 conditions x 4 models x 12 extra reps, isolated from the main
dataset) was launched 2026-08-06/08 to confirm this effect holds beyond
n=3/cell; see `scripts/run_replication_check.py`.

---

## 40. A ground-truth file positioned reasonably in every map type, still found 0/144 times -- the bottleneck is conceptual irrelevance, not delivery

**Type:** map/tool design limitation (distinct category) -- unlike
every other "unreachable file" entry in this list (#28, #37), this one
is not caused by truncation, pruning, positional burial, or a
non-existent relationship at generation time. The file is genuinely
available, at a reasonable position, in every map type tested -- and
still never touched. The limitation is that no map, current or
hypothetical, encodes conceptual/semantic relevance to an issue's own
text, and this file's inclusion has none.

**Evidence:** `scikit-learn/45` (ground truth, scorable:
`sklearn/_min_dependencies.py`, `sklearn/decomposition/_truncated_svd.py`;
issue is an RFC to raise scikit-learn's minimum supported scipy
version, quoting `SCIPY_MIN_VERSION = '1.0.0'` directly in the body).
`_min_dependencies.py` found in 138/144 (96%) -- near-trivial, the
constant name is quoted verbatim in the issue. `_truncated_svd.py`
found in **0/144**, and confirmed touched 0/144 too -- total
non-exploration.

**Checked map position directly, expecting a burial/pruning story like
#37's -- found the opposite:**

| Map type | `_truncated_svd.py` status |
|---|---|
| Structural | `found`, rank 342/1517 (22.5% through) |
| Frequency | `found`, rank 106/237 (44.7% through) |
| Co-change | `found`, rank 58/237 (24.5% through) |

None of these are burial-level positions the way `pandas/38`'s
`_exceptions.py` was (68-98% through, or pruned out entirely). This
file is genuinely available to any model that reads far enough into
any of the three maps.

**Checked the real PR (#20069) directly to understand why it's
included as ground truth at all.** It's a 122-file, 40+-commit
infrastructure rollout (CI configs across CircleCI/Travis/Azure
Pipelines, Python version support matrix) -- `_min_dependencies.py` is
the direct, intentional target (one line, exactly the issue's own
request). `_truncated_svd.py`'s 15-line diff is a **docstring doctest
fix** -- updated example output numbers, collateral damage from some
dependency version bump elsewhere in the same mega-PR silently changing
scipy's RNG output in a doctest. No logic change, no relationship to
the "raise the minimum scipy version" request beyond both landing in
the same enormous PR. Confirmed via co-change data: `_min_dependencies.py`
and `_truncated_svd.py` have **zero shared commits, ever** -- this
exact fix commit is the only time they've ever changed together, and
even then only coincidentally (bundled in the same PR, not causally
linked).

**Practical implication:** distinct from #37's "the relationship
doesn't exist yet" boundary case -- here there IS a relationship (both
files changed in the same real commit), and the map delivers the file
findably, but the relationship itself is conceptually arbitrary from
the issue's perspective. No search strategy grounded in the issue's own
content (`scipy_min_version`, `linprog`, `interior-point` -- all
genuinely on-target, confirmed in every model's search vocabulary)
would ever lead to a docstring-only file in an unrelated module. Worth
treating this ground-truth file similarly to this project's other
"lighter-weight" cases (`yt-dlp/41`, `fastapi/20`) despite being
PR-linked with a real code diff -- the diff is real, but its bundling
into scorable ground truth for *this* issue is closer to an artifact of
PR-granularity ground-truth extraction than a fact about what the issue
required. Ceiling analysis: since only one of two GT files is ever
findable, max possible F1 here is 0.667; gpt-oss and Nemotron both land
exactly there (clean ceiling hits), while Ministral (0.5926) and
DeepSeek (0.6297) fall slightly short from a handful of empty/off-target
submissions, not padding.

---

## 41. Wholesale frequency-map injection roughly halves an otherwise-near-perfect answer rate for one model specifically -- the map's own ranking, not the issue text, drives the drop (statistically confirmed, n=15)

**Type:** map/tool design harm (confirmed, condition-isolated) -- a
second entry demonstrating maps actively hurting (after #39), but a
cleaner, more surgical case: here the harm is isolated to exactly one
(model, condition) cell against a clean, fully-passing control every
other cell in this project would predict, not a broad multi-condition
effect.

**Evidence:** `scikit-learn/45` (ground truth includes
`sklearn/_min_dependencies.py`, whose target constant
`SCIPY_MIN_VERSION = '1.0.0'` is quoted verbatim in the issue body --
see #40 for the issue's other ground-truth file). Checked Ministral-3B's
hit rate on `_min_dependencies.py` by exact condition (not pooled map-
type group): `ast_compact` 3/3, **`freq` 0/3**, `cochange` 2/3,
`temporal_frequency` 3/3, `temporal_frequency_required` 3/3. The miss
is isolated to the single wholesale frequency-context condition -- every
other delivery of the same or different map data succeeds. Every other
model, in this exact same `freq` condition, succeeds 3/3 (checked
directly: gpt-oss, DeepSeek, Nemotron all submit `_min_dependencies.py`
alone, every rep) -- ruling out the map content itself being
unworkable; this is a Ministral-specific, `freq`-context-specific
interaction.

**Traced all 3 transcripts turn-by-turn.** Every trial's opening
reasoning latches onto the issue body's *elaboration* paragraph (about
`scipy.optimize.linprog`'s `"interior-point"` solver replacing
`"simplex"`) and never once searches for `min_version`,
`MIN_VERSION`, or anything resembling the actual quoted constant name
-- despite it being the single most literal, search-hunt-free
identifier available anywhere in the issue text. Checked the actual
injected `freq_map_pruned_55k.txt` directly: `sklearn/linear_model/*`
files dominate the top of the frequency-ranked list (`_coordinate_
descent.py` 35 edits, `_ridge.py` 32, `_base.py` 29, `_logistic.py`
25 -- all in roughly the top 20% by rank), while `_min_dependencies.py`
sits at rank 219/237, **91.9% through the list**, with only 3 edits.
All three trials spend their entire turn budget chasing
`scipy.optimize` usage through exactly that prominently-ranked
linear_model cluster (`glm.py`, `_base.py`, `_coordinate_descent.py`,
`utils/optimize.py`, `_huber.py`, `_logistic.py`, `_nca.py`) -- never
random flailing, but methodically following the map's own ordering
into a plausible-looking dead end.

**Why this is specifically a *delivery-mechanism* failure, not a
frequency-*data* failure**: the identical underlying frequency data,
delivered as a tool (`temporal_frequency`/`temporal_frequency_required`)
instead of wholesale context, produces 3/3 correct in both conditions.
The wholesale map dumps the entire ranked list into the prompt at once
with the real answer buried at the tail; the tool version only returns
whatever's explicitly queried, so a model that searches the issue's own
vocabulary first never encounters the misleading ordering at all. Every
other model in this dataset appears to do exactly that (search first,
consult map second); Ministral-3B here appears to read the passively-
injected ranked list itself as the primary cue for where to look, ahead
of the issue's own text -- the mirror image of #16/#36's presence-
boosts-a-correct-guess pattern, but for a wrong direction instead of a
right one, and isolated to one model.

**This case was selected (2026-08-08) as a targeted expanded-
replication candidate specifically for demonstrating map-as-context
harm** -- unlike #39's broad, all-conditions effect on `gpt-engineer/9`,
this is a single clean cell with a strong built-in control (every other
model/condition combination succeeds), making it a strong candidate for
isolating and confirming a genuine active-harm mechanism at higher n.
Deliberately picked *because* the frequency map's own ranking is poorly
aligned with this issue's true relevance (buries the answer at 91.9%
while surfacing an unrelated prominent cluster) -- a targeted stress
test of whether a low-quality map signal can override otherwise-
reliable baseline behavior, not a general claim about frequency maps.
Scope: Ministral-3B only, `none` (baseline) and `freq` (context)
conditions only, expanded reps via `scripts/run_replication_check.py`.

**Update, 2026-08-08 -- expanded to n=15/cell (original 3 + 12 new
reps), results confirm the effect but revise its shape.** Combined:
`none` **15/15 (100%)**, `freq` **8/15 (53%)** -- not a deterministic
0/3-style failure as the original n=3 implied, but a real, large,
statistically confirmed drop in success rate. Fisher's exact test (the
correct choice here over chi-square or McNemar's: two independent
proportions, not paired observations, and one cell is a literal zero --
chi-square's asymptotic approximation is unreliable at that boundary)
on the 2x2 table [15,0 / 8,7]: **two-sided p=0.0063**, one-sided
(baseline > freq) p=0.0032. Report the two-sided value as the headline
number -- the directional hypothesis was partly derived from the same
original n=3 pilot now folded into this larger sample, so treating
"freq hurts" as fully pre-specified would be generous to the finding.
Also revises the mechanism: the 5 new misses (rep4, 7, 8, 14 of the 12
extra) don't all repeat the original 3 reps' exact `linear_model`
derailment path -- they wander into different unrelated clusters
(`gaussian_process`, `neural_network`, `ensemble`) -- consistent with
"the map's poor ranking creates a general pull toward *some* prominent-
but-wrong file," not "there's one specific wrong answer the map always
produces." Revised headline framing: **`freq` context injection roughly
halves Ministral's success rate on this issue** (100%->53%), not
"eliminates it" -- see the cross-cutting note in "Notes on use" below
for how this and `thefuck/20` together bear on this project's broader
conclusion about map usage requiring external discernment the models
don't reliably have themselves.

---

## 42. A traceback whose every named frame is wrong -- the real (scorable) answer is a same-pattern sibling the traceback never mentions at all, and success tracks pattern-generalization discipline, not map condition

**Type:** model reasoning/search-strategy issue (map-agnostic) -- a
second confirmed generalization-task-disguised-as-localization case
after `transformers/27` (#22), but with a more severe version of the
same trap: here every traceback-named file is not just insufficient,
it's actively *outside the scored package scope entirely*, so
confidently trusting the traceback caps a trial's score at zero
regardless of how much further exploration follows.

**Evidence:** `stable-diffusion-webui/13` (`ModuleNotFoundError: No
module named 'pytorch_lightning.utilities.distributed'`). Traced the
full traceback directly: the outermost frame is
`modules/launch_utils.py:340`, which calls into `modules/shared.py:18`
(`from ldm.models.diffusion.ddpm import LatentDiffusion`), which
cascades into `repositories/stable-diffusion-stability-ai/ldm/models/
diffusion/ddpm.py:20` -- a **vendored, out-of-scope submodule**
(outside this repo's defined `modules/` package scope, confirmed via
`PACKAGE_MAP`) -- where the actual broken import line lives. Both
traceback-named in-scope frames (`launch_utils.py` 8 hits,
`shared.py` 11 hits) are this issue's two dominant wrong guesses --
not coincidental plausible-sibling guesses, but literal, exact
traceback frames. The scorable ground truth,
`modules/models/diffusion/ddpm_edit.py`, is **never mentioned in the
traceback at all** -- it's a separate, in-scope file that happens to
contain the identical copy-pasted broken import line
(`from pytorch_lightning.utilities.distributed import rank_zero_only`),
found in 99/144 trials (69%) but only by models that search for the
*pattern* rather than trust the crash trace's own file path.

**A second, distinct evidence issue worth flagging up front**: checked
the underlying dataset annotation (`loc_way: 'comment'`, no linked PR)
and, going further than a prior case, checked the actual repo history
directly -- the broken import line is **still unchanged at HEAD**, and
`requirements_versions.txt` still pins `pytorch_lightning==1.9.4`
unchanged throughout. No evidence this was ever actually fixed
upstream the way the ground truth implies. Same weak-evidence category
as `yt-dlp/41`/`fastapi/20` (#14/#15) -- a suggested location from an
issue comment, not a verified accepted patch -- but here confirmed via
direct git-history inspection rather than the pickle's own `loc_way`
field alone, a stronger check than this project has previously applied
to this category of issue.

**Model split tracks pattern-generalization discipline, not map
condition.** gpt-oss (F1=0.9722) and DeepSeek (0.8843) both work
near-ceiling; Ministral (0.3056) and Nemotron (0.4815) do much worse.
Search vocabulary is identical and on-target across every model and
every condition (`rank_zero_only`, `pytorch_lightning`, `distributed`)
-- traced a winning gpt-oss trial directly: it searches the broken
symbol itself, finds *all three* files containing it (the vendored
file, the scorable file, and the raw-but-unscorable
`extensions-builtin/LDSR/sd_hijack_ddpm_v1.py`), reads all three, and
correctly submits only the in-scope one. Traced a losing Ministral
trial directly: it finds the vendored file first via the same kind of
search, **submits it alone, and never generalizes the search further**
-- a real bug, found accurately, scored zero because it's the wrong
copy of a duplicated pattern. Checked dataset-wide: **5/144 trials
submit only the vendored out-of-scope file** as their entire answer --
a small but real, reproducible instance of this specific trap. Given
search terms are identical across every map condition, this is not a
map-driven split at all -- it's whether a model treats "I found *a*
file matching the error" as sufficient, or continues to check for
duplicated instances of the same pattern before committing.

**Practical implication**: distinct fix target from most of this
list's map-content conjectures, since no map/tool signal is missing or
underused here -- every model has equally good search vocabulary
available. The lever is a search-discipline instruction: after finding
a file that plausibly explains a traceback, explicitly check whether
the same broken pattern recurs elsewhere in-scope before submitting,
rather than treating traceback-frame-found as answer-found. Same class
of fix as `transformers/27`'s (#22) generalization gap, but that
issue's version required generalizing a *confirmed fix pattern*
forward across 12 files with no traceback anchor at all; this one only
requires checking whether an *already-open* file (found via ordinary
traceback-following) has duplicates -- a lower bar that gpt-oss/
DeepSeek already clear routinely, making Ministral/Nemotron's failure
here more clearly a discipline gap than a capability ceiling.

---

## 43. Ground truth encodes a fix that was merged, then reverted by the maintainer four days later -- and one of its three files has zero pre-fix textual anchor for any map or search strategy to find

**Type:** data-integrity nuance (confirmed) + map/tool design limitation
(one file, structural) -- a new category distinct from every prior
ground-truth caveat in this list. `yt-dlp/41`/`fastapi/20` (#14/#15)
and `stable-diffusion-webui/13` (#42) involve no real accepted fix at
all (`loc_way: 'comment'`); `pandas/38` (#37) involves a real,
permanent fix whose file relationship the map couldn't have seen
because the fix creates it. This is a third, new shape: a real,
PR-linked, *merged* fix (`loc_way: 'pr'`) that was subsequently
**reverted** by the maintainer, and never reinstated in that form.

**Evidence:** `requests/12` ("Not possible to specify max_retries in
v1.X?", ground truth `sessions.py`/`adapters.py`/`api.py`). Checked the
real PR (#1219, commit `796d3225`, 2013-02-27) directly: it threads a
`max_retries` keyword through `api.py`'s docstring → `Session.request`/
`resolve_redirects` (`sessions.py`) → `HTTPAdapter.send`
(`adapters.py`). Checked the surrounding history and found the
maintainer reverted it four days later (`23d85222`, "Revert
'...adding a max_retries argument'", bare message, no rationale given)
-- and it was never reinstated in this form anywhere in the repo's
subsequent history. **Six weeks later**, a different contributor
(`36dcce1a`, 2013-04-12) delivered the same user-facing capability via
a completely different, simpler design: `max_retries` as an
`HTTPAdapter.__init__()` constructor argument, touching **only
`adapters.py`** -- no threading through `sessions.py`/`api.py` at all.
Best-supported read: the original PR was reverted for a design
objection (an invasive per-request kwarg threaded through three layers,
vs. the adapter-mounting pattern already idiomatic in this codebase),
not because the feature itself was rejected -- the ground truth this
project scores against reflects the **rejected** design, not the
permanent one.

**A second, independent finding on the same issue**: `api.py` is found
in only 19/144 trials (13%), far below `adapters.py` (122/144, 85%)
and `sessions.py` (117/144, 81%). Checked why directly -- at
`base_commit`, `api.py` has **zero pre-existing occurrences of
`max_retries`** anywhere in the file; the fix's only change there is a
single new docstring line. Same shape as `thefuck/10`'s `conf.py`/
`const.py` (#26): a new-feature ground-truth file with nothing
code-level "wrong" pre-fix for any search strategy or map type to
anchor to.

**A third, structural observation**: zero wrong-file guesses across
all 144 trials -- every single prediction fell within the 3-file
ground truth. Models under-predict (miss `api.py`) rather than
substitute a plausible-but-wrong file, the same shape as
`gpt-engineer/12` (#28).

**Practical implication**: worth a methods-section caveat distinct from
the existing "no real fix" caveat -- a PR being merged and `loc_way`
being `'pr'` doesn't guarantee the ground truth reflects the codebase's
*permanent* state, only a state that was true at some point in history.
Worth a brief audit of how many of the 45 selected issues' fix commits
were later reverted or superseded, if time permits, since this
project's provenance checks (the `base_commit` self-reference audit,
entry #17) checked for a different kind of history problem and
wouldn't have caught this one.

---

## 44. A touch-vs-kept gap for one model, and a real content-gradient for another -- but the gradient didn't survive a first expanded-replication rep, illustrating exactly why more reps were warranted before trusting it

**Type:** model reasoning issue (gpt-oss) + open, actively-being-tested
question (DeepSeek) -- two separate model-specific findings on the same
issue, one resolved, one deliberately left open pending more data.

**Evidence (gpt-oss touch-vs-kept gap):** `requests/12`. gpt-oss's
`adapters.py` inclusion rate looked map-type-graded at first pass
(pooled group: Structural 6/9 → Frequency 5/9 → Co-change 3/9 →
All-tools 3/6) -- checked at the exact-condition level and this doesn't
hold: gpt-oss sits at 1/3 or 2/3 in nearly every condition **including
baseline** (1/3), with only one condition (`temporal_frequency`, 3/3)
standing out, plausibly n=3 noise rather than a real map effect. Traced
three missed trials directly: gpt-oss **reads `adapters.py` in full**
in every one, then answers via a natural `end_turn` (never calling
`submit_answer`), and its own end-of-turn content narrows to just
`sessions.py`. A genuine touch-vs-kept commitment gap, model-specific
and largely condition-independent -- corrected from an initial,
overstated co-change-specific framing before logging.

**Evidence (DeepSeek content-gradient, open question):** the same
issue's `api.py` shows a striking condition-level pattern for DeepSeek
at the original n=3: `none` 0.8/0.8/0.8, `freq` 0.8/0.8/0.8 (no lift),
`ast_compact` 1.0/1.0/0.8 (partial), `cochange` 1.0/1.0/1.0 (full) --
tracking exactly which conditions deliver the specific relationship
needed (checked the real delivered co-change map: `sessions.py`'s
top-3 partners are `models.py` 42x, **`api.py` 24x**, `utils.py` 14x --
prominent, not truncated away; `freq` carries no relational info at
all). Confirmed via transcript trace this is a touch-vs-kept gap, not a
discovery gap (`api.py` is read even at baseline) -- and confirmed no
transcript in any condition ever narrates using map/cochange content
explicitly. This was the most promising candidate found so far in this
project for genuinely *content*-mediated map use (contrast #16/#36's
presence-only effects), since the one condition carrying the specific
relevant relationship is the one that reliably fixes the miss and the
one that doesn't, doesn't.

**The first new expanded-replication rep already complicates this**,
which is worth recording as the reason this stays an open finding
rather than a confirmed one. Launched an expanded check (2026-08-08,
DeepSeek-V4-Flash only, `none`/`freq`/`ast_compact`/`cochange`, 12 extra
reps via `scripts/run_replication_check.py`) specifically to test
whether the gradient holds at higher n. The first new rep (rep4) came
back **F1=0.5, `['requests/adapters.py']` alone, uniformly across all
four conditions** -- not just failing to replicate the gradient, but a
more severe miss than any of the original 3 reps in any condition
(dropping `sessions.py` too, not just `api.py`). One rep is not enough
to conclude the original pattern was noise (the full 48-trial run is
still in progress as of 2026-08-08), but it's a direct, concrete
illustration of exactly the risk this project's n=3-by-default design
carries, and why the "run more reps before trusting a clean-looking
condition split" instinct behind this whole replication-check program
is justified -- see `keras/5`'s fuller debunking for the more extreme
version of the same lesson.

---

## 45. A reporter's own diagnosis is exactly right, and the second ground-truth file is a pure docstring update with zero functional code change

**Type:** ground-truth structure nuance (confirmed) -- a milder,
non-reverted cousin of `requests/12`'s companion-file pattern (#43):
here the second file is a real, permanent, intentional part of the
merged fix, but still has nothing functionally "wrong" in it for a
model to anchor to.

**Evidence:** `flask/18` ("DispatcherMiddleware with different loggers
per app in flask 1.0"). The reporter's own issue body states: *"I
assume this caused by `app.logger` always having the name
`flask.app`, maybe?"* -- checked the real PR (#3282, `df470aec`)
directly and this guess is exactly correct. The actual functional fix
is a **one-line change** in `logging.py`'s `create_logger()`:
`logging.getLogger("flask.app")` → `logging.getLogger(app.name)`.
`app.py`'s entire diff is a **docstring update** describing the new
per-app-logger-name behavior -- zero functional code change. Same
shape as `fastapi/9`'s `background.py` and `pandas/44`'s
`core/indexing.py`: a real, intentional ground-truth file whose
correctness is not something any code-level bug pattern points to.

**File breakdown**: `logging.py` found in 131/144 (91%, near-trivial
given the reporter names the mechanism directly). `app.py` found in
only 55/144 (38%) -- reasonable, given nothing is functionally broken
there. Wrong-file pollution is minimal (`blueprints.py` 2,
`_compat.py`/`ctx.py` 1 each). Search vocabulary is on-target and
near-identical across every model (`logger`, `create_logger`,
`current_app`, `flask.app`) -- not a vocabulary gap.

**Practical implication**: worth grouping with #43 as a recurring
sub-category of this project's ground-truth taxonomy -- files that are
correctly, intentionally part of a merged fix, but whose own diff
carries no code-level signal a map or search strategy could surface.
Distinct from #37/#40's "genuinely unreachable" files (no relationship
for any map to find) and from #14/#15's "no real fix" files (no
accepted patch at all) -- this is a third, milder category: a real
diff exists, but it's prose, not logic, so success here tracks whether
a model treats "this docstring should track a behavior change" as
worth including, a softer standard than most of this project's
ground-truth files require.

---

## 46. A confirmed, causally-traceable instance of a tool's specific returned content driving where a model looks -- not just presence

**Type:** map/tool design benefit (confirmed, content-mediated) -- the
rarest and strongest category of positive finding in this list.
Distinct from every prior "map helps" entry (#16, #36, and the
`requests/12` gradient in #44, which stays an open question): those
are inferred from behavioral correlation across conditions, with no
transcript ever explicitly narrating map use. This one is directly
traceable, call by call: a specific tool response contains a specific
line number, and the model's very next action reads that exact line.

**Evidence:** `flask/18`, Nemotron-3-Super, the "structural" family of
conditions specifically (`ast_compact` context, `structural` tool_free,
`structural_required` tool_required). Checked the actual tool response
directly: `lookup_structure(src/flask/app.py)` returns (within its
*first* page, before any pagination) the line
`logger(self) L655` -- the exact property definition whose docstring
needed updating (see #45). Traced 6 tool-based trials (`structural` x3,
`structural_required` x3): **5 of 6 call `lookup_structure(app.py)`
first, and their immediate next action is `read_file(app.py,
offset=650)`** -- landing right on the returned line number, not
reading from the top or searching blindly. The one exception
(`structural`/rep2) skips the tool and reads the whole file directly
instead, and still succeeds, just less efficiently. This is the
cleanest causal chain found in this project to date: tool call →
specific content returned → immediate, precisely-targeted action using
that content.

**A clean, condition-isolated pattern, checked at the exact-condition
level (not pooled)**: Nemotron's `app.py` hit rate is baseline (`none`)
**0/3**, and **9/9 across all three "structural" delivery conditions**
(`ast_compact` 3/3, `structural` 3/3, `structural_required` 3/3) --
every other condition (`freq`, `cochange`, and their tool-based
equivalents) sits at 0-2/3, mixed and lower. The signal that matters is
specifically *structural* content, and it works identically whether
delivered as passive context or an active tool call -- consistent with
the mechanism being "the line number itself is useful," not anything
specific to the tool-calling interaction.

**Practical implication**: worth treating as this project's clearest
existing evidence that map *content*, not just presence, can causally
improve outcomes -- when the map format actually encodes something a
model needs (a precise location) rather than a coarse relationship
(edit counts, co-occurrence) that still requires inference to act on.
Selected as a target for an expanded-replication check (2026-08-08) to
test reproducibility at higher n -- see follow-up note once results are
in.

---

### Notes on use

- Failure points are not mutually exclusive — a single trial can exhibit
  several at once (e.g. `pandas/35`'s DeepSeek trial shows both #1 and #2).
- "Type" tags exist to separate what a better map/tool could plausibly fix
  from what's a model-side reasoning issue, since those need different
  remedies in any recommendations section.
- **Framing note (2026-08-08), worth reading before any of the entries
  below get generalized into a broader claim**: this list is evidence
  that maps *can change* model behavior — not that they do so
  consistently, or that the change is reliably helpful or harmful. Two
  entries in particular are worth reading as a matched pair rather than
  in isolation, since they involve the same underlying model trait
  producing opposite outcomes: `thefuck/20` (Ministral the *only* model
  to ever solve that issue, 3/144 trials, all Ministral — hypothesis:
  its noisier, less confident search wanders past a traceback's crash
  site into the real fix file, where every more-confident model stops
  short) and entry #41 (`scikit-learn/45`, Ministral's otherwise-
  deterministic 100% baseline success rate roughly halved by `freq`
  context injection specifically, statistically confirmed at n=15,
  Fisher's exact p=0.0063 — traced to the same higher-variance
  disposition, here manifesting as susceptibility to a misleading map
  ranking rather than beneficial search noise). Same trait, opposite
  valence, depending on whether the "atypical" pull happens to point
  toward or away from the right answer. Two data points is a pattern
  worth watching, not yet a confirmed general finding — but it's a
  clean illustration of the project's likely core conclusion: these
  maps are not consistently helpful *or* harmful on their own, and the
  models themselves show little reliable capacity to discern when a
  given map's signal should be trusted versus overridden for a given
  issue. That discernment — when a map is worth consulting, and when
  its content should be set aside in favor of the issue's own text —
  appears to remain a human-engineering judgment call, not something
  these models reliably supply on their own, at least within this
  project's scope (4 models, 45 issues, 12 conditions).
- Twenty-seven issues analyzed so far (`pandas/35`, `fastapi/17`, `thefuck/20`,
  `keras/12`, `yt-dlp/41`, `fastapi/20`, `localstack/19`, `thefuck/10`,
  `pandas/44`, `scrapy/48`, `transformers/27`, `gpt-engineer/11`,
  `rich/12`, `keras/5`, `stable-diffusion-webui/5`,
  `gpt-engineer/12`, `yt-dlp/45`, `fastapi/9`, `pandas/26`, `transformers/5`,
  `pandas/38`, `gpt-engineer/9`, `scikit-learn/45`, `stable-diffusion-webui/13`,
  `requests/12`, `flask/18`);
  intentionally kept broad and issue-specific rather than prematurely
  generalized — revisit once a handful more issues are logged here to
  see which patterns recur. `scikit-learn/45` (entries #40, #41)
  produced two distinct findings: a ground-truth file positioned
  reasonably (never buried, never pruned) in every map type yet still
  found 0/144 times, because its inclusion is conceptually arbitrary —
  a docstring fix incidentally bundled into an unrelated 122-file
  infrastructure PR, not something any map (or issue-grounded search
  strategy) could plausibly connect (#40); and a second, cleaner
  instance of active map-as-context harm after `gpt-engineer/9` (#39) —
  Ministral-3B alone, isolated to the wholesale `freq` condition alone
  (3/3 misses, vs. 3/3 hits for every other model in that exact
  condition and 3/3 hits for Ministral itself under the tool-based
  delivery of the identical frequency data), traced directly to the
  map's own edit-frequency ranking burying the real answer at 91.9%
  through the list while prominently surfacing an unrelated file
  cluster the model spends its full budget chasing instead — selected
  as a targeted expanded-replication candidate (Ministral only,
  baseline vs. `freq`, launched 2026-08-08) specifically because its
  clean single-cell isolation and strong built-in control make it a
  stronger active-harm demonstration than `gpt-engineer/9`'s broader
  effect (#41). `transformers/5` (entries #33, #34, #35, #36)
  is the most heavily-instrumented single issue in this list so far —
  it refines the co-change-ignored family by checking one file's *entire*
  set of potential ground-truth links at once rather than a single pair
  in isolation (#33); surfaces two independent, dataset-wide-confirmed
  malformed-output bugs, one gpt-oss/`_required`-concentrated (#34) and
  one Ministral-exclusive (#35, first spotted on this issue's own
  Ministral/`structural`/tool_free trials, all 3 reps stuck at 0%
  ground-truth touch); and shows the cleanest multi-model instance yet
  of failure point #16's map-presence-as-framing effect, on files whose
  names are already sitting verbatim in the issue body (#36) — worth
  the same full-set-of-links check (#33) and the same
  named-in-body-vs-baseline-kept-rate check (#36) on any future issue
  where one ground-truth file's find-rate is a clear outlier among its
  siblings. `pandas/38` (entries #37, #38) is the first issue where a
  ground-truth file's unreachability was traced to three independent
  mechanisms stacking simultaneously — structural pruning, positional
  burial (68-98% through the frequency/co-change lists), and a
  co-change relationship that was genuinely zero not because the files
  are unrelated but because the fix commit itself creates the only
  connection between them (checked the real PR directly: a brand-new
  function in `_exceptions.py` with `pivot.py` as its sole caller, no
  import in either direction beforehand) — worth checking all three
  explicitly (not just "is it in the map at all"), and worth checking
  whether a 0%-find file's relevance is being *created* by the fix
  itself before concluding any richer map type, current or
  hypothetical, would have helped (#37). It's also a third confirmed
  instance of DeepSeek's
  chase-full-understanding turn-exhaustion pattern (after `pandas/26`
  #31, `pandas/44` #18), and — the sharper addition — a third distinct
  flavor of non-compliant forced final answer (after #34's garbled
  strings, #35's malformed tool-call names): DeepSeek's forced
  `submit_answer` call returned a `read_file` call instead, in 3/3
  `cochange` reps specifically, verified against the raw API response
  logs, not just the aggregate score (#38). Notably, all three of those
  reps had already read the correct primary file on turn 1 — direct
  evidence the failure is a commitment gap, not a discovery gap, even
  under severe turn exhaustion. `gpt-engineer/9` (entry #39) is the
  first issue in this list where map/tool presence measurably *hurts*
  rather than helps, and by a wide margin — negative
  `pooled_mean_delta_f1` in all 11 non-baseline conditions tested
  across all three studies, with Study 1's `temporal_cochange` the
  single worst-performing (issue, condition) row in that study's entire
  135-row ranking table. Initially looked like a co-change-driven
  over-application (the wrong-file attractor `main.py` genuinely is
  `ai.py`'s #1 co-change partner, undiluted by truncation), but checked
  directly and ruled out: most padding trials never call
  `lookup_cochange` at all, and the inflation is equally flat across
  every map type and every delivery mechanism — a general
  presence-boosts-confidence effect (same family as #16/#36) landing on
  a wrong file rather than the right one, not a co-change-specific
  mechanism. Worth the same caution as `keras/5`'s false-positive
  correction, in the opposite direction: don't accept a large,
  consistent *negative* delta's apparent mechanism at face value either
  — check what tool calls the padding trials actually made before
  attributing it to a specific map type. An expanded-replication check
  (all 12 conditions, isolated from the main dataset) is in progress as
  of 2026-08-08 to confirm the effect holds beyond n=3/cell. As of this session, `scripts/case_study_analysis.py` (saved
  2026-08-04) is the canonical, validated script for the wrong/right
  file breakdown, model x map-type grid, search-term extraction,
  touch-vs-kept, and turn-count sections repeated across every entry in
  this list — prefer it over new ad-hoc inline scripts going forward;
  see its docstring for why (it caught and corrected a real
  discrepancy against an earlier session's disposable inline count).
  Entry #34's dataset-wide garbage-`submit_answer` scan (8/6480 trials,
  gpt-oss-120B and `_required` conditions both over-represented) is a
  harness/model-interaction finding independent of any specific issue
  — worth re-running if this project's harness or tool-choice fallback
  logic changes, to confirm the rate hasn't grown. Entry #35 is a
  larger, model-specific confound in the same family — 5.2% of
  Ministral-3B's 1,620 trials contain a malformed tool-call name (0%
  for every other model), clustered in `tool_free`/baseline conditions
  and rare in `context` — any cross-model comparison involving
  Ministral anywhere in this list should be read with this in mind,
  since it inflates apparent localization weakness with a separate
  tool-calling format bug.
  `pandas/26` (entry #31) is a distinct
  finding worth remembering when interpreting any other Cython-heavy
  repo in this dataset (`pandas` especially): `scorable_files()`'s
  `.py`-only scope means a model correctly identifying real logic in a
  `.pyx` file gets zero credit and can be structurally disadvantaged
  relative to models that never look that deep — DeepSeek's
  worst-in-project score here (0.1833) reflects a scope boundary as
  much as, or more than, any reasoning failure. Entry #32, same issue,
  is a mechanism-level companion finding worth checking for whenever an
  aggregate baseline-vs-map delta looks large for one model: map
  presence didn't stop Nemotron's search loop, it got the real file
  "banked" earlier, which only sometimes translated into an actual
  submission before the turn cap — a third, more granular addition to
  the family of cautions started by failure point #14 about not taking
  aggregate condition deltas at face value.
  `yt-dlp/45` (entry #29) is a fourth confirmed instance of the
  co-change-retrieved-and-ignored pattern (#6, #12, #21, #24, #26) and
  the strongest raw link count of any of them (99x, mutual, top-3 both
  directions) — but is also a no-real-fix "comment"-sourced issue like
  `yt-dlp/41`/`fastapi/20`, so weight it accordingly when citing the
  pattern's generality (the PR-linked instances — `fastapi/17`,
  `keras/12`, `localstack/19`, `gpt-engineer/12` — are the stronger
  evidence). `fastapi/9` (entry #30) is PR-linked and a sixth co-change
  instance, but with a genuinely different mechanism from the other
  five: not signal-seen-and-discounted, but exploration that never
  reaches the signal at all because a single traceback-named file
  already looks like a complete answer — worth treating as a distinct
  subtype (under-exploration triggered by anchor confidence) rather
  than folding into the touch-vs-kept commitment-gap story that
  dominates the rest of this list. `gpt-engineer/12`
  (entry #28) is the first issue with essentially no wrong guesses at
  all (models stop rather than substitute a plausible-but-wrong file)
  and the first with two ground-truth files at 0% *touch* rate (not
  just 0% kept) — a clean natural experiment splitting failure point
  #7's truncation finding into a fixable half (`file_selector.py`, real
  dominant-strength link, hidden only by list length) and an unfixable
  half (`files_dict.py`, genuinely weak signal even untruncated). Worth
  citing over #7 itself when arguing for a specific fix (longer
  co-change lists), since this is the quantified, two-sided version of
  that claim. `thefuck/10` (entry #26) is the first issue
  analyzed with two scorable ground-truth files found in literally
  0/144 trials each, and is the first entry computed against this
  issue's corrected data — see the sync note directly below and entry
  #17 for the original bug. `stable-diffusion-webui/5` (entry #27,
  computed against the same corrected data) is the third confirmed
  instance of failure point #14's "condition-level correlation dissolves
  on inspection" pattern (after `yt-dlp/41` and `keras/5`) — worth
  treating as an established recurring risk in this dataset's small
  per-condition n (3 reps), not an occasional fluke, and checking for by
  default whenever a single condition stands out sharply for one model.
  **Update,
  2026-08-03**: the `thefuck/10` / `stable-diffusion-webui/5` re-run
  (see entry #17) is now complete and verified — 288/288 valid trials
  synced from the native machine into `study_1/2/3`, correct
  `base_commit` confirmed on every file, and every downstream derived
  CSV (`map_position_metrics.csv`, `cochange_pair_metrics.csv`,
  `issue_map_effect_ranking.csv`, `map_token_counts_by_model.csv`, the
  pruned-ground-truth-check family, `min_budget_for_gt.csv`,
  `compiled_results.pkl`, the tool-usage comparison CSVs, and
  `issue_case_study_notes.csv`'s own `rank`/`mean_f1` columns) has been
  recomputed against the corrected data — full audit trail in
  conversation on 2026-08-03. Both issues' mean F1 moved (`thefuck/10`
  0.0928→0.1372, `stable-diffusion-webui/5` 0.3970→0.4461), each
  swapping rank with its immediate neighbor (`pandas/44`,
  `gpt-engineer/12` respectively) — no other issue's data changed. The
  two issues' own case-study entries/rows are still outstanding (based
  on the old, invalid data, or not yet written) and should be treated as
  the next issues up for analysis, not as already covered. `rich/12` (entry
  #24) complicates the submit-gate finding from #18/#23 — the same
  mechanism that reliably helps single-file ground truth measurably hurts
  multi-file ground truth needing a combination of a salient and a
  non-salient file, by narrowing answer breadth toward one confident
  pick. `keras/5` provides a second, independent instance of that same
  gate-hurts-not-helps pattern for DeepSeek-V4-Flash specifically
  (tool_free 1/12 kept → tool_required 0/12 on `saving.py`, mirroring
  `rich/12`'s `syntax.py` result) — worth treating as a real
  DeepSeek-specific susceptibility rather than a one-issue fluke, and
  revisiting if a third instance turns up. `keras/5` is also a rare
  complete inversion of this project's usual per-model strength
  ordering — DeepSeek-V4-Flash, normally the strongest model in this
  series, is the *worst* performer on this issue (F1=0.0556, lowest of
  all four), a useful caution against treating any model as uniformly
  "the strong one" across issues. Entry #25 additionally establishes
  that context-delivered maps can be used silently, never appearing in a
  model's reasoning text — a detection gap in every prior entry's
  evidentiary standard (explicit citation or an observable tool call),
  worth checking for on other context-condition issues in this list
  retroactively, since absence of citation was previously treated as
  evidence of non-use. `transformers/27` (entry #22) is
  categorically different from the other ten — a generalization failure
  (find all instances of a confirmed pattern) rather than a localization
  failure (find the one relevant file) — and should be read as its own
  category, not pooled with the others when looking for cross-issue
  trends. `stable-diffusion-webui/13` (entry #42) is a second, related
  generalization-failure case, worth reading alongside #22 rather than
  with the localization-failure majority: every traceback-named frame
  (`launch_utils.py`, `shared.py`, both this issue's dominant wrong
  guesses) is genuinely accurate but falls outside the scored package
  scope, and the real answer is a same-pattern sibling the traceback
  never names at all — success here tracks whether a model checks for
  duplicate instances of a found pattern before submitting, not map
  condition (search vocabulary is identical across every condition and
  every model). A second, independently-confirmed instance of the
  no-real-accepted-fix category (#14/#15) too — checked the actual repo
  history directly this time (import line unchanged at HEAD, dependency
  pin unchanged) rather than relying on the dataset's own `loc_way`
  annotation alone. `requests/12` (entries #43, #44) adds a new
  ground-truth-provenance category — a real, PR-linked, *merged* fix
  that was reverted by the maintainer four days later in favor of a
  simpler design six weeks on, meaning the ground truth here reflects a
  rejected design, not a permanent one — plus two separate model
  findings on the same issue: a resolved gpt-oss touch-vs-kept gap, and
  an open DeepSeek content-gradient finding that a first expanded-
  replication rep already complicated rather than confirmed, worth
  citing as a concrete illustration of why this project's whole
  replication-check program exists. `flask/18` (entries #45, #46) pairs
  a milder, non-reverted version of #43's companion-file pattern (a
  real, permanent, intentional ground-truth file that's pure prose, no
  logic — group with #37/#40's genuinely-unreachable files and
  #14/#15's no-real-fix files as a third distinct ground-truth
  sub-category) with this project's strongest positive finding to date
  — a directly-traceable, call-by-call instance of a tool's specific
  returned content (a docstring's own line number) driving where a
  model looks next, not just the tool's presence boosting confidence.
  Worth reading #46 against every other "map helps" entry in this list
  (#16, #36, #44's open question) as the one case with a real causal
  chain in the transcript itself, not an inferred behavioral
  correlation — currently the subject of its own expanded-replication
  check to confirm reproducibility. `gpt-engineer/11` (entry #23) now holds the record for both the
  widest per-model success-rate split (0% to 100%) and the sharpest
  touch-vs-kept gap (72% touch / 0% keep, gpt-oss-120B) found in this
  project, and is the clearest evidence yet that Study 3's submit-gate
  mechanism only helps the under-exploration failure mode, not the
  already-explored-but-won't-commit one. The "retrieval succeeds,
  commitment fails" touch-vs-kept pattern (#10, #15, #18) now has a fourth
  instance in `scrapy/48` (`scrapy/utils/url.py` touched in 59/144 trials,
  kept in 1) — not written up as its own entry since it adds no new
  mechanism, but strengthens the case that this is a general, recurring
  model disposition rather than an issue-specific quirk. Entry #17
  additionally identified a
  second affected issue (`stable-diffusion-webui/5`) via a full audit of
  all 45 issues in `issue_selection_final.csv`, not from separate deep-dive
  analysis — that issue's own detailed notes/failure entries are still
  outstanding. Note `thefuck/10`'s own entries (#10's search-vocabulary
  discussion, folded into #17) are based on the now-invalidated,
  wrong-`base_commit` trial data — its case-study conclusions should be
  redone once the corrected re-run (already underway as of 2026-08-03)
  completes; `stable-diffusion-webui/5` is in the same position.
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
