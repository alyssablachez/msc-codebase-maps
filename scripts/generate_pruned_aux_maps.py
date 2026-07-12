"""
Generate size-capped versions of the frequency map and co-change map for
every selected issue, using the same least-frequently-edited-first pruning
rule as scripts/generate_pruned_maps.py (which handles the compact map).

Each map type is pruned independently against its own token budget: a file
kept in the pruned compact map is not necessarily kept in the pruned freq or
cochange map, since their per-file token cost differs.

Freq map: already sorted descending by edit count, so pruning is just
taking the longest prefix of lines that fits under budget.

Co-change map: source file is alphabetical, not frequency-ordered. Files are
re-ranked by edit frequency (from the issue's own freq_map.txt) and the
largest frequency-ordered prefix that fits under budget is kept, then
re-rendered alphabetically (matching the original format). Co-change
partners are reported as-is even if the partner file itself was pruned from
the map — a listed partner is a historical fact about the kept file, not a
promise that the partner's own block is present.

Writes repo_maps/pruned_aux_maps_stats[_{N}k].csv.

Usage:
    python3 scripts/generate_pruned_aux_maps.py
    python3 scripts/generate_pruned_aux_maps.py --token-budget 55000
    python3 scripts/generate_pruned_aux_maps.py --dry-run
"""
import argparse
import csv
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEL_CSV = os.path.join(_ROOT, "data", "issue_selection_final.csv")

DEFAULT_BUDGET = 30_000

OUT_COLS = [
    "repo", "tier", "issue_idx", "role",
    "freq_n_total", "freq_n_kept", "freq_n_pruned",
    "freq_tokens_before", "freq_tokens_after",
    "freq_pruned_files",
    "cochange_n_total", "cochange_n_kept", "cochange_n_pruned",
    "cochange_tokens_before", "cochange_tokens_after",
    "cochange_pruned_files",
]


def output_names(budget):
    if budget == DEFAULT_BUDGET:
        suffix = ""
        stats_csv = os.path.join(_ROOT, "repo_maps", "pruned_aux_maps_stats.csv")
    else:
        suffix = f"_{budget // 1000}k"
        stats_csv = os.path.join(_ROOT, "repo_maps", f"pruned_aux_maps_stats{suffix}.csv")
    freq_name     = f"freq_map_pruned{suffix}.txt"
    cochange_name = f"cochange_map_pruned{suffix}.txt"
    return freq_name, cochange_name, stats_csv


def parse_freq_map(path):
    """Return ordered list of (filepath, raw_line) as they appear (already
    sorted descending by edit count in the original file)."""
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            filepath = line.split("  [", 1)[0]
            entries.append((filepath, line))
    return entries


def prune_freq(entries, budget):
    """Greedily keep entries (already desc-frequency ordered) while under
    budget. Always keeps at least the first entry."""
    kept = []
    for i, (fp, line) in enumerate(entries):
        tentative = kept + [line]
        tentative_tokens = (sum(len(l) for l in tentative) + len(tentative)) // 4
        if tentative_tokens <= budget or i == 0:
            kept = tentative
        else:
            break
    kept_files = {fp for fp, line in entries[:len(kept)]}
    all_files = {fp for fp, _ in entries}
    pruned_files = sorted(all_files - kept_files)
    content = "\n".join(kept) + "\n"
    return content, kept_files, pruned_files


def parse_cochange_map(path):
    """Return dict {filepath: [block_lines]} preserving original blocks."""
    blocks = {}
    current_file = None
    current_lines = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("→ "):  # "→ partner (Nx)"
                current_lines.append(line)
            else:
                if current_file is not None:
                    blocks[current_file] = current_lines
                current_file = line
                current_lines = []
        if current_file is not None:
            blocks[current_file] = current_lines
    return blocks


