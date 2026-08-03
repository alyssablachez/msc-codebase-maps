"""
Re-run all 12 conditions x 4 models x 3 reps for the two issues whose
base_commit was found to be wrong (the fix commit's own hash instead of its
parent -- see data/model_failure_points.md entry #17). Every prior trial for
these two issues explored an already-fixed codebase and is invalid.

Deliberately hard-scoped to exactly these two (repo, issue_idx) pairs --
NOT driven from issue_selection_final.csv like run_batch*.py -- so there is
no risk of this script touching any of the other 43 issues' results.

base_commit has already been corrected in this repo's data/issue_selection_final.csv
and data/all_issues_with_pr_commit_comment_all_project_0922.pkl, and
repo_maps/thefuck/10/ and repo_maps/stable-diffusion-webui/5/ have already
been regenerated from the corrected commits (both steps done locally, not by
this script). Before running this on the native machine:

  1. Sync the corrected data: either `git pull` if /home/afb225/study1 is a
     clone of this repo, or manually copy over:
       - data/issue_selection_final.csv
       - data/all_issues_with_pr_commit_comment_all_project_0922.pkl (only
         needed if you regenerate maps there too; not needed if you just
         copy the already-regenerated repo_maps/ directories below)
       - repo_maps/thefuck/10/  (all files)
       - repo_maps/stable-diffusion-webui/5/  (all files)
  2. Clear the stale results/logs for these 2 issues from your results_base
     and its logs equivalent (mirroring what was done in this repo -- moved
     aside, not deleted, to stale_results_wrong_base_commit_<date>/). This
     script's own skip-if-exists check means it will silently do nothing if
     stale results are still sitting there.
  3. Confirm your repo clones (thefuck_full, stable_diffusion_webui_full)
     under repos_base/worker_<N>/ are on their default branch and clean
     (`git status`) before starting -- the harness checks out --detach and
     restores automatically, but a dirty tree beforehand will interfere.

Usage:
    python3 scripts/rerun_corrected_issues.py --dry-run

    python3 scripts/rerun_corrected_issues.py \
        --repos-base /home/afb225/study1/repos \
        --maps-base /home/afb225/study1/repo_maps \
        --results-base /home/afb225/study1/results

    # Restrict to one model/repo (e.g. to run two repos in parallel safely
    # on different worker IDs -- concurrent trials against the SAME repo
    # clone are unsafe, different repo clones are fine):
    python3 scripts/rerun_corrected_issues.py --repo thefuck --worker-id 1 &
    python3 scripts/rerun_corrected_issues.py --repo stable-diffusion-webui --worker-id 2 &
"""
import argparse
import datetime
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from repo_config import REPO_DIR_MAP

_ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS_DIR = os.path.join(_ROOT, "harness")
LOGS_DIR    = os.path.join(_ROOT, "logs")

REPO_TO_FOLDER = {repo: os.path.basename(path) for repo, path in REPO_DIR_MAP.items()}

DEFAULT_REPOS_BASE   = "/home/afb225/study1/repos"
DEFAULT_MAPS_BASE    = "/home/afb225/study1/repo_maps"
DEFAULT_RESULTS_BASE = "/home/afb225/study1/results"

# The two corrected issues. Ground truth for why these were wrong, and the
# corrected base_commit values, is in data/model_failure_points.md entry #17.
TARGET_ISSUES = [
    ("thefuck", 10),
    ("stable-diffusion-webui", 5),
]

MODELS = [
    "mistral/ministral-3b-latest",
    "fireworks_ai/accounts/fireworks/models/gpt-oss-120b",
    "deepseek/deepseek-v4-flash",
    "deepinfra/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B",
]

REPS = [1, 2, 3]

TURN_LIMIT = 30  # Study convention (see DEVLOG 2026-07-22) -- NOT the
                  # individual harness scripts' own --max-turns default of 20.

