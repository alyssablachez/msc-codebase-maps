"""
Statistical comparison of ast vs ast_compact map conditions.

Usage:
    python3 scripts/ast_vs_compact_analysis.py
"""
import io
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

_ROOT   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_TXT = os.path.join(_ROOT, "logs", "ast_vs_compact_analysis.txt")

SHORT = {
    'deepinfra_Qwen_Qwen3-VL-30B-A3B-Instruct':          'Qwen3-VL-30B',
    'deepinfra_Qwen_Qwen3-VL-235B-A22B-Instruct':         'Qwen3-VL-235B',
    'fireworks_ai_accounts_fireworks_models_gpt-oss-20b':  'gpt-oss-20b',
    'fireworks_ai_accounts_fireworks_models_gpt-oss-120b': 'gpt-oss-120b',
    'mistral_ministral-3b-latest':                         'ministral-3b',
    'mistral_ministral-14b-latest':                        'ministral-14b',
    'deepseek_deepseek-v4-flash':                          'deepseek-flash',
    'deepseek_deepseek-v4-pro':                            'deepseek-pro',
    'deepinfra_nvidia_Nemotron-3-Nano-30B-A3B':           'Nemotron-Nano-30B',
    'deepinfra_nvidia_NVIDIA-Nemotron-3-Super-120B-A12B': 'Nemotron-Super-120B',
    'deepinfra_zai-org_GLM-4.7-Flash':                    'GLM-4.7-Flash',
    'deepinfra_zai-org_GLM-4.7':                          'GLM-4.7',
}
MODEL_ORDER = list(SHORT.values())


# ── helpers ───────────────────────────────────────────────────────────────────

def section(title):
    return f"\n{'='*70}\n{title}\n{'='*70}\n"


def wilcoxon_paired(a, b, label=""):
    """Run Wilcoxon signed-rank test on paired arrays a and b.
    Returns dict of stats. Skips zero-difference pairs per default scipy behaviour.
    """
    diffs = np.array(a) - np.array(b)
    n = len(diffs)
    nonzero = np.sum(diffs != 0)
    if nonzero < 10:
        return {"n": n, "nonzero": nonzero, "mean_diff": np.mean(diffs),
                "median_diff": np.median(diffs), "W": np.nan,
                "p": np.nan, "z": np.nan, "r": np.nan,
                "note": "too few non-zero differences"}
    result = stats.wilcoxon(diffs, alternative='two-sided', method='approx')
    W = result.statistic
    p = result.pvalue
    # Z from normal approximation
    z = result.zstatistic if hasattr(result, 'zstatistic') else np.nan
    # Fallback: derive z from p if not available
    if np.isnan(z) and not np.isnan(p):
        z = stats.norm.isf(p / 2) * np.sign(np.mean(diffs))
    r = z / np.sqrt(n) if not np.isnan(z) else np.nan
    return {"n": n, "nonzero": nonzero, "mean_diff": np.mean(diffs),
            "median_diff": np.median(diffs), "W": W, "p": p, "z": z, "r": r,
            "note": ""}


def holm_bonferroni(p_values):
    """Return Holm-Bonferroni corrected p-values for a list of p-values."""
    k = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    corrected = [None] * k
    prev = 0.0
    for rank, (orig_i, p) in enumerate(indexed):
        adj = min(1.0, max(prev, p * (k - rank)))
        corrected[orig_i] = adj
        prev = adj
    return corrected


def sig_star(p):
    if np.isnan(p): return "n/a"
    if p < 0.001:   return "***"
    if p < 0.01:    return "**"
    if p < 0.05:    return "*"
    return "ns"


# ── load and pair data ────────────────────────────────────────────────────────

def load_pairs(df):
    ast = df[df['map_type'] == 'ast'].copy()
    cmp = df[df['map_type'] == 'ast_compact'].copy()
    pairs = ast.merge(cmp, on=['model_dir', 'task_idx', 'rep'],
                      suffixes=('_ast', '_cmp'))
    pairs['model_short'] = pairs['model_dir'].map(SHORT)
    return pairs


