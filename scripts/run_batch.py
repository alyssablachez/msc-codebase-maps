"""
Run a randomised batch of file-localisation trials across experimental conditions.

Usage:
    # Full batch (75 trials: 5 tasks × 3 maps × 5 reps)
    python3 scripts/run_batch.py

    # Test run (6 trials: 1 task × 3 maps × 2 reps)
    python3 scripts/run_batch.py --tasks 0 --reps 2
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time

_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HARNESS = os.path.join(_ROOT, "harness", "run_trial.py")
RESULTS_DIR = os.path.join(_ROOT, "results")


def load_result(model, task, map_type, rep):
    safe_model = model.replace("/", "_")
    path = os.path.join(RESULTS_DIR, safe_model, f"task_{task}_{map_type}_rep{rep}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fmt_time(seconds):
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def main():
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description="Run a randomised batch of localisation trials")
    parser.add_argument("--model",  default="mistral/devstral-medium-latest")
    parser.add_argument("--tasks",  nargs="+", type=int, default=[0, 4, 12, 14, 15])
    parser.add_argument("--maps",   nargs="+", default=["none", "ast", "ast_compact"])
    parser.add_argument("--reps",   type=int,  default=5)
    parser.add_argument("--delay",  type=float, default=2.0,
                        help="Seconds to pause between trials (default: 2)")
    parser.add_argument("--seed",   type=int,  default=42,
                        help="Random seed for shuffle (default: 42)")
    parser.add_argument("--max-turns", type=int, default=20,
                        help="--max-turns forwarded to run_trial.py (default: 20)")
    args = parser.parse_args()

    combos = [
        (task, map_type, rep)
        for task in args.tasks
        for map_type in args.maps
        for rep in range(args.reps)
    ]
    random.seed(args.seed)
    random.shuffle(combos)

    total = len(combos)
    print("=" * 65)
    print(f"BATCH  {total} trials  "
          f"({len(args.tasks)} tasks × {len(args.maps)} maps × {args.reps} reps)")
    print(f"Model  {args.model}")
    print(f"Seed   {args.seed}   Delay {args.delay}s   Max-turns {args.max_turns}")
    print("=" * 65)
    print()

    failures     = []
    total_cost   = 0.0
    stop_reasons = {}
    batch_start  = time.time()
    completed    = 0

    for i, (task, map_type, rep) in enumerate(combos):
        elapsed   = time.time() - batch_start
        remaining = total - i
        eta_str   = ""
        if completed > 0:
            avg_s = elapsed / completed
            eta_s = avg_s * remaining
            eta_str = f" | ETA ~{fmt_time(eta_s)}  (avg {avg_s:.0f}s/trial)"

        print(f"─── [{i+1}/{total}] task={task} map={map_type} rep={rep} | "
              f"elapsed={fmt_time(elapsed)}{eta_str} | cost=${total_cost:.4f} ───")

        trial_start = time.time()
        try:
            proc = subprocess.run(
                [sys.executable, HARNESS,
                 "--model",     args.model,
                 "--task",      str(task),
                 "--map",       map_type,
                 "--rep",       str(rep),
                 "--max-turns", str(args.max_turns)],
                timeout=600,    # 10 min hard ceiling per trial
            )
            trial_elapsed = time.time() - trial_start

            if proc.returncode != 0:
                failures.append({
                    "task": task, "map": map_type, "rep": rep,
                    "reason": f"exit code {proc.returncode}",
                })
                print(f">>> FAILED (exit {proc.returncode}) in {trial_elapsed:.0f}s\n")
            else:
                res = load_result(args.model, task, map_type, rep)
                if res:
                    cost = res.get("metrics", {}).get("total_cost", 0.0)
                    total_cost += cost
                    sr = res.get("metrics", {}).get("stop_reason", "unknown")
                    stop_reasons[sr] = stop_reasons.get(sr, 0) + 1
                else:
                    print(">>> WARNING: result file not found after successful run")
                completed += 1
                print(f">>> OK in {trial_elapsed:.0f}s\n")

        except subprocess.TimeoutExpired:
            failures.append({
                "task": task, "map": map_type, "rep": rep,
                "reason": "timeout (600s)",
            })
            print(">>> FAILED (timeout)\n")
        except Exception as exc:
            failures.append({
                "task": task, "map": map_type, "rep": rep,
                "reason": str(exc),
            })
            print(f">>> FAILED ({exc})\n")

        if i < total - 1:
            time.sleep(args.delay)

    total_elapsed  = time.time() - batch_start
    avg_per_trial  = total_elapsed / total if total else 0

    print()
    print("=" * 65)
    print("BATCH COMPLETE")
    print(f"  Trials    {completed}/{total} succeeded  ({len(failures)} failed)")
    print(f"  Cost      ${total_cost:.4f}")
    print(f"  Time      {fmt_time(total_elapsed)}  (avg {avg_per_trial:.0f}s/trial)")
    print()
    print("  Stop reasons:")
    for sr, count in sorted(stop_reasons.items(), key=lambda x: -x[1]):
        pct = 100 * count / completed if completed else 0
        print(f"    {sr:<15s} {count:4d}  ({pct:.0f}%)")
    if failures:
        print()
        print("  Failures:")
        for fail in failures:
            print(f"    task={fail['task']} map={fail['map']} rep={fail['rep']}: {fail['reason']}")
    print("=" * 65)


if __name__ == "__main__":
    main()
