"""
Run a full batch of file-localisation trials for one (worker, rep, model)
combination: every issue in issue_selection_final.csv, across all four map
conditions (none, ast_compact, freq, cochange).

Trials whose result file already exists are skipped (safe to re-run after
a partial batch). Trials for a non-none map condition whose map file is
missing are skipped with a warning rather than failing.

Usage:
    python3 scripts/run_batch.py --worker-id 1 --rep 1 \
        --model deepseek/deepseek-v4-flash

    python3 scripts/run_batch.py --worker-id 2 --rep 1 \
        --model claude-sonnet-4-6 \
        --repos-base /home/afb225/study1/repos \
        --maps-base /home/afb225/study1/repo_maps \
        --results-base /home/afb225/study1/results
"""
import argparse
import datetime
import json
import os
import random
import subprocess
import sys
import time

import pandas as pd

_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(_ROOT, "harness", "run_trial.py")
SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")
LOGS_DIR = os.path.join(_ROOT, "logs")

DEFAULT_REPOS_BASE   = "/home/afb225/study1/repos"
DEFAULT_MAPS_BASE    = "/home/afb225/study1/repo_maps"
DEFAULT_RESULTS_BASE = "/home/afb225/study1/results"

MAP_CONDITIONS = ["none", "ast_compact", "freq", "cochange"]

# Mirrors harness/run_trial.py's MAP_FILES — kept in sync manually since the
# two scripts intentionally have no import-time dependency on each other
# (run_batch.py only invokes run_trial.py as a subprocess).
MAP_FILES = {
    "ast_compact": "compact_map_pruned_55k.txt",
    "freq":        "freq_map_pruned_55k.txt",
    "cochange":    "cochange_map_pruned_55k.txt",
}

MAX_RETRIES   = 2
RETRY_BACKOFF = 30   # seconds between retries
TRIAL_TIMEOUT = 900  # seconds hard ceiling per attempt