# ── analyses ──────────────────────────────────────────────────────────────────

def analysis1_overall(pairs, out):
    out.write(section("ANALYSIS 1: Overall ast vs ast_compact (all models combined)"))

    outcomes = {
        'f1':           {'label': 'F1',           'excl_empty': True},
        'turns':        {'label': 'Turns',         'excl_empty': False},
        'input_tokens': {'label': 'Input tokens',  'excl_empty': False},
    }

    results = {}
    for col, meta in outcomes.items():
        if meta['excl_empty']:
            sub = pairs[(~pairs['empty_prediction_ast']) & (~pairs['empty_prediction_cmp'])]
            note = f"(empty pairs excluded: {len(pairs)-len(sub)} dropped)"
        else:
            sub = pairs
            note = "(all pairs included)"

        r = wilcoxon_paired(sub[f'{col}_ast'], sub[f'{col}_cmp'], col)
        r['label'] = meta['label']
        r['excl_note'] = note
        results[col] = r

    # Holm-Bonferroni correction
    p_vals = [results[c]['p'] for c in outcomes]
    p_corr = holm_bonferroni(p_vals)
    for (col, _), p_adj in zip(outcomes.items(), p_corr):
        results[col]['p_adj'] = p_adj

    # Print table
    out.write(f"{'Outcome':<14} {'N':>5} {'Mean Δ':>10} {'Median Δ':>10} "
              f"{'W':>10} {'p':>10} {'p_adj':>10} {'r':>7} {'sig':>4}\n")
    out.write("-" * 80 + "\n")
    for col, r in results.items():
        out.write(f"{r['label']:<14} {r['n']:>5} {r['mean_diff']:>10.4f} "
                  f"{r['median_diff']:>10.4f} {r['W']:>10.1f} "
                  f"{r['p']:>10.4f} {r['p_adj']:>10.4f} "
                  f"{r['r']:>7.3f} {sig_star(r['p_adj']):>4}\n")
        out.write(f"               {r['excl_note']}\n")

    out.write("\nSign convention: Δ = ast − ast_compact  "
              "(positive = ast higher, negative = ast_compact higher)\n")
    out.write("Holm-Bonferroni correction applied across 3 tests.\n")
    out.write("Effect size r: 0.1=small, 0.3=medium, 0.5=large\n")
    return results


def analysis2_per_model(pairs, out):
    out.write(section("ANALYSIS 2: Per-model ast vs ast_compact (F1 only)"))

    rows = []
    for model in MODEL_ORDER:
        sub = pairs[(pairs['model_short'] == model) &
                    (~pairs['empty_prediction_ast']) &
                    (~pairs['empty_prediction_cmp'])]
        n_pairs = len(sub)
        mean_ast = sub['f1_ast'].mean()
        mean_cmp = sub['f1_cmp'].mean()
        diff = mean_ast - mean_cmp
        if n_pairs >= 10:
            r = wilcoxon_paired(sub['f1_ast'], sub['f1_cmp'])
            p, W = r['p'], r['W']
        else:
            p, W = np.nan, np.nan
        rows.append({'model': model, 'n_pairs': n_pairs,
                     'mean_f1_ast': mean_ast, 'mean_f1_compact': mean_cmp,
                     'diff': diff, 'W': W, 'p_raw': p})

    # Holm-Bonferroni across models
    valid_p = [(i, r['p_raw']) for i, r in enumerate(rows) if not np.isnan(r['p_raw'])]
    if valid_p:
        idxs, pvals = zip(*valid_p)
        padj = holm_bonferroni(list(pvals))
        p_adj_map = dict(zip(idxs, padj))
    else:
        p_adj_map = {}

    out.write(f"{'Model':<22} {'N':>5} {'mean_ast':>9} {'mean_cmp':>9} "
              f"{'diff':>8} {'W':>8} {'p':>8} {'p_adj':>8} {'sig':>4}\n")
    out.write("-" * 85 + "\n")
    for i, r in enumerate(rows):
        p_adj = p_adj_map.get(i, np.nan)
        out.write(f"{r['model']:<22} {r['n_pairs']:>5} "
                  f"{r['mean_f1_ast']:>9.4f} {r['mean_f1_compact']:>9.4f} "
                  f"{r['diff']:>8.4f} {r['W']:>8.1f} "
                  f"{r['p_raw']:>8.4f} {p_adj:>8.4f} {sig_star(p_adj):>4}\n")

    out.write("\nHolm-Bonferroni correction applied across models.\n")
    return rows


