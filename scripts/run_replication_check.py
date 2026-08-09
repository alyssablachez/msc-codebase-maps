"""
Expanded-replication check for issues flagged in
data/model_failure_points.md's case-study notes as showing a large
baseline-vs-map delta_f1 at the standard n=3 reps/cell:

  - keras/5      -- top-ranked "most helped" issue in all three studies'
                    issue_map_effect_ranking*.csv, but direct transcript
                    inspection of the best-looking cells found no
                    content-mediated map/tool usage (see the notes column
                    of data/issue_case_study_notes.csv, keras/5 row) --
                    the leading candidate false positive. 4 conditions
                    (baseline + each study's single strongest-delta
                    condition).
  - localstack/19 -- entry #16 in model_failure_points.md, a *verified*
                    presence-mediated effect (baseline explores the right
                    files but submits doc/README.md; any map condition
                    flips the final answer) -- included as a comparison
                    case, not because it's in doubt. Same 4-condition
                    scope as keras/5.
  - gpt-engineer/9 -- added 2026-08-06. Negative pooled_mean_delta_f1 in
                    11/11 tested (non-baseline) conditions across all
                    three studies -- the single worst-performing row in
                    Study 1's entire ranking table. Partially-verified
                    mechanism: any map/tool presence roughly triples
                    main.py's wrong-file inclusion rate (17%->42-58%,
                    single-file ground truth), concentrated in
                    gpt-oss/DeepSeek/Nemotron while Ministral stays
                    unaffected -- checked directly that this is NOT
                    primarily co-change-tool-driven (most padding
                    trials never call lookup_cochange at all, even when
                    available). Given the finding is "every condition
                    hurts," not one standout condition, this issue gets
                    ALL 12 conditions (baseline + all 11 others), not
                    the 4-condition per-study-representative design used
                    for the other two.
  - scikit-learn/45 -- added 2026-08-08. Entry #41: Ministral-3B misses
                    an otherwise-trivial single-file answer
                    (`sklearn/_min_dependencies.py`, whose target
                    constant is quoted verbatim in the issue body)
                    3/3 under wholesale `freq` context injection --
                    every other model gets it 3/3 in that exact
                    condition, and Ministral itself gets it 3/3 under
                    every other condition including the tool-based
                    delivery of the identical frequency data. Traced to
                    the injected frequency map's own edit-count ranking
                    burying the real answer at 91.9% through the list
                    while prominently surfacing an unrelated file
                    cluster the model spends its full budget chasing
                    instead. Narrowest scope of any target issue here:
                    2 conditions (`none`, `freq`) x 1 model
                    (Ministral-3B only, via TARGET_ISSUES_MODELS) --
                    every other (model, condition) cell already has a
                    clean, consistent n=3 result that isn't in
                    question, so testing them again would just burn
                    budget.
  - requests/12    -- added 2026-08-08. DeepSeek-V4-Flash's only
                    real known-open case in this list with any
                    behavioral evidence toward *content*-mediated map
                    use rather than pure presence/framing (contrast
                    #16/#36): F1 by condition sits at exactly
                    none=0.8/0.8/0.8, freq=0.8/0.8/0.8 (no lift),
                    ast_compact=1.0/1.0/0.8 (partial), cochange=
                    1.0/1.0/1.0 (full) -- a clean gradient matching
                    which conditions actually deliver the specific
                    relationship needed (sessions.py's real, delivered,
                    rank-2/count-24x cochange partner is
                    requests/api.py, the exact file baseline drops).
                    Confirmed via transcript trace this is a touch-vs-
                    kept gap, not a discovery gap (api.py is read even
                    at baseline) -- and confirmed no transcript, in any
                    condition, ever narrates using map/cochange content
                    explicitly, so even a fully-confirmed result here
                    stays "behaviorally consistent with content-driven
                    use," not proof of a causal readout. Scope: 4
                    conditions (`none`, `freq`, `ast_compact`,
                    `cochange`) x 1 model (DeepSeek-V4-Flash only, via
                    TARGET_ISSUES_MODELS) -- deliberately includes all
                    3 context conditions plus baseline, not just a
                    single winner vs. baseline, since the gradient
                    across conditions (not just the cochange/baseline
                    gap) is the actual thing being tested.
  - flask/18       -- added 2026-08-08. Entry #46, this project's
                    strongest positive map-effect finding to date --
                    unlike every other target here, this is a
                    directly-traced, call-by-call causal mechanism, not
                    an inferred behavioral correlation: lookup_structure
                    (src/flask/app.py) returns "logger(self) L655" in
                    its very first (unpaginated) page of results, and
                    Nemotron-3-Super's next action in 5 of 6 traced
                    tool-based trials is read_file(app.py, offset=650)
                    -- landing exactly on that returned line number.
                    Checked at the exact-condition level: Nemotron's
                    app.py hit rate is baseline (`none`) 0/3, and a
                    clean 3/3 across all three "structural" delivery
                    conditions (`ast_compact` context, `structural`
                    tool_free, `structural_required` tool_required) --
                    every other map type sits at 0-2/3, mixed and
                    lower. Scope: 4 conditions (`none`, `ast_compact`,
                    `structural`, `structural_required`) x 1 model
                    (Nemotron-3-Super only, via TARGET_ISSUES_MODELS)
                    -- deliberately spans all three structural delivery
                    mechanisms plus baseline, since the finding is that
                    the *structural* signal itself is causal regardless
                    of how it's delivered, not that one specific
                    condition is.
  - localstack/2   -- added 2026-08-09. A genuinely unexplained
                    condition-level swing for DeepSeek-V4-Flash across
                    all 12 conditions, checked and only partially
                    resolved so far. A dataset-wide check (all 4
                    models, all 6,480 trials) established the general
                    mechanism: every max_turns trial gets one forced
                    final-answer re-ask, and recovery is near-binary on
                    whether the model complies (DeepSeek complies
                    47% of the time dataset-wide; ~100% recovery when
                    compliant, ~0% when not). That explains WHY
                    max_turns trials swing between full recovery and
                    total loss, but not WHY compliance itself varies so
                    much by condition on this specific issue: `ast_compact`
                    (structural context) avoids hitting max_turns
                    altogether (0/3), directly explained by content --
                    the injected map literally lists `check_content_md5
                    (data, headers) L884`, the exact fix function, an
                    almost one-to-one match to the issue's own title.
                    `cochange` complies/recovers cleanly (3/3, f1=1.0
                    every rep) despite hitting max_turns just as often
                    as most other conditions (2/3) -- but checked
                    directly and this is NOT explained by delivered
                    content the way structural's is: cochange's own
                    partner list for s3_listener.py (common.py 26x,
                    generic_proxy.py 20x, aws_stack.py 18x) has no
                    obvious thematic connection to the MD5 bug, and
                    the file was already touched in every trial
                    regardless of condition, so discovery isn't the
                    difference either. `freq` gets neither benefit
                    (max_turns 3/3, compliant only 1/3, and that one
                    still pads with a wrong file). All 12 conditions
                    requested specifically because the pattern doesn't
                    resolve into a single clean story the way the other
                    targets here do -- worth the full sweep to see
                    whether a condition-level compliance-rate pattern
                    holds up at n=15/cell or dissolves into noise once
                    the sample is large enough to trust.

Purpose (per conversation 2026-08-04): more reps can settle whether a
delta_f1 is real (a genuine causal effect of map/tool presence on
behavior), even if it isn't content-mediated -- that's a different,
narrower question than "did the transcript show the model citing map
content." What more reps alone can't do is say *which* mediation
pathway is operating; that still needs the transcripts, now checked
systematically across the larger sample rather than a handful of
cherry-picked best-looking cells.

Deliberately hard-scoped to exactly these (repo, issue_idx) pairs, and a
SEPARATE results-base from the main study (default
.../replication_check_results, not .../results) -- explicit user
instruction: "treat this as a separate test, not mix the data in with
the rest." None of this project's existing analysis tooling
(compile_results.py, rank_issues_by_map_effect*.py,
case_study_analysis.py) points at this directory, so it cannot
contaminate any existing table without a deliberate, separate step.

(A wider 5-condition-per-issue variant for keras/5 and localstack/19 --
all three Study 1 injection types plus all_tools_required, dropping
each issue's Study 2 pick -- was tried and reverted 2026-08-05; those
two issues are back to the original one-condition-per-study design.
gpt-engineer/9 gets the full 12-condition treatment instead, per above.)

The harness itself has no --logs-base flag -- its per-trial .jsonl
transcript log (raw provider API responses, including per-turn token
usage under each entry's "usage" field) always writes to this repo's
own logs/ directory, regardless of --results-base. That data is not
cosmetic: notebooks/study_comparison_by_map_type.ipynb's
extract_trajectory() reads exactly this file, for exactly this field,
to build the cumulative-token-usage trajectory plots -- confirmed by
inspection 2026-08-05. The real per-study logs live at study_1/logs/,
study_2/logs/, study_3/logs/ (a one-time migration out of the harness's
default bare logs/ location, mirroring the same consolidation
compile_results.py's comments describe for results/). To keep this
test's logs out of both the bare logs/ tree AND that migrated
location -- so a future "clean up logs/" pass can't ever sweep this
test's files into the real per-study log tree the notebook reads --
every trial's .jsonl is moved (not copied) out of the harness's default
write location and into a separate, parallel replication_check_logs/
tree (--logs-base) immediately after the trial succeeds, so the shared
logs/ directory never accumulates anything from this test at all.

New reps are numbered starting at 4 (not 1) so that if these ever *are*
merged into the main results tree later, they can't silently collide
with or overwrite the original rep1-3.

Usage:
    python3 scripts/run_replication_check.py --dry-run

    python3 scripts/run_replication_check.py \
        --repos-base /home/afb225/study1/repos \
        --maps-base /home/afb225/study1/repo_maps \
        --results-base /home/afb225/study1/replication_check_results

    # Parallelize across worker clones (same pattern as
    # rerun_corrected_issues.py -- concurrent trials against the SAME
    # repo clone are unsafe, different repo clones are fine):
    python3 scripts/run_replication_check.py --repo keras --worker-id 1 &
    python3 scripts/run_replication_check.py --repo localstack --worker-id 2 &
    python3 scripts/run_replication_check.py --repo gpt-engineer --worker-id 3 &
    wait
"""
import argparse
import datetime
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repo_config import REPO_DIR_MAP

