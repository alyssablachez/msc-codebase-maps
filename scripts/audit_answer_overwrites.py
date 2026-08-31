"""
Studies 1, 2, and 3 -- generalized screen for trials where a well-formed
candidate answer appeared earlier in the transcript and was later replaced
by a worse final answer, by ANY mechanism -- not just Study 3's explicit
submit-gate rejection (scripts/audit_gate_overwrites.py covers that
specific case; this script is the superset, covering the same question
across all three studies including the ones with no gate at all).

Two distinct ways a trial's transcript can contain a "lost" candidate:
  1. REJECTED_SUBMIT  -- a submit_answer tool call that was rejected
     (Study 3's required-tool gate only; Study 1/2 have no gate, so this
     is always empty for them).
  2. FORCED_OVERWRITE -- the trial did not end via a normal mid-loop
     submit_answer call, so the harness's forced final-answer elicitation
     (harness/run_trial.py's "if not submitted" block) generated a *new*
     tool call/text response, while the model had already stated a
     parseable, well-formed file list in an earlier message's content
     (the original Study-0-era CONTENT_ANSWER pattern) that the forced
     answer disagreed with. Only flagged when the two differ.

For every trial with >=1 candidate from either mechanism, this records the
LAST such candidate (closest to the eventual outcome) and its F1 against
ground truth, alongside the actual final answer's F1, so the real
performance cost (if any) is visible rather than just a syntactic diff.

Usage:
    python3 scripts/audit_answer_overwrites.py
"""
import glob
import json
import os
import re

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUDIES = {
    "study_1": os.path.join(_ROOT, "study_1", "results"),
    "study_2": os.path.join(_ROOT, "study_2", "results"),
    "study_3": os.path.join(_ROOT, "study_3", "results"),
}
OUT_CSV = os.path.join(_ROOT, "data", "answer_overwrite_audit.csv")

PY_PATH_RE = re.compile(r'\b([\w][\w/\-]*\.[a-zA-Z]+)\b')


def _is_well_formed(files):
    return isinstance(files, list) and len(files) > 0 and all(isinstance(f, str) and f.strip() for f in files)


def _f1(pred, gt):
    p, t = set(pred), set(gt)
    if not t:
        return None
    if not p:
        return 0.0
    tp = len(p & t)
    precision = tp / len(p)
    recall = tp / len(t)
    return 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0


def _recover_files_from_content(text):
    """Deliberately narrower than scripts/audit_empty_predictions.py's
    version: only the two structured-JSON patterns (a JSON array, or a
    {"files": [...]} object), no bare-path regex fallback. The bare-path
    fallback is appropriate when scanning a single specific turn already
    known to be the model's final-answer statement (as Study 0's audit
    used it), but here it was initially applied to every assistant turn
    across the whole transcript and matched incidental file mentions in
    ordinary reasoning prose ("checking app.py, then logging.getLogger")
    as if they were stated answers -- a first pass produced 3,016 "flagged"
    trials (39% of all data), which is implausible on its face and traced
    directly to this over-permissive matching. Restricting to
    structured-JSON-only, combined with only checking the single last
    normal assistant turn (see classify_trial), removes that false-positive
    source."""
    if not text:
        return []
    for match in re.finditer(r'\[([^\[\]]*\.[a-zA-Z]+[^\[\]]*)\]', text, re.DOTALL):
        try:
            parsed = json.loads("[" + match.group(1) + "]")
            files = [f for f in parsed if isinstance(f, str) and "." in f]
            if files:
                return files
        except json.JSONDecodeError:
            pass
    for match in re.finditer(r'\{[^{}]*"files"\s*:\s*(\[[^\[\]]*\])[^{}]*\}', text, re.DOTALL):
        try:
            files_list = json.loads(match.group(1))
            files = [f for f in files_list if isinstance(f, str)]
            if files:
                return files
        except json.JSONDecodeError:
            pass
    return []