def analysis3_per_task(pairs, out):
    out.write(section("ANALYSIS 3: Per-task ast vs ast_compact (F1 only)"))

    rows = []
    for task in sorted(pairs['task_idx'].unique()):
        sub = pairs[(pairs['task_idx'] == task) &
                    (~pairs['empty_prediction_ast']) &
                    (~pairs['empty_prediction_cmp'])]
        n_pairs = len(sub)
        mean_ast = sub['f1_ast'].mean()
        mean_cmp = sub['f1_cmp'].mean()
        diff = mean_ast - mean_cmp
        if n_pairs >= 10:
            r = wilcoxon_paired(sub['f1_ast'], sub['f1_cmp'])
            p, W = r['p'], r['W']
        else:
            p, W = np.nan, np.nan
        rows.append({'task': task, 'n_pairs': n_pairs,
                     'mean_f1_ast': mean_ast, 'mean_f1_compact': mean_cmp,
                     'diff': diff, 'W': W, 'p_raw': p})

    valid_p = [(i, r['p_raw']) for i, r in enumerate(rows) if not np.isnan(r['p_raw'])]
    if valid_p:
        idxs, pvals = zip(*valid_p)
        padj = holm_bonferroni(list(pvals))
        p_adj_map = dict(zip(idxs, padj))
    else:
        p_adj_map = {}

    out.write(f"{'Task':>6} {'N':>5} {'mean_ast':>9} {'mean_cmp':>9} "
              f"{'diff':>8} {'W':>8} {'p':>8} {'p_adj':>8} {'sig':>4}\n")
    out.write("-" * 70 + "\n")
    for i, r in enumerate(rows):
        p_adj = p_adj_map.get(i, np.nan)
        out.write(f"{r['task']:>6} {r['n_pairs']:>5} "
                  f"{r['mean_f1_ast']:>9.4f} {r['mean_f1_compact']:>9.4f} "
                  f"{r['diff']:>8.4f} {r['W']:>8.1f} "
                  f"{r['p_raw']:>8.4f} {p_adj:>8.4f} {sig_star(p_adj):>4}\n")

    out.write("\nHolm-Bonferroni correction applied across tasks.\n")
    return rows


def analysis4_tokens(pairs, out):
    out.write(section("ANALYSIS 4: Token cost — ast vs ast_compact"))

    mean_ast = pairs['input_tokens_ast'].mean()
    mean_cmp = pairs['input_tokens_cmp'].mean()
    diff     = mean_ast - mean_cmp
    pct_save = diff / mean_ast * 100

    out.write(f"Overall mean input tokens:\n")
    out.write(f"  ast:         {mean_ast:>12,.0f}\n")
    out.write(f"  ast_compact: {mean_cmp:>12,.0f}\n")
    out.write(f"  difference:  {diff:>12,.0f}  ({pct_save:.1f}% fewer with compact)\n\n")

    out.write(f"{'Model':<22} {'ast_tokens':>12} {'compact_tokens':>15} "
              f"{'diff':>10} {'saving_%':>10}\n")
    out.write("-" * 72 + "\n")
    for model in MODEL_ORDER:
        sub = pairs[pairs['model_short'] == model]
        ma  = sub['input_tokens_ast'].mean()
        mc  = sub['input_tokens_cmp'].mean()
        d   = ma - mc
        pct = d / ma * 100 if ma > 0 else 0
        out.write(f"{model:<22} {ma:>12,.0f} {mc:>15,.0f} {d:>10,.0f} {pct:>9.1f}%\n")

    return mean_ast, mean_cmp, diff, pct_save


