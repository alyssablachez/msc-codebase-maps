"""
Per-repo, per-language LoC across the MULocBench benchmark, bucketed into
small/medium/large by total LoC: small < 15k, medium 15k-150k, large >= 150k
-- an even three-way split of the 46-repo pool (15/16/15).

Reads study_0/results/loc_by_language.json.
Writes figures/data/mulocbench_language_loc.csv (long format: repo, size,
language, loc).

Usage:
    python3 figures/scripts/compute_mulocbench_language_loc.py
"""
import json
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_CSV = os.path.join(_ROOT, "figures", "data", "mulocbench_language_loc.csv")


def bucket(total):
    if total < 15_000:
        return "small"
    elif total < 150_000:
        return "medium"
    return "large"


def main():
    with open(os.path.join(_ROOT, "study_0", "results", "loc_by_language.json")) as f:
        loc_by_language = json.load(f)

    df = pd.DataFrame(loc_by_language).T.fillna(0)
    total = df.sum(axis=1)
    size = total.apply(bucket)

    long = df.reset_index().melt(id_vars="index", var_name="language", value_name="loc")
    long = long.rename(columns={"index": "repo"})
    long["size"] = long["repo"].map(size)
    long = long[long["loc"] > 0]

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    long.to_csv(OUT_CSV, index=False)
    print(f"Saved: {OUT_CSV}  ({long['repo'].nunique()} repos, {long['language'].nunique()} languages)")
    print(size.value_counts())


if __name__ == "__main__":
    main()