_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_DIR = os.path.join(_ROOT, "harness")
# Where the harness itself (hardcoded, no CLI override) always writes each
# trial's raw .jsonl transcript log -- NOT the same as study_1/logs/ etc.,
# which is a one-time-migrated copy of this same bare directory from the
# original study batches. See module docstring.
HARNESS_LOGS_DIR = os.path.join(_ROOT, "logs")

REPO_TO_FOLDER = {repo: os.path.basename(path) for repo, path in REPO_DIR_MAP.items()}

DEFAULT_REPOS_BASE   = "/home/afb225/study1/repos"
DEFAULT_MAPS_BASE    = "/home/afb225/study1/repo_maps"
DEFAULT_RESULTS_BASE = "/home/afb225/study1/replication_check_results"
DEFAULT_LOGS_BASE    = "/home/afb225/study1/replication_check_logs"

# Any location this script must refuse to write logs into -- the bare
# harness default (would still mix with a future real-study batch run from
# the same checkout) and every real per-study log location.
FORBIDDEN_LOGS_BASE_SUFFIXES = (
    "study1/logs", "study_1/logs", "study_2/logs", "study_3/logs", os.path.join("final_project", "logs"),
)

MODELS = [
    "mistral/ministral-3b-latest",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
    "deepseek/deepseek-v4-flash",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
]

