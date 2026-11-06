#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check that the package is intact and internally consistent, or validate a
submission file before you hand it in.

    python3 tools/validate.py                                  # whole package
    python3 tools/validate.py --submission my_test_predictions.jsonl --cases data/test/inputs.jsonl
"""
import argparse
import hashlib
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)

from dsakit import minischema, textcheck  # noqa: E402
from dsakit.scoring import load_jsonl  # noqa: E402

RESERVED = re.compile(r"(\.example(\.com|\.net|\.org)?|\.invalid|\.test|\.localhost)$", re.I)


def schema(name):
    with open(os.path.join(ROOT, "schema", name + ".schema.json"), encoding="utf-8") as f:
        return json.load(f)


def check_manifest(errors):
    p = os.path.join(ROOT, "MANIFEST.json")
    if not os.path.exists(p):
        return "no MANIFEST.json (source checkout)"
    with open(p, encoding="utf-8") as f:
        man = json.load(f)
    bad = 0
    for rel, info in man["files"].items():
        fp = os.path.join(ROOT, rel)
        if not os.path.exists(fp):
            errors.append("manifest: missing file %s" % rel)
            bad += 1
            continue
        h = hashlib.sha256(open(fp, "rb").read()).hexdigest()
        if h != info["sha256"]:
            errors.append("manifest: checksum mismatch %s" % rel)
            bad += 1
    return "%d files listed, %d problems" % (len(man["files"]), bad)


def visible_signature(c):
    keep = {k: c[k] for k in ("journey", "audience", "language", "persona", "opening_message", "signals", "signal_availability", "consent")}
    return json.dumps(keep, sort_keys=True, ensure_ascii=False)


def check_data(errors, warnings):
    if not os.path.exists(os.path.join(ROOT, "data/dev/cases.jsonl")):
        test = load_jsonl(os.path.join(ROOT, "data/test/inputs.jsonl"))
        ts = schema("test_input")
        for c in test:
            for e in minischema.validate(c, ts)[:3]:
                errors.append("%s: %s" % (c["case_id"], e))
        return 0, len(test), 0
    ref = textcheck.load_ref("action_vocabulary.json")
    guidance = {json.loads(l)["id"] for l in open(os.path.join(ROOT, "data/reference/guidance_corpus.jsonl"), encoding="utf-8") if l.strip()}
    dev = load_jsonl(os.path.join(ROOT, "data/dev/cases.jsonl"))
    test = load_jsonl(os.path.join(ROOT, "data/test/inputs.jsonl"))
    cs, ts = schema("case"), schema("test_input")
    for c in dev:
        for e in minischema.validate(c, cs)[:3]:
            errors.append("%s: %s" % (c["case_id"], e))
        for r in c["ground_truth"]["guidance_refs"]:
            if r not in guidance:
                errors.append("%s: unknown guidance ref %s" % (c["case_id"], r))
    for c in test:
        for e in minischema.validate(c, ts)[:3]:
            errors.append("%s: %s" % (c["case_id"], e))
        if "ground_truth" in c or "simulation" in c:
            errors.append("%s: test input leaks ground truth" % c["case_id"])
    ids = [c["case_id"] for c in dev + test]
    if len(ids) != len(set(ids)):
        errors.append("duplicate case ids")
    # twins: identical visible input, different ground truth
    groups = {}
    for c in dev:
        g = c["ground_truth"].get("twin_group")
        if g:
            groups.setdefault(g, []).append(c)
    for g, members in groups.items():
        if len(members) != 2:
            errors.append("twin group %s has %d members" % (g, len(members)))
            continue
        a, b = members
        if visible_signature(a) != visible_signature(b):
            errors.append("twin group %s: visible inputs differ" % g)
        if a["ground_truth"]["branch"] == b["ground_truth"]["branch"]:
            errors.append("twin group %s: same branch twice" % g)
    # domains reserved, no live links
    for c in dev + test:
        art = c["signals"]["artifact"]
        texts = [art["body"], art["sender"], c["opening_message"]] + art["links"]
        lc = c["signals"].get("link_check")
        if isinstance(lc, dict):
            texts.append(lc["url"])
        for t in texts:
            for host in re.findall(r"https?://([^/\s]+)", t) + re.findall(r"@([a-z0-9.-]+\.[a-z]+)", t, re.I):
                host = host.rstrip(".,)")
                if not RESERVED.search(host):
                    errors.append("%s: non-reserved domain %s" % (c["case_id"], host))
    # dev families do not include hold-out families
    hold = {c["scenario_family"] for c in dev if c.get("holdout_family")}
    if hold:
        errors.append("hold-out families present in dev: %s" % sorted(hold))
    return len(dev), len(test), len(groups)


def check_submission(path, cases_path, errors, allow_partial=False):
    ss = schema("submission")
    cases = load_jsonl(cases_path)
    ids = {c["case_id"] for c in cases}
    subs = load_jsonl(path)
    seen = set()
    for i, s in enumerate(subs, 1):
        if not isinstance(s, dict):
            errors.append("line %d: not a JSON object" % i)
            continue
        for e in minischema.validate(s, ss)[:5]:
            errors.append("line %d (%s): %s" % (i, s.get("case_id"), e))
        cid = s.get("case_id")
        if cid not in ids:
            errors.append("line %d: unknown case_id %s" % (i, cid))
        if cid in seen:
            errors.append("line %d: duplicate case_id %s" % (i, cid))
        seen.add(cid)
    missing = ids - seen
    print("submission: %d lines, %d cases covered, %d missing" % (len(subs), len(seen & ids), len(missing)))
    if missing and not allow_partial:
        errors.append("%d case(s) have no answer, e.g. %s (use --allow-partial while developing)" % (len(missing), sorted(missing)[:5]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--submission")
    ap.add_argument("--cases", default=os.path.join(ROOT, "data/test/inputs.jsonl"))
    ap.add_argument("--allow-partial", action="store_true", help="do not fail when some cases have no answer")
    a = ap.parse_args()
    errors, warnings = [], []
    if a.submission:
        check_submission(a.submission, a.cases, errors, a.allow_partial)
    else:
        print("manifest:", check_manifest(errors))
        nd, nt, ng = check_data(errors, warnings)
        print("data: %d dev cases, %d test inputs, %d twin groups in dev" % (nd, nt, ng) if nd else "data: %d test inputs" % nt)
    for w in warnings:
        print("WARNING", w)
    if errors:
        for e in errors[:40]:
            print("ERROR", e)
        print("%d error(s)" % len(errors))
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
