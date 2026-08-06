"""
Expanded-replication check for two issues flagged in
data/model_failure_points.md's case-study notes as showing a large
baseline-vs-map delta_f1 at the standard n=3 reps/cell:

  - keras/5      -- top-ranked "most helped" issue in all three studies'
                    issue_map_effect_ranking*.csv, but direct transcript
                    inspection of the best-looking cells found no
                    content-mediated map/tool usage (see the notes column
                    of data/issue_case_study_notes.csv, keras/5 row) --
                    the leading candidate false positive.
  - localstack/19 -- entry #16 in model_failure_points.md, a *verified*
                    presence-mediated effect (baseline explores the right
                    files but submits doc/README.md; any map condition
                    flips the final answer) -- included as a comparison
                    case, not because it's in doubt.

Purpose (per conversation 2026-08-04): more reps can settle whether a
delta_f1 is real (a genuine causal effect of map/tool presence on
behavior), even if it isn't content-mediated -- that's a different,
narrower question than "did the transcript show the model citing map
content." What more reps alone can't do is say *which* mediation
pathway is operating; that still needs the transcripts, now checked
systematically across the larger sample rather than a handful of
cherry-picked best-looking cells.

Deliberately hard-scoped to exactly these two (repo, issue_idx) pairs,
a curated 4-condition subset per issue (baseline + each study's single
strongest-delta condition, so the comparison is apples-to-apples across
studies), and a SEPARATE results-base from the main study (default
.../replication_check_results, not .../results) -- explicit user
instruction: "treat this as a separate test, not mix the data in with
the rest." None of this project's existing analysis tooling
(compile_results.py, rank_issues_by_map_effect*.py,
case_study_analysis.py) points at this directory, so it cannot
contaminate any existing table without a deliberate, separate step.

(A wider 5-condition-per-issue variant -- all three Study 1 injection
types plus all_tools_required, dropping each issue's Study 2 pick -- was
tried and reverted 2026-08-05; back to the original one-condition-per-
study design below.)

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
    "temporal_frequency": (os.path.join(HARNESS_DIR, "run_trial_temporal_frequency.py"), [], ["freq_index_full.json"]),
    "all_tools_required": (os.path.join(HARNESS_DIR, "run_trial_all_tools_required.py"), [],
                            ["ast_index_full.json", "freq_index_full.json", "cochange_index_full.json"]),
}

# Per issue: baseline ("none") plus that study's single strongest
# pooled_mean_delta_f1 condition, read directly from
# data/issue_map_effect_ranking.csv / _study2.csv / _study3.csv
# (2026-08-04) -- kept to 4 conditions/issue so the two issues are
# directly comparable and the extra-rep budget stays bounded (2 issues
# x 4 conditions x 4 models x 12 extra reps = 384 trials). Reverted back
# to this design 2026-08-05 after briefly trying a wider 5-condition
# variant (see module docstring). "cochange" stays in the CONDITIONS
# table above even though no target issue currently uses it -- harmless
# to leave available if the design changes again.
TARGET_ISSUES_CONDITIONS = {
    ("keras", 5): ["none", "freq", "temporal_frequency", "all_tools_required"],
    ("localstack", 19): ["none", "ast_compact", "temporal_frequency", "all_tools_required"],
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
    models = MODELS if args.model is None else [args.model]
    reps = REPS if args.rep is None else [args.rep]

    for repo, issue_idx in issues:
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
    print(f"REPLICATION CHECK: keras/5 (suspected false positive) vs "
          f"localstack/19 (verified comparison case)  worker={args.worker_id}")
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