# Extra reps only -- existing rep1-3 in the main results tree are
# untouched and not read by this script at all.
N_EXTRA_REPS = 12
REPS = list(range(4, 4 + N_EXTRA_REPS))  # rep4 .. rep15 -> n=15 total/cell once combined

TURN_LIMIT = 30  # matches the rest of the study (DEVLOG 2026-07-22)

# condition -> (harness script path, extra CLI args, required index/map
# file(s) relative to {maps_base}/{repo}/{issue_idx}/) -- same table as
# scripts/rerun_corrected_issues.py, trimmed to the subset actually used
# below.
CONDITIONS = {
    "none":              (os.path.join(HARNESS_DIR, "run_trial.py"), ["--map", "none"], []),
    "ast_compact":       (os.path.join(HARNESS_DIR, "run_trial.py"), ["--map", "ast_compact"], ["compact_map_pruned_55k.txt"]),
    "freq":              (os.path.join(HARNESS_DIR, "run_trial.py"), ["--map", "freq"], ["freq_map_pruned_55k.txt"]),
    "cochange":          (os.path.join(HARNESS_DIR, "run_trial.py"), ["--map", "cochange"], ["cochange_map_pruned_55k.txt"]),

    "structural":         (os.path.join(HARNESS_DIR, "run_trial_structural.py"), [], ["ast_index_full.json"]),
    "temporal_frequency": (os.path.join(HARNESS_DIR, "run_trial_temporal_frequency.py"), [], ["freq_index_full.json"]),
    "temporal_cochange":  (os.path.join(HARNESS_DIR, "run_trial_temporal_cochange.py"), [], ["cochange_index_full.json"]),
    "all_tools":          (os.path.join(HARNESS_DIR, "run_trial_all_tools.py"), [],
                            ["ast_index_full.json", "freq_index_full.json", "cochange_index_full.json"]),

    "structural_required":         (os.path.join(HARNESS_DIR, "run_trial_structural_required.py"), [], ["ast_index_full.json"]),
    "temporal_frequency_required": (os.path.join(HARNESS_DIR, "run_trial_temporal_frequency_required.py"), [], ["freq_index_full.json"]),
    "temporal_cochange_required":  (os.path.join(HARNESS_DIR, "run_trial_temporal_cochange_required.py"), [], ["cochange_index_full.json"]),
    "all_tools_required":          (os.path.join(HARNESS_DIR, "run_trial_all_tools_required.py"), [],
                                     ["ast_index_full.json", "freq_index_full.json", "cochange_index_full.json"]),
}

