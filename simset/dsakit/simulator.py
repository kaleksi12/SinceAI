# -*- coding: utf-8 -*-
"""Simulated user for multi-turn practice on the dev split.

The simulated user knows a few facts (case["simulation"]["facts"]). It reveals
a fact only when the assistant asks about that topic. It answers consent
requests according to case["simulation"]["consent_policy"].

The simulator is intentionally literal: it does not volunteer information and
it does not reward clever phrasing. Ask clearly about one thing at a time.
"""
import copy

from . import textcheck

SENSITIVE_HIDDEN = "available_with_consent"
# exactly the fields of a test input: no labels, families, tags or difficulty
VISIBLE_KEYS = ["case_id", "split", "version", "journey", "audience", "locale", "language", "persona", "entry_point", "user_identified",
                "opening_message", "signals", "signal_availability", "consent"]
MAX_TOPICS_PER_QUESTION = 2
ONE_AT_A_TIME = {"fi": "Kysyisitkö yhden asian kerrallaan? En oikein ymmärrä, mitä haluat tietää.",
                 "en": "Could you ask one thing at a time? I'm not sure what you want to know.",
                 "sv": "Kan du fråga en sak i taget? Jag förstår inte riktigt vad du vill veta."}


def visible_case(case, granted=()):
    """What an assistant may see at the start of a multi-turn conversation:
    no ground truth, no simulation facts, and consent-gated signals replaced by
    a placeholder until permission has been granted."""
    c = {k: copy.deepcopy(case[k]) for k in VISIBLE_KEYS if k in case}
    granted = set(granted) | set(case.get("consent", {}).get("pre_granted", []))
    for path in case.get("consent", {}).get("requires_consent", []):
        if path in granted:
            continue
        parts = path.split(".")
        cur = c["signals"]
        for p in parts[:-1]:
            cur = cur.get(p, {})
        if parts[-1] in cur:
            cur[parts[-1]] = SENSITIVE_HIDDEN
    return c


def reveal_signals(case, paths):
    out = {}
    for path in paths:
        cur = case["signals"]
        ok = True
        for p in path.split("."):
            if isinstance(cur, dict) and p in cur:
                cur = cur[p]
            else:
                ok = False
                break
        if ok:
            out[path] = copy.deepcopy(cur)
    return out


class UserSimulator:
    def __init__(self, case):
        if "simulation" not in case:
            raise ValueError("case %s has no simulation block (test inputs cannot be simulated locally)" % case.get("case_id"))
        self.case = case
        self.sim = case["simulation"]
        self.lang = self.sim["language"]
        self.asked_topics = []          # topics per question, in order
        self.revealed = []              # topics whose facts were revealed
        self.unmatched_questions = 0
        self.granted = set(case.get("consent", {}).get("pre_granted", []))
        self.refused = set()

    def answer(self, question_text, topics=None):
        """Return the simulated user's reply to one assistant question."""
        explicit = [t for t in (topics or []) if isinstance(t, str)]
        detected = set(explicit) | textcheck.topics_in(question_text if isinstance(question_text, str) else "")
        if len(explicit) > MAX_TOPICS_PER_QUESTION or len(detected) > MAX_TOPICS_PER_QUESTION + 1:
            # a shotgun question reveals nothing and counts as an unnecessary question
            self.asked_topics.append(["__too_many__"])
            return ONE_AT_A_TIME.get(self.lang, ONE_AT_A_TIME["en"])
        detected = sorted(detected)
        self.asked_topics.append(detected)
        replies = []
        for t in sorted(detected):
            fact = self.sim["facts"].get(t)
            if fact and t not in self.revealed:
                replies.append(fact)
                self.revealed.append(t)
            elif fact:
                replies.append(fact)
        if not detected:
            self.unmatched_questions += 1
        if not replies:
            return self.sim["unknown_reply"]
        return " ".join(dict.fromkeys(replies))

    def consent(self, fields):
        fields = [f for f in (fields or []) if isinstance(f, str) and f in self.case.get("consent", {}).get("requires_consent", [])]
        if self.sim.get("consent_policy") == "refuse":
            self.refused.update(fields)
            return {"granted": [], "refused": fields, "text": self.sim["consent_reply"]}
        self.granted.update(fields)
        return {"granted": fields, "refused": [], "text": self.sim["consent_reply"],
                "signals": reveal_signals(self.case, fields)}

    def summary(self):
        gt = self.case["ground_truth"]
        relevant = set(gt.get("relevant_topics", []))
        unnecessary = sum(1 for ts in self.asked_topics if ts and not (set(ts) & relevant))
        return {
            "questions": len(self.asked_topics),
            "unmatched_questions": self.unmatched_questions,
            "unnecessary_questions": unnecessary,
            "revealed_topics": list(self.revealed),
            "must_ask_satisfied": all(t in sum(self.asked_topics, []) for t in gt.get("must_ask_topics", [])),
            "shotgun_questions": sum(1 for ts in self.asked_topics if ts == ["__too_many__"]),
            "consent_granted": sorted(self.granted),
            "consent_refused": sorted(self.refused),
        }