def classify_trial(d):
    transcript = d.get("transcript", [])
    final_files = d.get("final_files_predicted") or []
    gt = d.get("ground_truth_scorable") or d.get("ground_truth") or []
    final_f1 = _f1(final_files, gt)
    stop_reason = d.get("metrics", {}).get("stop_reason", "")

    candidates = []  # (mechanism, turn, files)

    # REJECTED_SUBMIT: every rejected submit_answer attempt is a genuine,
    # deliberate answer statement regardless of where in the transcript it
    # falls -- scanning all of them is correct (validated against Study 3).
    for t in transcript:
        if t.get("turn") == "final":
            continue
        if t.get("role") == "tool" and t.get("name") == "submit_answer" and t.get("rejected"):
            files = t.get("args", {}).get("files", [])
            if _is_well_formed(files):
                candidates.append(("REJECTED_SUBMIT", t.get("turn"), files))

    # CONTENT_STATED: only meaningful, and only checked, when the trial did
    # NOT end via a normal submit_answer call -- i.e. the forced-elicitation
    # fallback (harness/run_trial.py's "if not submitted" block) is what
    # actually produced final_files_predicted, so a genuine prior answer
    # could have been discarded. For a normally "submitted" trial there is
    # no fallback and nothing to overwrite. Only the single LAST normal
    # assistant turn is checked (matching audit_empty_predictions.py's
    # _last_normal_assistant_content convention), not the whole transcript.
    if stop_reason != "submitted":
        last_content_turn = None
        for t in reversed(transcript):
            if t.get("turn") == "final":
                continue
            if t.get("role") == "assistant" and t.get("content"):
                last_content_turn = t
                break
        if last_content_turn is not None:
            files = _recover_files_from_content(str(last_content_turn["content"]))
            if _is_well_formed(files):
                candidates.append(("CONTENT_STATED", last_content_turn.get("turn"), files))

    if not candidates:
        return None

    # Only meaningful if the final answer came via a route that could have
    # discarded it -- i.e. the last candidate's file set differs from the
    # final one. Identical-set cases (candidate later formally resubmitted)
    # are not an overwrite.
    last_mechanism, last_turn, last_files = candidates[-1]
    if set(last_files) == set(final_files):
        return None

    candidate_f1 = _f1(last_files, gt)

    return {
        "mechanism":       last_mechanism,
        "candidate_turn":  last_turn,
        "candidate_files": json.dumps(last_files),
        "candidate_f1":    candidate_f1,
        "final_files":     json.dumps(final_files),
        "final_f1":        final_f1,
        "n_candidates":    len(candidates),
        "stop_reason":     d.get("metrics", {}).get("stop_reason", ""),
    }


def main():
    rows = []
    for study, results_dir in STUDIES.items():
        files = glob.glob(os.path.join(results_dir, "**", "*.json"), recursive=True)
        print(f"Scanning {study}: {len(files)} trial files...")
        for fp in files:
            try:
                d = json.load(open(fp, encoding="utf-8"))
            except Exception as e:
                print(f"WARNING: could not read {fp}: {e}")
                continue
            row = classify_trial(d)
            if row is not None:
                row["study"] = study
                row["model"] = d.get("model", "")
                row["repo"] = d.get("repo", "")
                row["issue_idx"] = d.get("issue_idx")
                row["map_type"] = d.get("map_type", "")
                row["rep"] = d.get("rep")
                row["file"] = os.path.relpath(fp, results_dir)
                rows.append(row)

    df = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    print(f"\n{'='*70}\nTotal trials with a lost/overwritten candidate answer: {len(df)}\n{'='*70}")
    print(df.groupby(["study", "mechanism"]).size().to_string())

    worse = df[df["final_f1"] < df["candidate_f1"]]
    better = df[df["final_f1"] > df["candidate_f1"]]
    same = df[df["final_f1"] == df["candidate_f1"]]
    print(f"\nfinal F1 WORSE than the lost candidate's: {len(worse)}")
    print(f"final F1 BETTER than the lost candidate's: {len(better)}")
    print(f"same F1 despite different file sets:       {len(same)}")

    if len(worse):
        print(f"\n{'='*70}\nTRIALS WHERE THE OVERWRITE MADE THE OUTCOME WORSE\n{'='*70}")
        for _, r in worse.sort_values(["study", "file"]).iterrows():
            print(f"  [{r['study']}] {r['model']}/{r['repo']}/{r['issue_idx']}/{r['map_type']}/{r['file']}")
            print(f"    mechanism={r['mechanism']}  turn={r['candidate_turn']}")
            print(f"    candidate (F1={r['candidate_f1']:.3f}): {r['candidate_files']}")
            print(f"    final     (F1={r['final_f1']:.3f}): {r['final_files']}")
            print()

    print(f"Saved: {OUT_CSV}")


if __name__ == "__main__":
    main()