ALL_CONDITIONS = list(CONDITIONS.keys())

# Per issue: keras/5 and localstack/19 keep the original 4-condition
# design (baseline + each study's single strongest pooled_mean_delta_f1
# condition, read from data/issue_map_effect_ranking.csv / _study2.csv /
# _study3.csv, 2026-08-04) -- reverted to this 2026-08-05 after briefly
# trying a wider 5-condition variant (see module docstring).
#
# gpt-engineer/9 (added 2026-08-06) gets all 12 conditions instead: its
# finding is "every condition hurts" (negative pooled_mean_delta_f1 in
# 11/11 tested conditions across all three studies), not one standout
# condition, so a single-representative-per-study design would
# under-test the actual claim.
#
# scikit-learn/45 (added 2026-08-08) is narrower still: just 2
# conditions (baseline, freq) -- see TARGET_ISSUES_MODELS below for why
# it's also restricted to one model. The finding here (entry #41) is a
# single clean (model, condition) cell actively harmed by wholesale
# frequency-map injection specifically, with every other model in the
# identical condition, and Ministral itself under every other condition
# including the tool-based delivery of the SAME frequency data, already
# confirmed at 3/3 -- baseline and freq are the only two cells that
# need more reps to confirm the effect; every other cell already has a
# clean, consistent n=3 result that doesn't need re-testing.
#
# requests/12 (added 2026-08-08) tests a different question than the
# other four: not "is this delta real" but "does the pattern track
# which conditions actually carry the relevant content." All 3 Study 1
# context conditions plus baseline are included (not just one winner)
# specifically so the freq/ast_compact/cochange gradient itself -- not
# just a single condition vs. baseline -- can be checked at higher n.
#
# flask/18 (added 2026-08-08) tests reproducibility of entry #46's
# directly-traced tool-content-driven mechanism (lookup_structure
# returning app.py's logger property at line 655, Nemotron immediately
# reading that exact offset). Spans all three "structural" delivery
# mechanisms plus baseline, since the finding is that the structural
# signal itself is causal regardless of delivery, not one specific
# condition.
#
# localstack/2 (added 2026-08-09) gets ALL 12 conditions -- unlike
# every other single-model target here, this one doesn't resolve into
# one clean mechanism. ast_compact's advantage is content-explained
# (the injected map directly names the fix function); cochange's
# advantage is checked and NOT content-explained (its delivered partner
# list has no thematic connection to the bug, and the file was already
# touched regardless of condition); freq gets neither benefit. The full
# sweep is specifically to see whether DeepSeek's per-condition forced-
# answer compliance rate is a real, stable pattern at n=15/cell or
# dissolves into noise -- deliberately not narrowed to a hypothesis
# that isn't settled yet.
TARGET_ISSUES_CONDITIONS = {
    ("keras", 5): ["none", "freq", "temporal_frequency", "all_tools_required"],
    ("localstack", 19): ["none", "ast_compact", "temporal_frequency", "all_tools_required"],
    ("gpt-engineer", 9): ALL_CONDITIONS,
    ("scikit-learn", 45): ["none", "freq"],
    ("requests", 12): ["none", "freq", "ast_compact", "cochange"],
    ("flask", 18): ["none", "ast_compact", "structural", "structural_required"],
    ("localstack", 2): ALL_CONDITIONS,
}