def recommendation(overall_results, model_rows, token_diff_pct, out):
    out.write(section("DECISION FRAMEWORK & RECOMMENDATION"))

    f1_res  = overall_results['f1']
    f1_sig  = not np.isnan(f1_res['p_adj']) and f1_res['p_adj'] < 0.05
    ast_better     = f1_res['mean_diff'] > 0   # ast − compact > 0
    compact_better = f1_res['mean_diff'] < 0
    compact_saves  = token_diff_pct > 0

    n_models_ast_sig    = sum(1 for r in model_rows
                              if not np.isnan(r['p_raw']) and r['p_raw'] < 0.05 and r['diff'] > 0)
    n_models_compact_sig = sum(1 for r in model_rows
                               if not np.isnan(r['p_raw']) and r['p_raw'] < 0.05 and r['diff'] < 0)

    out.write(f"Overall F1 test (Holm-corrected): p = {f1_res['p_adj']:.4f}  "
              f"({'significant' if f1_sig else 'not significant'})\n")
    out.write(f"Mean Δ (ast − compact): {f1_res['mean_diff']:+.4f}  "
              f"({'ast higher' if ast_better else 'compact higher' if compact_better else 'equal'})\n")
    out.write(f"Token saving with compact: {token_diff_pct:.1f}%\n")
    out.write(f"Models where ast sig. better: {n_models_ast_sig}\n")
    out.write(f"Models where compact sig. better: {n_models_compact_sig}\n\n")

    if not f1_sig and compact_saves:
        rec = ("RECOMMENDATION: Drop ast (verbose), keep ast_compact.\n"
               "Rationale: No statistically significant F1 difference between conditions "
               f"(p={f1_res['p_adj']:.3f}), and ast_compact uses {token_diff_pct:.1f}% "
               "fewer input tokens. The compact format delivers equivalent accuracy at "
               "lower context cost.")
    elif f1_sig and ast_better:
        rec = ("RECOMMENDATION: Drop ast_compact, keep ast.\n"
               f"Rationale: ast significantly outperforms ast_compact (p={f1_res['p_adj']:.3f}, "
               f"Δ={f1_res['mean_diff']:+.4f}). The accuracy gain outweighs the token saving.")
    elif f1_sig and compact_better:
        rec = ("RECOMMENDATION: Drop ast (verbose), keep ast_compact.\n"
               f"Rationale: ast_compact significantly outperforms ast (p={f1_res['p_adj']:.3f}, "
               f"Δ={f1_res['mean_diff']:+.4f}), and also uses fewer tokens. Clear winner.")
    else:
        rec = ("RECOMMENDATION: Mixed results — flag for manual review.\n"
               f"Rationale: Overall p={f1_res['p_adj']:.3f} but per-model results are "
               f"inconsistent ({n_models_ast_sig} models favour ast, "
               f"{n_models_compact_sig} favour compact). "
               "Consider keeping both conditions or choosing based on the target model.")

    out.write(rec + "\n")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    df = pd.read_csv(os.path.join(_ROOT, "results_all.csv"))

    # Flag completeness
    for m in df['model_short'].unique():
        n = len(df[df['model_short'] == m])
        if n < 75:
            print(f"WARNING: {m} has only {n} trials (expected 75)")

    pairs = load_pairs(df)

    buf = io.StringIO()
    buf.write("AST vs AST_COMPACT MAP CONDITION ANALYSIS\n")
    buf.write(f"Total matched pairs: {len(pairs)}  "
              f"(N=25 per model × 12 models)\n")

    overall = analysis1_overall(pairs, buf)
    model_rows = analysis2_per_model(pairs, buf)
    analysis3_per_task(pairs, buf)
    _, _, _, token_pct = analysis4_tokens(pairs, buf)
    recommendation(overall, model_rows, token_pct, buf)

    output = buf.getvalue()
    print(output)

    with open(OUT_TXT, "w") as f:
        f.write(output)
    print(f"Saved → {OUT_TXT}")


if __name__ == "__main__":
    main()
