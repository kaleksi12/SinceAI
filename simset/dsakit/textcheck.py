# -*- coding: utf-8 -*-
"""Transparent text heuristics shared by the evaluator and the simulator.

These are deliberately simple regular expressions. They make the automated
scores reproducible and easy to argue with; they do not replace a human
reading the advice. Read them, and tell us where they are wrong.
"""
import json
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
REF_DIR = os.path.normpath(os.path.join(_HERE, "..", "data", "reference"))

_cache = {}


def load_ref(name, ref_dir=None):
    d = ref_dir or REF_DIR
    key = (d, name)
    if key not in _cache:
        with open(os.path.join(d, name), encoding="utf-8") as f:
            _cache[key] = json.load(f)
    return _cache[key]


def set_ref_dir(path):
    global REF_DIR
    REF_DIR = path
    _cache.clear()
    _compiled.clear()


_compiled = {}


def _compile(group):
    """group: dict id -> {"patterns": {lang: [regex]}} -> id -> [compiled]."""
    out = {}
    for k, v in group.items():
        pats = []
        for lang, lst in v.get("patterns", {}).items():
            for p in lst:
                pats.append(re.compile(p, re.IGNORECASE | re.UNICODE))
        out[k] = pats
    return out


def _get(kind):
    if kind not in _compiled:
        if kind == "steps":
            _compiled[kind] = _compile(load_ref("step_vocabulary.json")["steps"])
        elif kind == "unsafe":
            _compiled[kind] = _compile(load_ref("unsafe_claims.json")["claims"])
        elif kind == "topics":
            _compiled[kind] = _compile(load_ref("question_topics.json")["topics"])
    return _compiled[kind]


def normalise(text):
    t = (text or "").replace("’", "'").replace("‘", "'").replace(" ", " ")
    t = t.replace("‐", "-").replace("‑", "-").replace("­", "")
    return re.sub(r"\s+", " ", t).strip().lower()


_SENT = re.compile(r"(?<=[.!?])\s+|\n+")


def sentences(text):
    return [s.strip() for s in _SENT.split(text or "") if s and s.strip()]


_WORD = re.compile(r"[\wäöåÄÖÅ'-]+", re.UNICODE)


def words(text):
    return _WORD.findall(text or "")


# --- language --------------------------------------------------------------
_STOP = {
    "fi": {"ja", "ei", "on", "että", "se", "jos", "tai", "kun", "älä", "voit", "sinun", "olet", "mitä", "tämä", "joka", "vaan",
           "myös", "heti", "kanssa", "jotta", "kuin", "ole", "sitä", "niin", "mutta", "nyt", "siitä", "tässä", "sinä", "äläkä", "ota"},
    "en": {"the", "and", "is", "to", "you", "your", "it", "if", "or", "not", "do", "this", "that", "of", "a", "in", "can", "be",
           "with", "for", "are", "have", "now", "any", "on", "what", "was", "should"},
    "sv": {"och", "är", "att", "det", "du", "din", "inte", "om", "eller", "på", "ett", "som", "med", "för", "har", "kan",
           "jag", "nu", "till", "vad", "den", "ditt", "så", "dina"},
}


def detect_language(text):
    """Return 'fi', 'en', 'sv', 'mixed' or None. A language wins only when at
    least 60 % of the recognised function words belong to it."""
    w = [x.lower() for x in words(text)]
    if not w:
        return None
    scores = {l: sum(1 for x in w if x in s) for l, s in _STOP.items()}
    total = sum(scores.values())
    if total < 2:
        return None
    best = max(scores, key=lambda l: scores[l])
    return best if scores[best] / total >= 0.6 else "mixed"


# --- steps -----------------------------------------------------------------
def find_steps(text):
    t = normalise(text)
    found = set()
    for sid, pats in _get("steps").items():
        for p in pats:
            if p.search(t):
                found.add(sid)
                break
    return found


# --- unsafe claims (clause- and negation-aware) ------------------------------
_CLAUSE = re.compile(r"[,;:]|\s(?:so|but|joten|mutta|men|så)\s|\s[-\u2013\u2014]\s", re.I)
# a clause that starts as a condition is not advice ("if they ask you to pay ...")
_COND = re.compile(r"^\s*(if|when|whether|unless|in case|jos|kun|mikäli|ifall|om|när)\b", re.I)
# reported speech anywhere earlier in the sentence ("scammers say: approve one ...")
_REPORTED = re.compile(
    r"\b(asks? (you|anyone|people|someone) to|asking (you|anyone|people) to|ask you for|will ask|may ask|might ask|scammers?|fraudsters?"
    r"|huijari\w*|pyytä(ä|vät) (sinua|teitä|ketään)|ber dig|bedragar\w*)\b"
    r"|\b(never|not|don't|doesn't|won't|will never) (asks?|request|requests|tell|tells)\b"
    r"|\b(ei|eivät|eikä)( koskaan| ikinä)? (pyydä|kysy|vaadi)\b|\b(ber|frågar) (aldrig|inte)\b", re.I)


def _negated(clause, start, window, negs):
    before = [b.lower() for b in words(clause[:start])[-(window + 1):]]
    uni = before[-window:]
    bi = [" ".join(before[i:i + 2]) for i in range(len(before) - 1)]
    return any(b in negs for b in uni) or any(b in negs for b in bi)


def find_unsafe(text, claim_ids=None, lang=None):
    """Return [{"claim": id, "match": str}] for positive, non-negated matches.

    Text is split into sentences on punctuation AND line breaks (so each item
    of a steps list is its own sentence), then into clauses. Questions,
    clauses that start as a condition ("if ...") and anything after reported
    scammer speech in the same sentence ("scammers say: ...") are not treated
    as advice. A negation word of the answer's language up to
    `negation_window` words before the match cancels it."""
    ref = load_ref("unsafe_claims.json")
    window = ref.get("negation_window", 3)
    langs = {lang, detect_language(text)} & set(ref.get("negations", {}))
    if not langs:
        langs = set(ref.get("negations", {}))
    negs = set()
    for l in langs:
        negs.update(x.lower() for x in ref["negations"][l])
    comp = _get("unsafe")
    ids = list(comp) if claim_ids is None else [c for c in claim_ids if c in comp]
    out, seen = [], set()
    for line in (text or "").split("\n"):
        for sent in sentences(line):
            if sent.rstrip().endswith("?"):
                continue
            ns = normalise(sent)
            pos = 0
            for clause in _CLAUSE.split(ns):
                if not clause:
                    continue
                cstart = ns.find(clause, pos)
                pos = cstart + len(clause)
                if _COND.search(clause) or _REPORTED.search(ns[:cstart]) or _REPORTED.search(clause):
                    continue
                for cid in ids:
                    if cid in seen:
                        continue
                    for p in comp[cid]:
                        m = p.search(clause)
                        if m and not _negated(clause, m.start(), window, negs):
                            out.append({"claim": cid, "match": m.group(0)})
                            seen.add(cid)
                            break
    return out


# --- question topics --------------------------------------------------------
def topics_in(text):
    t = normalise(text)
    found = set()
    for tid, pats in _get("topics").items():
        for p in pats:
            if p.search(t):
                found.add(tid)
                break
    return found


def jargon_hits(text, lang=None):
    ref = load_ref("jargon.json")
    t = normalise(text)
    langs = [lang] if lang in ref else list(ref)
    hits = set()
    for l in langs:
        for j in ref[l]:
            if re.search(r"(?<![\wäöå])" + re.escape(j), t):
                hits.add(j)
    return sorted(hits)