# Per-issue model restriction -- defaults to all 4 (MODELS) when an
# issue isn't listed here. scikit-learn/45's finding (entry #41) is
# specifically that Ministral-3B, and only Ministral-3B, misses under
# freq context (every other model already confirmed 3/3 correct in that
# exact condition at n=3) -- running the other 3 models here would just
# re-confirm a result that isn't in question and burn budget for
# nothing. requests/12's finding (entry #44) is specifically about
# DeepSeek-V4-Flash's touch-vs-kept behavior on requests/api.py -- the
# other 3 models weren't part of the observed pattern and aren't in
# scope here. flask/18's finding (entry #46) is specifically about
# Nemotron-3-Super's tool-content-driven reads of app.py -- the other 3
# models weren't part of the observed pattern. localstack/2's finding
# is specifically about DeepSeek-V4-Flash's turn-exhaustion/compliance
# behavior -- the other 3 models are already solid-to-perfect at n=3
# on this issue (gpt-oss exact-match 36/36) and aren't in scope.
TARGET_ISSUES_MODELS = {
    ("scikit-learn", 45): ["mistral/ministral-3b-latest"],
    ("requests", 12): ["deepseek/deepseek-v4-flash"],
    ("flask", 18): ["deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B"],
    ("localstack", 2): ["deepseek/deepseek-v4-flash"],
}

MAX_RETRIES   = 2
RETRY_BACKOFF = 30
TRIAL_TIMEOUT = 900


