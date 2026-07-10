"""Run once after closing map_generation_stats.csv and issue_selection_random.csv."""
import json, os, subprocess, pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── stats CSV ────────────────────────────────────────────────────────────────
stats_path = os.path.join(_ROOT, "repo_maps", "map_generation_stats.csv")
stats = pd.read_csv(stats_path)

out_dir       = os.path.join(_ROOT, "repo_maps", "keras", "15")
ast_path      = os.path.join(out_dir, "ast_map.json")
compact_path  = os.path.join(out_dir, "compact_map.txt")
freq_path     = os.path.join(out_dir, "freq_map.txt")
cochange_path = os.path.join(out_dir, "cochange_map.txt")

def fchars(p):
    return len(open(p, encoding="utf-8", errors="replace").read()) if os.path.exists(p) else None

n_files, n_records, ast_chars = 0, 0, 0
files_seen = set()
with open(ast_path, encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        if line:
            n_records += 1
            ast_chars += len(line) + 1
            try: files_seen.add(json.loads(line)["file"])
            except: pass
n_files = len(files_seen)

cc = fchars(compact_path); fc = fchars(freq_path); coc = fchars(cochange_path)
r = subprocess.run(["git", "-C", os.path.join(_ROOT, "repos/keras_full"),
    "log", "-1", "--format=%ci", "80fbbc3a"], capture_output=True, text=True)
cdate = r.stdout.strip().split()[0]

new_row = {
    "repo": "keras", "tier": "medium", "issue_idx": 15, "role": "flexible",
    "base_commit": "80fbbc3a", "commit_date": cdate, "package_dir": out_dir,
    "n_source_files": n_files, "n_ast_records": n_records,
    "ast_map_chars": ast_chars, "ast_map_tokens": ast_chars // 4,
    "compact_map_chars": cc, "compact_map_tokens": cc // 4 if cc else None,
    "compact_reduction_pct": round((1 - cc / ast_chars) * 100, 1) if cc and ast_chars else None,
    "freq_map_chars": fc, "freq_map_tokens": fc // 4 if fc else None,
    "cochange_map_chars": coc, "cochange_map_tokens": coc // 4 if coc else None,
    "status": "success", "error_message": "", "duration_seconds": 141.3,
}
stats = pd.concat([stats, pd.DataFrame([new_row])], ignore_index=True)
stats.to_csv(stats_path, index=False)
print(f"stats saved — {len(stats)} rows")
print(f"keras/15: compact={new_row['compact_map_tokens']} tok  freq={new_row['freq_map_tokens']} tok")

# ── issue selection CSV ──────────────────────────────────────────────────────
sel_path = os.path.join(_ROOT, "data", "issue_selection_random.csv")
sel = pd.read_csv(sel_path)

# replace the keras/12 flexible duplicate row with keras/15 flexible
dup = (sel["repo"] == "keras") & (sel["issue_idx"] == 12) & (sel["role"] == "flexible")
sel.loc[dup, "issue_idx"]    = 15
sel.loc[dup, "ground_truth"] = str(["keras/backend/theano_backend.py",
                                     "keras/layers/advanced_activations.py"])
sel.to_csv(sel_path, index=False)
print("issue_selection_random.csv updated — keras/12 flexible → keras/15 flexible")
print(sel[sel["repo"] == "keras"][["issue_idx", "role", "ground_truth"]].to_string())
