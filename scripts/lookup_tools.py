"""
Execution logic for the lookup_* tools (see lookup_tool_schemas.py for the
JSON schemas handed to the model). Shared by every harness/run_trial_*.py
tool-based variant so the actual read/render/paginate logic lives in one
place rather than duplicated across files -- same rationale as
repo_config.py/source_filter.py being centralized.

Reads from the full, path-indexed maps (ast_index_full.json /
freq_index_full.json / cochange_index_full.json, see
generate_all_indexes.py), not the old budget-capped wholesale maps.

See DEVLOG 2026-07-16 for the cap/pagination design rationale:
- lookup_structure paginates by member (class/function) index, capped at
  STRUCTURE_CAP_CHARS per call, because ast record size has an
  unbounded-feeling tail (worst case ~48k tokens for one file).
- lookup_cochange has a model-chosen top_k with no hard ceiling, because
  partner-list length is naturally bounded (worst case ~12k tokens
  uncapped, since partner count tops out around ~1,000).
- lookup_frequency needs no cap at all (~9-10 tokens per file, always).
"""
import json
import os

STRUCTURE_CAP_CHARS = 40_000
DEFAULT_COCHANGE_TOP_K = 10

# (maps_root, repo, issue_idx, kind) -> loaded index dict, or None if the
# index file doesn't exist. Cached per-process: a single trial may look up
# many files from the same issue's index, and each index is unchanged for
# the lifetime of a trial (a fresh subprocess per trial, see run_trial.py).
_index_cache = {}


def _load_index(maps_root, repo, issue_idx, kind):
    """kind: 'ast', 'freq', or 'cochange'."""
    key = (maps_root, repo, issue_idx, kind)
    if key not in _index_cache:
        path = os.path.join(maps_root, repo, str(issue_idx), f"{kind}_index_full.json")
        if not os.path.exists(path):
            _index_cache[key] = None
        else:
            with open(path, encoding="utf-8") as f:
                _index_cache[key] = json.load(f)
    return _index_cache[key]


def _flatten_ast_members(record):
    """Ordered list of rendered text blocks, one per class or function:
    each class (with its own docstring) immediately followed by its
    methods, then trailing module-level functions -- matches
    compact_map.py's existing grouping, just not re-truncated (full
    docstrings, not first-line-only)."""
    methods_by_class = {}
    module_functions = []
    for fn in record.get("functions", []):
        cls = fn.get("class")
        if cls:
            methods_by_class.setdefault(cls, []).append(fn)
        else:
            module_functions.append(fn)

    members = []
    for cls in record.get("classes", []):
        bases = cls.get("bases") or []
        header = (f"class {cls['name']}({', '.join(bases)}) L{cls['line']}"
                  if bases else f"class {cls['name']} L{cls['line']}")
        block = header
        if cls.get("docstring"):
            block += f'\n  "{cls["docstring"].strip()}"'
        members.append(block)
        for fn in methods_by_class.get(cls["name"], []):
            sig = fn.get("signature") or "()"
            fblock = f"  {fn['name']}{sig} L{fn['line']}"
            if fn.get("docstring"):
                fblock += f'\n    "{fn["docstring"].strip()}"'
            members.append(fblock)
    for fn in module_functions:
        sig = fn.get("signature") or "()"
        block = f"{fn['name']}{sig} L{fn['line']}"
        if fn.get("docstring"):
            block += f'\n  "{fn["docstring"].strip()}"'
        members.append(block)
    return members


def execute_lookup_structure(args, repo, issue_idx, maps_root):
    path = args.get("path") or ""
    if not path:
        return "Error: path argument is required"

    index = _load_index(maps_root, repo, issue_idx, "ast")
    if index is None:
        return "Error: no structural index available for this issue"
    record = index.get(path)
    if record is None:
        return f"Error: no structural data for '{path}' (not a known file in this package)"

    members = _flatten_ast_members(record)
    if not members:
        return f"[{path}: no top-level classes or functions]"

    try:
        offset = int(args.get("offset") or 1)
    except (TypeError, ValueError):
        offset = 1
    offset = max(1, offset)
    if offset > len(members):
        return (f"Error: offset={offset} is past the end of {path} "
                f"({len(members)} members total)")

    chars = 0
    included = []
    i = offset - 1
    while i < len(members):
        block = members[i]
        block_len = len(block) + 1
        # Always include at least one member per page, even if it alone
        # exceeds the cap -- a page must never come back empty.
        if included and chars + block_len > STRUCTURE_CAP_CHARS:
            break
        chars += block_len
        included.append(block)
        i += 1
    next_offset = i + 1
    last_shown = offset + len(included) - 1

    if next_offset <= len(members):
        header = (f"[{path}: members {offset}-{last_shown} of {len(members)}. "
                   f"More available -- call again with offset={next_offset}.]")
    else:
        header = f"[{path}: members {offset}-{last_shown} of {len(members)} (end of file).]"

    return header + "\n\n" + "\n".join(included)


def execute_lookup_frequency(args, repo, issue_idx, maps_root):
    path = args.get("path") or ""
    if not path:
        return "Error: path argument is required"

    index = _load_index(maps_root, repo, issue_idx, "freq")
    if index is None:
        return "Error: no frequency index available for this issue"
    record = index.get(path)
    if record is None:
        return f"Error: no frequency data for '{path}' (not a known file in this package)"

    edits = record.get("edits", 0)
    last_edit = record.get("last_edit", "unknown")
    return f"{path}: {edits} historical edits, last edited {last_edit}"


def execute_lookup_cochange(args, repo, issue_idx, maps_root):
    path = args.get("path") or ""
    if not path:
        return "Error: path argument is required"

    index = _load_index(maps_root, repo, issue_idx, "cochange")
    if index is None:
        return "Error: no co-change index available for this issue"
    partners = index.get(path)
    if partners is None:
        return f"Error: no co-change data for '{path}' (not a known file in this package)"
    if not partners:
        return f"[{path}: no recorded co-change partners]"

    try:
        top_k = int(args.get("top_k") or DEFAULT_COCHANGE_TOP_K)
    except (TypeError, ValueError):
        top_k = DEFAULT_COCHANGE_TOP_K
    top_k = max(1, top_k)

    sub = partners[:top_k]
    lines = [f"  {p['file']}  ({p['count']} co-changes)" for p in sub]
    header = f"[{path}: top {len(sub)} of {len(partners)} total co-change partners]"
    return header + "\n" + "\n".join(lines)