def fmt_time(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def repo_path_for(repos_base, worker_id, repo):
    folder = REPO_TO_FOLDER.get(repo)
    if folder is None:
        raise ValueError(f"No known repo folder for '{repo}' — not in REPO_DIR_MAP")
    return os.path.join(repos_base, f"worker_{worker_id}", folder)


def result_path_for(results_base, safe_model, repo, issue_idx, condition, rep):
    return os.path.join(results_base, safe_model, repo, str(issue_idx), condition, f"rep{rep}.json")


def harness_log_path_for(safe_model, repo, issue_idx, condition, rep):
    """Where the harness itself actually wrote this trial's .jsonl -- always
    under this repo's bare logs/, since the harness has no --logs-base
    flag. Matches harness/run_trial.py's own logs_dir construction exactly
    (verified against source, 2026-08-05) -- and identically for the
    tool-based harnesses, whose hardcoded CONDITION constant equals the
    same condition string used everywhere else in this script."""
    return os.path.join(HARNESS_LOGS_DIR, safe_model, repo, str(issue_idx), condition, f"rep{rep}.jsonl")


def isolated_log_path_for(logs_base, safe_model, repo, issue_idx, condition, rep):
    return os.path.join(logs_base, safe_model, repo, str(issue_idx), condition, f"rep{rep}.jsonl")


def prune_empty_dirs_up_to(leaf_dir, stop_at):
    """After moving a file out of leaf_dir, remove leaf_dir and any now-empty
    parent directories, stopping at (and never removing) stop_at itself --
    keeps the shared harness logs/ tree from accumulating empty condition/
    issue/repo/model directory skeletons after every trial's .jsonl is
    moved out."""
    d = leaf_dir
    stop_at = os.path.abspath(stop_at)
    while os.path.abspath(d) != stop_at and os.path.isdir(d) and not os.listdir(d):
        parent = os.path.dirname(d)
        os.rmdir(d)
        d = parent


def missing_files(maps_base, repo, issue_idx, filenames):
    issue_dir = os.path.join(maps_base, repo, str(issue_idx))
    return [f for f in filenames if not os.path.exists(os.path.join(issue_dir, f))]


def build_trial_list(args):
    trials = []
    skipped_existing = 0
    skipped_missing_map = 0

    all_issues = list(TARGET_ISSUES_CONDITIONS.keys())
    issues = all_issues if args.repo is None else [t for t in all_issues if t[0] == args.repo]
    reps = REPS if args.rep is None else [args.rep]

    for repo, issue_idx in issues:
        # Per-issue model restriction (see TARGET_ISSUES_MODELS), further
        # narrowed by --model if given.
        issue_models = TARGET_ISSUES_MODELS.get((repo, issue_idx), MODELS)
        models = issue_models if args.model is None else [args.model] if args.model in issue_models else []
        if not models and args.model is not None:
            print(f"WARNING: --model {args.model} is not in scope for {repo}/{issue_idx} "
                  f"(restricted to {issue_models}) -- skipping", file=sys.stderr)
            continue
        for condition in TARGET_ISSUES_CONDITIONS[(repo, issue_idx)]:
            _, _, required_files = CONDITIONS[condition]
            missing = missing_files(args.maps_base, repo, issue_idx, required_files)
            if missing:
                print(f"WARNING: missing map file(s) for {repo}/{issue_idx}/{condition}: {missing}",
                      file=sys.stderr)
                skipped_missing_map += len(models) * len(reps)
                continue
            for model in models:
                safe_model = model.replace("/", "_")
                for rep in reps:
                    result_path = result_path_for(
                        args.results_base, safe_model, repo, issue_idx, condition, rep)
                    if os.path.exists(result_path):
                        skipped_existing += 1
                        continue
                    trials.append({
                        "repo": repo, "issue_idx": issue_idx,
                        "condition": condition, "model": model, "rep": rep,
                    })
    return trials, skipped_existing, skipped_missing_map


def main():
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worker-id", type=int, default=1, choices=[1, 2, 3, 4, 5],
                         help="Which repos-base/worker_<N>/ clone to check out against (default: 1)")
    parser.add_argument("--repo", choices=[t[0] for t in TARGET_ISSUES_CONDITIONS], default=None,
                         help="Restrict to one of the two flagged repos (for safe parallel runs)")
    parser.add_argument("--model", choices=MODELS, default=None,
                         help="Restrict to one model (default: all 4)")
    parser.add_argument("--rep", type=int, choices=REPS, default=None,
                         help=f"Restrict to one rep (default: all of rep4..rep{3+N_EXTRA_REPS})")
    parser.add_argument("--repos-base",   default=DEFAULT_REPOS_BASE)
    parser.add_argument("--maps-base",    default=DEFAULT_MAPS_BASE)
    parser.add_argument("--results-base", default=DEFAULT_RESULTS_BASE,
                         help="Deliberately separate from the main study's results-base -- "
                              "do not point this at .../study1/results")
    parser.add_argument("--logs-base", default=DEFAULT_LOGS_BASE,
                         help="Where each trial's .jsonl transcript log is moved to immediately "
                              "after the trial succeeds (the harness itself always writes it to "
                              "this repo's bare logs/ first -- no CLI override exists there). "
                              "Deliberately separate from every real per-study log location.")
    parser.add_argument("--max-turns", type=int, default=TURN_LIMIT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if os.path.abspath(args.results_base).rstrip("/").endswith("study1/results"):
        raise SystemExit(
            "--results-base points at the main study's results directory -- refusing to run. "
            "This check is meant to stay separate from the main dataset (see module docstring)."
        )
    normalized_logs_base = os.path.abspath(args.logs_base).rstrip("/")
    if any(normalized_logs_base.endswith(suffix) for suffix in FORBIDDEN_LOGS_BASE_SUFFIXES):
        raise SystemExit(
            f"--logs-base ({args.logs_base}) resolves to a real study log location -- refusing "
            "to run. This check is meant to stay separate from the main dataset (see module docstring)."
        )

    trials, skipped_existing, skipped_missing_map = build_trial_list(args)

    total = len(trials)
    print("=" * 72)
    print(f"REPLICATION CHECK: keras/5 (suspected false positive), localstack/19 "
          f"(verified comparison case), gpt-engineer/9 (all 12 conditions, "
          f"11/11 negative)  worker={args.worker_id}")
    print(f"Target issues x conditions: {TARGET_ISSUES_CONDITIONS if args.repo is None else {k: v for k, v in TARGET_ISSUES_CONDITIONS.items() if k[0] == args.repo}}")
    print(f"Models: {MODELS if args.model is None else [args.model]}")
    print(f"Reps: {REPS if args.rep is None else [args.rep]} (extra, on top of existing rep1-3 "
          f"in the main results tree, which this script never reads or writes)")
    print(f"Trials to run: {total}  "
          f"(skipped: {skipped_existing} already done, {skipped_missing_map} missing map)")
    print(f"Max turns: {args.max_turns}")
    print(f"Repos base:   {args.repos_base}")
    print(f"Maps base:    {args.maps_base}")
    print(f"Results base: {args.results_base}  (SEPARATE from the main study)")
    print(f"Logs base:    {args.logs_base}  (SEPARATE from the main study; each trial's .jsonl "
          f"is moved here immediately after it succeeds)")
    print("=" * 72)

    if args.dry_run:
        for t in trials:
            print(f"  would run: {t['repo']}/{t['issue_idx']}/{t['condition']}/{t['model']}/rep{t['rep']}")
        print(f"\n(dry run, {total} trials would execute, nothing was run)")
        return

    date_str = datetime.date.today().isoformat()
    os.makedirs(HARNESS_LOGS_DIR, exist_ok=True)
    batch_log_path = os.path.join(HARNESS_LOGS_DIR, f"replication_check_{args.worker_id}_{date_str}.log")
    log_lines = []

    def log(msg=""):
        print(msg)
        log_lines.append(msg)

    succeeded, failures = 0, []
    batch_start = time.time()

    for i, trial in enumerate(trials):
        repo, issue_idx = trial["repo"], trial["issue_idx"]
        condition, model, rep = trial["condition"], trial["model"], trial["rep"]
        harness, extra_args, _ = CONDITIONS[condition]
        repo_path = repo_path_for(args.repos_base, args.worker_id, repo)

        elapsed = time.time() - batch_start
        eta = f" | ETA ~{fmt_time((elapsed / i) * (total - i))}" if i else ""
        log(f"[{i+1}/{total}] {repo}/{issue_idx}/{condition}/{model}/rep{rep}"
            f" — running... (elapsed {fmt_time(elapsed)}{eta})")

        cmd = [sys.executable, harness,
               "--model",        model,
               "--repo-path",    repo_path,
               "--issue-idx",    str(issue_idx),
               "--rep",          str(rep),
               "--worker-id",    str(args.worker_id),
               "--max-turns",    str(args.max_turns),
               "--maps-base",    args.maps_base,
               "--results-base", args.results_base] + extra_args

        attempt, trial_ok, last_reason = 0, False, ""
        trial_start = time.time()
        while attempt <= MAX_RETRIES:
            if attempt > 0:
                log(f"    retry {attempt}/{MAX_RETRIES} after {RETRY_BACKOFF}s …")
                time.sleep(RETRY_BACKOFF)
            try:
                proc = subprocess.run(cmd, timeout=TRIAL_TIMEOUT)
                if proc.returncode != 0:
                    last_reason = f"exit code {proc.returncode}"
                    attempt += 1
                else:
                    trial_ok = True
                    break
            except subprocess.TimeoutExpired:
                last_reason = f"timeout ({TRIAL_TIMEOUT}s)"
                attempt += 1
            except Exception as exc:
                last_reason = str(exc)
                attempt += 1

        trial_elapsed = time.time() - trial_start
        if trial_ok:
            succeeded += 1
            log(f">>> OK in {trial_elapsed:.0f}s")

            safe_model = model.replace("/", "_")
            src_log = harness_log_path_for(safe_model, repo, issue_idx, condition, rep)
            dst_log = isolated_log_path_for(args.logs_base, safe_model, repo, issue_idx, condition, rep)
            if os.path.exists(src_log):
                os.makedirs(os.path.dirname(dst_log), exist_ok=True)
                shutil.move(src_log, dst_log)
                prune_empty_dirs_up_to(os.path.dirname(src_log), HARNESS_LOGS_DIR)
                log(f"    moved log -> {dst_log}")
            else:
                log(f"    WARNING: expected log not found at {src_log} -- nothing moved")
        else:
            failures.append({**trial, "reason": last_reason})
            log(f">>> FAILED after {attempt} attempt(s): {last_reason}")
        log()

    total_elapsed = time.time() - batch_start
    log("=" * 72)
    log("SUMMARY")
    log(f"  Attempted   {total}")
    log(f"  Succeeded   {succeeded}")
    log(f"  Failed      {len(failures)}")
    log(f"  Time        {fmt_time(total_elapsed)}"
        + (f"  (avg {total_elapsed/total:.0f}s/trial)" if total else ""))
    if failures:
        log()
        log("  Failures:")
        for f in failures:
            log(f"    {f['repo']}/{f['issue_idx']}/{f['condition']}/{f['model']}/rep{f['rep']}: {f['reason']}")
    log("=" * 72)

    with open(batch_log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    print(f"\nLog saved -> {batch_log_path}")


if __name__ == "__main__":
    main()