def prune_cochange(blocks, freq_rank, budget):
    """Rank blocks by edit frequency (freq_rank: filepath -> rank, lower is
    more frequent), keep the largest frequency-ordered prefix under budget,
    render remaining blocks alphabetically."""
    present_ordered = sorted(blocks, key=lambda fp: freq_rank.get(fp, len(freq_rank)))

    kept_files = []
    running_lines = []
    for i, fp in enumerate(present_ordered):
        block_lines = [fp] + blocks[fp]
        tentative = running_lines + block_lines
        tentative_tokens = (sum(len(l) for l in tentative) + len(tentative)) // 4
        if tentative_tokens <= budget or i == 0:
            running_lines = tentative
            kept_files.append(fp)
        else:
            break

    kept_set = set(kept_files)
    pruned_files = sorted(set(blocks) - kept_set)

    out_lines = []
    for fp in sorted(kept_set):
        out_lines.append(fp)
        out_lines.extend(blocks[fp])
    content = "\n".join(out_lines) + "\n" if out_lines else ""
    return content, kept_set, pruned_files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--token-budget", type=int, default=DEFAULT_BUDGET)
    args = ap.parse_args()

    issues = pd.read_csv(SEL_CSV)
    total = len(issues)
    budget = args.token_budget
    freq_name, cochange_name, OUT_CSV = output_names(budget)

    print(f"Generating pruned (<{budget:,} tok) freq/cochange maps for {total} issues")
    if args.dry_run:
        print()

    rows = []
    for enum_i, (_, row) in enumerate(issues.iterrows()):
        repo, tier, issue_idx, role = row["repo"], row["tier"], int(row["issue_idx"]), row["role"]

        issue_dir    = os.path.join(_ROOT, "repo_maps", repo, str(issue_idx))
        freq_in      = os.path.join(issue_dir, "freq_map.txt")
        cochange_in  = os.path.join(issue_dir, "cochange_map.txt")
        freq_out     = os.path.join(issue_dir, freq_name)
        cochange_out = os.path.join(issue_dir, cochange_name)

        if args.dry_run:
            print(f"  {repo:<28} issue={issue_idx:>3}  -> {freq_out}, {cochange_out}")
            continue

        # ── Freq map ──────────────────────────────────────────────────────
        freq_entries = parse_freq_map(freq_in)
        freq_tokens_before = (sum(len(l) for _, l in freq_entries) + len(freq_entries)) // 4
        freq_content, freq_kept, freq_pruned = prune_freq(freq_entries, budget)
        with open(freq_out, "w", encoding="utf-8") as f:
            f.write(freq_content)
        freq_tokens_after = len(freq_content) // 4

        # ── Co-change map ────────────────────────────────────────────────
        freq_rank = {fp: i for i, (fp, _) in enumerate(freq_entries)}
        cochange_blocks = parse_cochange_map(cochange_in)
        cochange_tokens_before = os.path.getsize(cochange_in) // 4
        cochange_content, cochange_kept, cochange_pruned = prune_cochange(
            cochange_blocks, freq_rank, budget)
        with open(cochange_out, "w", encoding="utf-8") as f:
            f.write(cochange_content)
        cochange_tokens_after = len(cochange_content) // 4

        rows.append({
            "repo": repo, "tier": tier, "issue_idx": issue_idx, "role": role,
            "freq_n_total": len(freq_entries), "freq_n_kept": len(freq_kept),
            "freq_n_pruned": len(freq_pruned),
            "freq_tokens_before": freq_tokens_before, "freq_tokens_after": freq_tokens_after,
            "freq_pruned_files": ";".join(freq_pruned),
            "cochange_n_total": len(cochange_blocks), "cochange_n_kept": len(cochange_kept),
            "cochange_n_pruned": len(cochange_pruned),
            "cochange_tokens_before": cochange_tokens_before,
            "cochange_tokens_after": cochange_tokens_after,
            "cochange_pruned_files": ";".join(cochange_pruned),
        })

        print(f"[{enum_i+1:>2}/{total}] {repo} issue={issue_idx} ({role}) — "
              f"freq {freq_tokens_before:>6}->{freq_tokens_after:>6} tok "
              f"({len(freq_kept)}/{len(freq_entries)} files), "
              f"cochange {cochange_tokens_before:>6}->{cochange_tokens_after:>6} tok "
              f"({len(cochange_kept)}/{len(cochange_blocks)} files)")

    if args.dry_run:
        return

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_COLS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nStats saved -> {OUT_CSV}")


if __name__ == "__main__":
    main()
