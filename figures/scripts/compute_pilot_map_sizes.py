"""
Compute estimated token counts (chars // 4) for the Study 0 pilot's three
map types -- ast, ctags, ast_compact -- across the five requests/ tasks,
paired with each task's base_commit date.

Reads the archived map files directly (study_0/repo_maps/requests/task_N/).
Uses chars // 4 rather than an exact tiktoken encode -- the same estimation
convention used everywhere else in the pipeline's token-count columns
(generate_pruned_maps.py, generate_pruned_aux_maps.py, generate_all_maps.py,
index_size_stats.py), so this figure is comparable to those, not to
scripts/estimate_tokens.py's exact-tiktoken numbers.

Usage:
    python3 figures/scripts/compute_pilot_map_sizes.py
"""
import csv
import os
import subprocess

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPO_DIR = os.path.join(_ROOT, "repos", "requests_full")
TASKS_DIR = os.path.join(_ROOT, "study_0", "repo_maps", "requests")
OUT_CSV = os.path.join(_ROOT, "figures", "data", "pilot_study_map_sizes.csv")

# task_idx -> (base_commit, map filename per type)
TASKS = {
    0:  "ccabcf1fca906bfa6b65a3189c1c41061e6c1042",
    4:  "9968a10fcfad7268b552808c4f8946eecafc956a",
    12: "be62645dd56580dd7576032b348cf79d880851d8",
    14: "4683f169909857d663275346655975af7190fd62",
    15: "1c2022cf868cb503815f34901ad8e85cf524d01a",
}

MAP_FILES = {
    "ast":         "ast_map.json",
    "ctags":       "ctags_map.json",
    "ast_compact": "compact_map.txt",
}

def commit_date(sha):
    result = subprocess.run(
        ["git", "-C", REPO_DIR, "log", "-1", "--format=%ci", sha],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip().split()[0]  # YYYY-MM-DD


def token_count(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return len(content) // 4


def main():
    rows = []
    for task_idx, base_commit in TASKS.items():
        date = commit_date(base_commit)
        for map_type, fname in MAP_FILES.items():
            path = os.path.join(TASKS_DIR, f"task_{task_idx}", fname)
            tokens = token_count(path)
            rows.append({
                "task": task_idx,
                "base_commit": base_commit[:8],
                "commit_date": date,
                "map_type": map_type,
                "tokens": tokens,
            })
            print(f"task_{task_idx}  {date}  {map_type:<12} {tokens:>8,} tokens")

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["task", "base_commit", "commit_date", "map_type", "tokens"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nSaved: {OUT_CSV}")


if __name__ == "__main__":
    main()