def fmt_time(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def repo_path_for(repos_base, worker_id, repo):
    return os.path.join(repos_base, f"worker_{worker_id}", f"{repo}_full")


def map_file_for(maps_base, repo, issue_idx, map_type):
    filename = MAP_FILES.get(map_type)
    if filename is None:
        return None
    return os.path.join(maps_base, repo, str(issue_idx), filename)


def result_path_for(results_base, safe_model, repo, issue_idx, map_type, rep):
    return os.path.join(results_base, safe_model, repo, str(issue_idx), map_type, f"rep{rep}.json")


def load_result(path):
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_trial_list(issues, args, safe_model):
    """Return (trials, n_skipped_existing, n_skipped_missing_map)."""
    trials = []
    skipped_existing = 0
    skipped_missing_map = 0

    for _, row in issues.iterrows():
        repo, issue_idx = row["repo"], int(row["issue_idx"])
        for map_type in MAP_CONDITIONS:
            result_path = result_path_for(
                args.results_base, safe_model, repo, issue_idx, map_type, args.rep)
            if os.path.exists(result_path):
                skipped_existing += 1
                continue

            if map_type != "none":
                map_path = map_file_for(args.maps_base, repo, issue_idx, map_type)
                if not os.path.exists(map_path):
                    print(f"WARNING: map file missing, skipping {repo}/{issue_idx}/{map_type}: "
                          f"{map_path}", file=sys.stderr)
                    skipped_missing_map += 1
                    continue

            trials.append({"repo": repo, "issue_idx": issue_idx, "map_type": map_type})

    return trials, skipped_existing, skipped_missing_map


def main():
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(
        description="Run a full batch of trials for one worker/rep/model")
    parser.add_argument("--worker-id", type=int, required=True, choices=[1, 2, 3, 4, 5])
    parser.add_argument("--rep",       type=int, required=True)
    parser.add_argument("--model",     required=True)
    parser.add_argument("--repos-base",   default=DEFAULT_REPOS_BASE)
    parser.add_argument("--maps-base",    default=DEFAULT_MAPS_BASE)
    parser.add_argument("--results-base", default=DEFAULT_RESULTS_BASE)
    parser.add_argument("--turn-limit", type=int, default=20,
                        help="Max agent turns per trial, forwarded to run_trial.py (default: 20)")
    args = parser.parse_args()

    safe_model = args.model.replace("/", "_")
    issues = pd.read_csv(SEL_CSV)

    trials, skipped_existing, skipped_missing_map = build_trial_list(issues, args, safe_model)

    seed = args.worker_id * 1000 + args.rep
    random.seed(seed)
    random.shuffle(trials)

    total = len(trials)
    date_str = datetime.date.today().isoformat()
    os.makedirs(LOGS_DIR, exist_ok=True)
    batch_log_path = os.path.join(
        LOGS_DIR, f"batch_{args.worker_id}_{args.rep}_{safe_model}_{date_str}.log")

    log_lines = []

    def log(msg=""):
        print(msg)
        log_lines.append(msg)

    log("=" * 72)
    log(f"BATCH  worker={args.worker_id} rep={args.rep} model={args.model}")
    log(f"Issues: {len(issues)}   Map conditions: {MAP_CONDITIONS}")
    log(f"Trials to run: {total}   "
        f"(skipped: {skipped_existing} already done, {skipped_missing_map} missing map)")
    log(f"Seed: {seed}   Turn limit: {args.turn_limit}")
    log(f"Repos base:   {args.repos_base}")
    log(f"Maps base:    {args.maps_base}")
    log(f"Results base: {args.results_base}")
    log("=" * 72)
    log()

    succeeded     = 0
    failures      = []
    total_in_tok  = 0
    total_out_tok = 0
    total_cached  = 0
    total_cost    = 0.0
    stop_reasons  = {}
    batch_start   = time.time()

    for i, trial in enumerate(trials):
        repo, issue_idx, map_type = trial["repo"], trial["issue_idx"], trial["map_type"]
        repo_path = repo_path_for(args.repos_base, args.worker_id, repo)

        elapsed = time.time() - batch_start
        eta_str = ""
        if succeeded > 0:
            avg_s = elapsed / (i if i else 1)
            eta_str = f" | ETA ~{fmt_time(avg_s * (total - i))}"
        log(f"[{i+1}/{total}] {repo}/{issue_idx}/{map_type}/rep{args.rep}"
            f" — running... (elapsed {fmt_time(elapsed)}{eta_str})")

        cmd = [sys.executable, HARNESS,
               "--model",        args.model,
               "--repo-path",    repo_path,
               "--issue-idx",    str(issue_idx),
               "--map",          map_type,
               "--rep",          str(args.rep),
               "--worker-id",    str(args.worker_id),
               "--max-turns",    str(args.turn_limit),
               "--maps-base",    args.maps_base,
               "--results-base", args.results_base]

        trial_start = time.time()
        attempt = 0
        trial_ok = False
        last_reason = ""
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
            result_path = result_path_for(
                args.results_base, safe_model, repo, issue_idx, map_type, args.rep)
            res = load_result(result_path)
            if res:
                m = res.get("metrics", {})
                total_in_tok  += m.get("total_input_tokens", 0) or 0
                total_out_tok += m.get("total_output_tokens", 0) or 0
                total_cached  += m.get("total_cached_tokens", 0) or 0
                total_cost    += m.get("total_cost", 0.0) or 0.0
                sr = m.get("stop_reason", "unknown")
                stop_reasons[sr] = stop_reasons.get(sr, 0) + 1
            else:
                log(f"    WARNING: result file not found after successful run: {result_path}")
            succeeded += 1
            log(f">>> OK in {trial_elapsed:.0f}s")
        else:
            failures.append({
                "repo": repo, "issue_idx": issue_idx, "map_type": map_type,
                "reason": last_reason,
            })
            log(f">>> FAILED after {attempt} attempt(s): {last_reason}")
        log()

    total_elapsed = time.time() - batch_start

    log("=" * 72)
    log("BATCH SUMMARY")
    log(f"  Attempted   {total}")
    log(f"  Succeeded   {succeeded}")
    log(f"  Failed      {len(failures)}")
    log(f"  Skipped     {skipped_existing + skipped_missing_map}  "
        f"({skipped_existing} already done, {skipped_missing_map} missing map)")
    log(f"  Tokens      {total_in_tok:,} in / {total_out_tok:,} out / {total_cached:,} cached")
    log(f"  Cost        ${total_cost:.4f}")
    if total:
        log(f"  Time        {fmt_time(total_elapsed)}  (avg {total_elapsed/total:.0f}s/trial)")
    else:
        log("  Time        0s (nothing to run)")
    log()
    log("  Stop reasons:")
    for sr, count in sorted(stop_reasons.items(), key=lambda x: -x[1]):
        pct = 100 * count / succeeded if succeeded else 0
        log(f"    {sr:<15s} {count:4d}  ({pct:.0f}%)")
    if failures:
        log()
        log("  Failures:")
        for fail in failures:
            log(f"    {fail['repo']}/{fail['issue_idx']}/{fail['map_type']}: {fail['reason']}")
    log("=" * 72)

    with open(batch_log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    print(f"\nBatch log saved -> {batch_log_path}")


if __name__ == "__main__":
    main()
