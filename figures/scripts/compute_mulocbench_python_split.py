"""
Per-repo Python vs. non-Python LoC (raw, not %), bucketed into
small/medium/large by total LoC (MULocBench's own bucket(total) thresholds:
<10k small, <100k medium, else large -- same as compute_mulocbench_language_loc.py).

Reads figures/data/mulocbench_language_loc.csv (compute_mulocbench_language_loc.py).
Writes figures/data/mulocbench_python_split.csv.

Usage:
    python3 figures/scripts/compute_mulocbench_python_split.py
"""
import os

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IN_CSV = os.path.join(_ROOT, "figures", "data", "mulocbench_language_loc.csv")
OUT_CSV = os.path.join(_ROOT, "figures", "data", "mulocbench_python_split.csv")


def main():
    long = pd.read_csv(IN_CSV)
    total = long.groupby("repo")["loc"].sum().rename("total_loc")
    python_loc = (
        long[long["language"] == ".py"].groupby("repo")["loc"].sum().rename("python_loc")
    )
    size = long.drop_duplicates("repo").set_index("repo")["size"]

    out = pd.concat([total, python_loc], axis=1).fillna(0)
    out["python_loc"] = out["python_loc"].astype(int)
    out["other_loc"] = (out["total_loc"] - out["python_loc"]).astype(int)
    out["size"] = size
    out = out.reset_index().rename(columns={"index": "repo"})

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    print(f"Saved: {OUT_CSV}  ({len(out)} repos)")
    print(out["size"].value_counts())


if __name__ == "__main__":
    main()
