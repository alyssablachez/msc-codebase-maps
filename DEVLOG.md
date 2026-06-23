# Development Log

## 2026-06-22 (Week 4)
- Reorganized project directory structure

## 2026-06-23 (Week 4)

- Made first git commit and pushed project to GitHub (msc-codebase-maps)
- Set up SSH authentication for git
- Discovered AST and ctags maps disagreed significantly in size at some commits (ctags up to 3x larger than AST)
- Root cause: `requests` vendored third-party dependencies (urllib3, chardet, idna) under `requests/packages/` during 2013–2016; ctags' whole-repo recursive scan picked these up, AST's shallow directory walk didn't
- Refactored monolithic map generation script into modular, independently-callable scripts: `generate_ast_map.py`, `generate_ctags_map.py`, `compare_maps.py`, `estimate_tokens.py`, plus shared `git_utils.py`
- First fix attempt: excluded `tests`, `docs`, `packages` via ctags `--exclude` flags — worked, but discovered a stray `test_requests.py` at repo root (pre-2014 layout) slipped through since it wasn't inside a `tests/` folder
- Decided on more principled fix: point both AST and ctags directly at the resolved package directory (`requests/` or `src/requests/`) rather than the whole repo + growing exclude list
- Made AST recursive to match ctags' `--recurse`, but this reintroduced the vendored-packages problem since `packages/` lives *inside* the package folder itself
- Final fix: explicit `--exclude-dirs` (default `["packages"]`) applied to both tools when recursing through the package directory, configurable for future codebases with different vendoring conventions
- Regenerated all 5 task maps; comparison still needs verification after latest fix

**Key learning:** real historical codebases have packaging quirks (vendoring) that aren't visible from current HEAD — worth checking structure at each target commit before assuming map generation logic transfers cleanly across commits.

**Next:** verify final map sizes/comparison, then build run_trial.py harness (Week 3 goal, now overdue)

