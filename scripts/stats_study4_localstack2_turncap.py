"""
Study 4 -- supplementary test specific to localstack/2's documented
pattern (DEVLOG 2026-08-08): DeepSeek's weak score breaks down by
DELIVERY MECHANISM specifically (context injection vs. voluntary tool
vs. required tool), not cleanly by individual map condition -- tool_free
(voluntary) hits max_turns 100% of the time, context delivery is
DeepSeek's best mechanism. This tests that mechanism-level pattern
directly, using every rep (n=15/condition, all 12 conditions) now
available for this issue, DeepSeek only.

Fisher-Freeman-Halton generalization of Fisher's exact isn't available
in this project's scipy version for r x c tables, so this uses a
chi-square test of independence (delivery_mechanism x hit_turn_cap) --
justified here since cell counts are much larger pooling across all
conditions within a mechanism (n=45/mechanism) than in the per-condition
success tests, clearing chi-square's expected-count-5 rule of thumb.

Usage:
    python3 scripts/stats_study4_localstack2_turncap.py
"""
import os

import pandas as pd
from scipy.stats import chi2_contingency, fisher_exact
from statsmodels.stats.multitest import multipletests

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PKL = os.path.join(_ROOT, "data", "compiled_results_combined.pkl")
OUT_DIR = os.path.join(_ROOT, "data", "stats_study4")
OUT_CSV_OMNIBUS = os.path.join(OUT_DIR, "study4_localstack2_turncap_omnibus.csv")
OUT_CSV_PAIRWISE = os.path.join(OUT_DIR, "study4_localstack2_turncap_pairwise.csv")

MECHANISM_ORDER = ["injection", "on_demand_voluntary", "on_demand_required"]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    df = pd.read_pickle(DATA_PKL)
    sub = df[(df["repo"] == "localstack") & (df["issue_idx"] == 2) &
            (df["model"] == "deepseek/deepseek-v4-flash")].copy()

    sub["mechanism"] = sub.apply(
        lambda r: "injection" if r["delivery_mechanism"] == "injection"
        else ("on_demand_required" if r["submission_mode"] == "required" else "on_demand_voluntary"),
        axis=1,
    )

    table = pd.crosstab(sub["mechanism"], sub["hit_turn_cap"]).reindex(MECHANISM_ORDER)
    print("Contingency table (mechanism x hit_turn_cap):")
    print(table)
    chi2, p, dof, expected = chi2_contingency(table)
    print(f"\nChi-square: stat={chi2:.4f}, dof={dof}, p={p:.4e}")
    print("Expected counts:\n", pd.DataFrame(expected, index=table.index, columns=table.columns))

    omnibus = pd.DataFrame([{
        "test": "chi2_independence_mechanism_x_turncap", "n": len(sub),
        "chi2_stat": round(chi2, 4), "dof": dof, "p_value": p,
    }])
    omnibus.to_csv(OUT_CSV_OMNIBUS, index=False)
    print(f"\nSaved: {OUT_CSV_OMNIBUS}")

    # Pairwise mechanism comparisons, Fisher's exact (2x2), Holm-corrected
    rows = []
    pairs = [("on_demand_voluntary", "injection"), ("on_demand_required", "injection"),
            ("on_demand_required", "on_demand_voluntary")]
    for cond, ref in pairs:
        a = sub[sub["mechanism"] == cond]["hit_turn_cap"]
        b = sub[sub["mechanism"] == ref]["hit_turn_cap"]
        tbl = [[int((a == True).sum()), int((a == False).sum())],
              [int((b == True).sum()), int((b == False).sum())]]
        odds_ratio, p_raw = fisher_exact(tbl)
        rows.append({
            "comparison": f"{cond}_vs_{ref}", "n_cond": len(a), "n_ref": len(b),
            "cond_hit_rate": round(a.mean(), 3), "ref_hit_rate": round(b.mean(), 3),
            "odds_ratio": round(odds_ratio, 4) if odds_ratio != float("inf") else odds_ratio,
            "p_raw": p_raw,
        })
    pairwise = pd.DataFrame(rows)
    pairwise["p_holm"] = multipletests(pairwise["p_raw"], method="holm")[1]
    print("\nPairwise mechanism comparisons (Fisher's exact, Holm-corrected):")
    print(pairwise.to_string(index=False))
    pairwise.to_csv(OUT_CSV_PAIRWISE, index=False)
    print(f"\nSaved: {OUT_CSV_PAIRWISE}")


if __name__ == "__main__":
    main()