# condition -> (harness script path, extra CLI args beyond the shared set,
# required index/map file(s) relative to {maps_base}/{repo}/{issue_idx}/)
CONDITIONS = {
    "none":         (os.path.join(HARNESS_DIR, "run_trial.py"), ["--map", "none"], []),
    "ast_compact":  (os.path.join(HARNESS_DIR, "run_trial.py"), ["--map", "ast_compact"], ["compact_map_pruned_55k.txt"]),
    "freq":         (os.path.join(HARNESS_DIR, "run_trial.py"), ["--map", "freq"], ["freq_map_pruned_55k.txt"]),
    "cochange":     (os.path.join(HARNESS_DIR, "run_trial.py"), ["--map", "cochange"], ["cochange_map_pruned_55k.txt"]),

    "structural":         (os.path.join(HARNESS_DIR, "run_trial_structural.py"), [], ["ast_index_full.json"]),
    "temporal_frequency":  (os.path.join(HARNESS_DIR, "run_trial_temporal_frequency.py"), [], ["freq_index_full.json"]),
    "temporal_cochange":   (os.path.join(HARNESS_DIR, "run_trial_temporal_cochange.py"), [], ["cochange_index_full.json"]),
    "all_tools":           (os.path.join(HARNESS_DIR, "run_trial_all_tools.py"), [],
                             ["ast_index_full.json", "freq_index_full.json", "cochange_index_full.json"]),

    "structural_required":         (os.path.join(HARNESS_DIR, "run_trial_structural_required.py"), [], ["ast_index_full.json"]),
    "temporal_frequency_required": (os.path.join(HARNESS_DIR, "run_trial_temporal_frequency_required.py"), [], ["freq_index_full.json"]),
    "temporal_cochange_required":  (os.path.join(HARNESS_DIR, "run_trial_temporal_cochange_required.py"), [], ["cochange_index_full.json"]),
    "all_tools_required":          (os.path.join(HARNESS_DIR, "run_trial_all_tools_required.py"), [],
                                     ["ast_index_full.json", "freq_index_full.json", "cochange_index_full.json"]),
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


def missing_files(maps_base, repo, issue_idx, filenames):
    issue_dir = os.path.join(maps_base, repo, str(issue_idx))
    return [f for f in filenames if not os.path.exists(os.path.join(issue_dir, f))]


def build_trial_list(args):
    trials = []
    skipped_existing = 0
    skipped_missing_map = 0

    issues = TARGET_ISSUES if args.repo is None else [t for t in TARGET_ISSUES if t[0] == args.repo]
    models = MODELS if args.model is None else [args.model]

    for repo, issue_idx in issues:
        for condition, (_, _, required_files) in CONDITIONS.items():
            missing = missing_files(args.maps_base, repo, issue_idx, required_files)
            if missing:
                print(f"WARNING: missing map file(s) for {repo}/{issue_idx}/{condition}: {missing}",
                      file=sys.stderr)
                skipped_missing_map += len(models) * len(REPS)
                continue
            for model in models:
                safe_model = model.replace("/", "_")
                for rep in REPS:
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
    parser.add_argument("--repo", choices=[t[0] for t in TARGET_ISSUES], default=None,
                         help="Restrict to one of the two corrected repos (for safe parallel runs)")
    parser.add_argument("--model", choices=MODELS, default=None,
                         help="Restrict to one model (default: all 4)")
    parser.add_argument("--repos-base",   default=DEFAULT_REPOS_BASE)
    parser.add_argument("--maps-base",    default=DEFAULT_MAPS_BASE)
    parser.add_argument("--results-base", default=DEFAULT_RESULTS_BASE)
    parser.add_argument("--max-turns", type=int, default=TURN_LIMIT,
                         help=f"Forwarded to the harness as --max-turns (default: {TURN_LIMIT}, "
                              f"matching the rest of the study -- NOT the harnesses' own default of 20)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    trials, skipped_existing, skipped_missing_map = build_trial_list(args)

    total = len(trials)
    print("=" * 72)
    print(f"RE-RUN: corrected base_commit issues  worker={args.worker_id}")
    print(f"Target issues: {TARGET_ISSUES if args.repo is None else [t for t in TARGET_ISSUES if t[0] == args.repo]}")
    print(f"Models: {MODELS if args.model is None else [args.model]}")
    print(f"Trials to run: {total}  "
          f"(skipped: {skipped_existing} already done, {skipped_missing_map} missing map)")
    print(f"Max turns: {args.max_turns}")
    print(f"Repos base:   {args.repos_base}")
    print(f"Maps base:    {args.maps_base}")
    print(f"Results base: {args.results_base}")
    print("=" * 72)

    if args.dry_run:
        for t in trials:
            print(f"  would run: {t['repo']}/{t['issue_idx']}/{t['condition']}/{t['model']}/rep{t['rep']}")
        print(f"\n(dry run, {total} trials would execute, nothing was run)")
        return

    date_str = datetime.date.today().isoformat()
    os.makedirs(LOGS_DIR, exist_ok=True)
    batch_log_path = os.path.join(LOGS_DIR, f"rerun_corrected_{args.worker_id}_{date_str}.log")
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
