#!/usr/bin/env python3
"""
Strip `urldate` (access date) from BibTeX entries that don't need one under
Vancouver / NLM rules: formally published work (journal articles, conference
papers, books) and archival preprints (arXiv, SSRN) keep a fixed version, so
no access date. Web pages, blogs, vendor docs, web-only reports, and online
news keep their urldate.

Usage:
    python3 scripts/scrub_urldate.py references.bib            # writes references.clean.bib
    python3 scripts/scrub_urldate.py references.bib out.bib
"""
import re
import sys

FIELD_RE = re.compile(r'^\s*([A-Za-z_-]+)\s*=', re.MULTILINE)
TYPE_RE = re.compile(r'@(\w+)\s*\{\s*([^,]+),', re.DOTALL)


def entry_fields(body: str) -> dict:
    """Crude field map: name -> raw value text (good enough for detection)."""
    out = {}
    for m in FIELD_RE.finditer(body):
        name = m.group(1).lower()
        # grab from after '=' to the line's logical end (next '\n  <field> =' or entry end)
        start = m.end()
        rest = body[start:]
        nxt = FIELD_RE.search(rest)
        val = rest[: nxt.start()] if nxt else rest
        out[name] = val
    return out


def should_strip(etype: str, f: dict) -> bool:
    etype = etype.lower()
    url = (f.get("url", "") + f.get("eprint", "")).lower()
    doi = f.get("doi", "").lower()
    is_preprint = (
        "arxiv.org" in url
        or "ssrn" in url
        or "eprinttype" in f
        or doi.strip().strip("{} ").startswith("10.48550")
        or doi.strip().strip("{} ").startswith("10.2139")
    )
    if etype in {"inproceedings", "incollection", "inbook", "conference", "book"}:
        return True
    if etype == "article":
        # academic article iff it has a DOI or a volume; news @article has neither
        return ("doi" in f) or ("volume" in f)
    if etype in {"misc", "unpublished"}:
        return is_preprint
    # @online, @report, @www, @electronic, @techreport, @manual -> keep
    return False


def process(text: str):
    out = []
    stripped, kept = [], []
    pos = 0
    for m in re.finditer(r'@\w+\s*\{', text):
        # find matching close brace for this entry
        i = m.end()
        depth = 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        entry = text[m.start():i]
        tm = TYPE_RE.match(entry)
        etype, key = tm.group(1), tm.group(2).strip()
        f = entry_fields(entry)
        out.append(text[pos:m.start()])
        if "urldate" in f and should_strip(etype, f):
            entry = re.sub(r'\n[ \t]*urldate\s*=\s*\{[^}]*\}\s*,?', "", entry, count=1)
            stripped.append(key)
        elif "urldate" in f:
            kept.append(key)
        out.append(entry)
        pos = i
    out.append(text[pos:])
    return "".join(out), stripped, kept


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "references.bib"
    dst = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + ".clean.bib"
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    new, stripped, kept = process(text)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(new)
    print(f"wrote {dst}")
    print(f"\nstripped urldate ({len(stripped)}):")
    for k in stripped:
        print(f"  - {k}")
    print(f"\nkept urldate ({len(kept)}):")
    for k in kept:
        print(f"  - {k}")
