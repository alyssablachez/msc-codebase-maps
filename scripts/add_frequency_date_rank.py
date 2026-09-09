"""
Adds a date-based rank to data/map_position_metrics.csv for frequency-map
rows only: where does the ground-truth file sit if the SAME set of files
actually injected (repo_maps/<repo>/<issue_idx>/freq_map_pruned_55k.txt,
matching harness/run_trial.py's MAP_FILES["freq"]) is re-sorted by most-
recent-edit date instead of by edit count? The map itself is always
shown to the model sorted by count -- this checks whether recency alone
would have put the ground-truth file somewhere different, i.e. whether
count and recency agree or diverge as signals for this file.

Only frequency carries per-file dates at all: structural (compact_map_
pruned_55k.txt) lists symbols/line numbers, and co-change (cochange_map_
pruned_55k.txt) lists partner files with co-change counts -- neither has
a last-edited date in the injected text. So structural/cochange rows in
the output get blank date columns, same convention this CSV already uses
for status="pruned_out"/"never_included" rows (blank position, map-level
totals still populated).

Purely additive: reads the existing CSV, adds "date_rank",
"total_files_with_dates", "pct_through_dates" columns, leaves every
existing column and value untouched. No generator script exists for the
base CSV (see DEVLOG 2026-08-xx) -- this only touches the new columns.

Usage:
    python3 scripts/add_frequency_date_rank.py
"""
import os
import re

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN_CSV = os.path.join(_ROOT, "data", "map_position_metrics.csv")
OUT_CSV = IN_CSV  # in place -- purely additive, existing columns untouched

LINE_RE = re.compile(r"^(.+?)\s+\[(\d+) edits?, last: (\d{4}-\d{2}-\d{2})\]\s*$")


def parse_freq_map(repo, issue_idx):
    """Returns list of (path, edit_count, last_edit_date) in the file's
    own on-disk order (i.e. already sorted by edit count descending,
    since that's how generate_pruned_maps.py writes it)."""
    path = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx), "freq_map_pruned_55k.txt")
    if not os.path.isfile(path):
        return None
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            m = LINE_RE.match(line)
            if not m:
                continue
            entries.append((m.group(1), int(m.group(2)), m.group(3)))
    return entries


def date_rank_for(entries, gt_file):
    """Rank (1-indexed) of gt_file when entries are re-sorted by date
    descending (most recent first), ties broken by the original edit-
    count-descending order (stable sort preserves that automatically
    since entries already arrive in that order). None if gt_file isn't
    in the list at all."""
    by_date = sorted(entries, key=lambda e: e[2], reverse=True)
    for i, (path, _, _) in enumerate(by_date, start=1):
        if path == gt_file:
            return i, len(by_date)
    return None, len(by_date)


def main():
    df = pd.read_csv(IN_CSV)
    date_rank_col = []
    total_dated_col = []
    pct_col = []

    cache = {}
    for _, row in df.iterrows():
        if row["map_type"] != "frequency":
            date_rank_col.append(pd.NA)
            total_dated_col.append(pd.NA)
            pct_col.append(pd.NA)
            continue

        key = (row["repo"], row["issue_idx"])
        if key not in cache:
            cache[key] = parse_freq_map(row["repo"], row["issue_idx"])
        entries = cache[key]

        if entries is None:
            date_rank_col.append(pd.NA)
            total_dated_col.append(pd.NA)
            pct_col.append(pd.NA)
            continue

        rank, total = date_rank_for(entries, row["gt_file"])
        date_rank_col.append(rank if rank is not None else pd.NA)
        total_dated_col.append(total)
        pct_col.append(round(100 * rank / total, 1) if rank is not None else pd.NA)

    df["date_rank"] = pd.array(date_rank_col, dtype="Int64")
    df["total_files_with_dates"] = pd.array(total_dated_col, dtype="Int64")
    df["pct_through_dates"] = pct_col

    n_freq = (df["map_type"] == "frequency").sum()
    n_matched = df["date_rank"].notna().sum()
    print(f"{n_freq} frequency rows, {n_matched} got a date_rank "
         f"({n_freq - n_matched} missing -- map file not found or gt_file not listed)")

    df.to_csv(OUT_CSV, index=False)
    print(f"Saved -> {OUT_CSV}")

    freq = df[df["map_type"] == "frequency"].dropna(subset=["date_rank"])
    print("\nSummary, frequency rows with a match:")
    print(freq[["pct_through_files", "pct_through_dates"]].describe())
    # how often does date rank agree/disagree in direction with count rank
    freq = freq.copy()
    freq["rank_diff"] = freq["date_rank"] - freq["file_rank"]
    print(f"\nGT file ranked BETTER (earlier) by date than by count: "
         f"{(freq['rank_diff'] < 0).sum()}/{len(freq)}")
    print(f"GT file ranked WORSE (later) by date than by count: "
         f"{(freq['rank_diff'] > 0).sum()}/{len(freq)}")
    print(f"Same rank by both: {(freq['rank_diff'] == 0).sum()}/{len(freq)}")


if __name__ == "__main__":
    main()
