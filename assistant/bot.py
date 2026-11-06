"""Single-turn assistant: LLM analysis -> rules envelope -> LLM wording -> validation."""
import copy
import json
import os
import re

from . import kit, llm, prompts, rules

GATED = "available_with_consent"
ACTIONS = set(kit.ref("action_vocabulary.json")["actions"])
YNU = {"yes", "no", "unknown", "na"}
BOOL_FACTS = ["self_initiated", "code_shared", "credentials_entered", "card_details_entered", "money_transferred", "app_installed",
              "remote_access_given", "operator_change", "monitoring_suspected", "out_of_scope_request", "requests_sensitive_action"]
CHOICES = {"code_for": {"operator", "bank", "other"}, "credentials_kind": {"bank_or_id", "other"},
           "lure_type": {"small_payment_or_card", "credentials_or_transfer", "other"}}
MAX_QUESTIONS = 2
EXTRA_QUESTIONS = {"remote_access_given": {"fi": "Annoitko soittajalle etäkäytön laitteeseesi?", "en": "Did you let the caller control your device remotely?",
                                           "sv": "Gav du uppringaren fjärråtkomst till din enhet?"}}


def parse_json(text):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    obj, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    return obj


def _hide(signals, paths):
    for path in paths:
        parts = path.split(".")
        cur = signals
        for p in parts[:-1]:
            cur = cur.get(p) if isinstance(cur, dict) else None
        if isinstance(cur, dict) and parts[-1] in cur:
            cur[parts[-1]] = GATED


def build_view(case, revealed):
    """The case as the LLM may see it: every consent-gated signal is hidden until requested."""
    view = copy.deepcopy(kit.visible(case))
    _hide(view["signals"], [p for p in case["consent"]["requires_consent"] if p not in revealed])
    return view


def _normalise(raw):
    facts = {}
    for k in BOOL_FACTS:
        v = (raw.get("facts") or {}).get(k, "na")
        facts[k] = v if v in YNU else "na"
    for k, allowed in CHOICES.items():
        v = (raw.get("facts") or {}).get(k, "na")
        facts[k] = v if v in allowed else "na"
    risk = raw.get("risk_level")
    return {"summary": str(raw.get("summary", ""))[:300], "facts": facts,
            "proposed_action": raw.get("proposed_action") if raw.get("proposed_action") in ACTIONS else "verify_via_official_channel",
            "risk_level": risk if risk in rules.RISK else "medium", "benign": bool(raw.get("benign")),
            "abstain": bool(raw.get("abstain")), "needs_signals": [p for p in raw.get("needs_signals") or [] if isinstance(p, str)]}


def analyze(view, gated_left, model):
    """Returns (analysis, degraded)."""
    msgs = prompts.analysis_messages(view, gated_left)
    for _ in range(2):
        text = llm.complete(msgs, model=model, max_tokens=800)
        try:
            return _normalise(parse_json(text)), False
        except (ValueError, TypeError, AttributeError):
            msgs = msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": "That was not a valid JSON object. Return only the JSON object."}]
    return _normalise({}), True


def question_text(topic, lang):
    q = kit.baseline.QUESTIONS.get(topic) or EXTRA_QUESTIONS.get(topic)
    return q.get(lang) or q["en"]


def pick_passages(summary, action, lang, k=2):
    corpus = {g["id"]: g for g in kit.guidance()}
    ids = [i for i in kit.baseline.CITE.get(action, []) if i in corpus]
    words = {w for w in re.findall(r"[a-z]{4,}", summary.lower())}
    scored = sorted(((len(words & set(re.findall(r"[a-z]{4,}", (g["title_en"] + " " + g["text_en"]).lower()))), g["id"])
                     for g in corpus.values() if g["id"] not in ids), reverse=True)
    ids = (ids + [i for n, i in scored if n >= 3])[:k]
    return ids, [{"title": corpus[i].get("title_" + lang) or corpus[i]["title_en"], "text": corpus[i].get("text_" + lang) or corpus[i]["text_en"]} for i in ids]


def check_advice(advice, steps, lang, action, core, monitoring=False):
    tc = kit.textcheck
    full = advice + "\n" + "\n".join(steps)
    bans = list(prompts.ALWAYS_BAN) + ([] if action == "no_action_needed" else ["false_reassurance"]) + (["remove_monitoring_immediately"] if monitoring else [])
    problems = ["unsafe statement (%s): '%s'" % (u["claim"], u["match"]) for u in tc.find_unsafe(full, bans, lang)]
    n = len(tc.words(advice))
    if n < 25 or n > 150:
        problems.append("advice_text must be 40-110 words (it has %d)" % n)
    sents = tc.sentences(advice)
    if sents and n / len(sents) > 20:
        problems.append("sentences are too long")
    det = tc.detect_language(advice)
    if det not in (None, lang) or any(tc.detect_language(s) not in (None, lang) for s in sents if len(tc.words(s)) >= 4):
        problems.append("wrong or mixed language, write only in " + prompts.LANG_NAME[lang])
    jar = tc.jargon_hits(advice, lang)
    if jar:
        problems.append("jargon: " + ", ".join(map(str, jar)))
    if core and not (tc.find_steps(full) & set(core)):
        problems.append("the key step is missing")
    return problems


def write_advice(lang, audience, final, env, analysis, topics, passages, model):
    """Returns (advice, steps, used_fallback)."""
    core, _ = prompts.steps_for(final["primary_action"])
    extra = []
    for _ in range(2):
        text = llm.complete(prompts.writer_messages(lang, audience, final, env, analysis, topics, passages, extra), model=model, max_tokens=900)
        try:
            out = parse_json(text)
            advice, steps = str(out["advice_text"]).strip(), [str(s) for s in out.get("steps") or []][:5]
            problems = check_advice(advice, steps, lang, final["primary_action"], core, analysis["facts"]["monitoring_suspected"] == "yes")
        except (ValueError, TypeError, KeyError, AttributeError):
            advice, steps, problems = "", [], ["the reply was not a valid JSON object"]
        if not problems:
            return advice, steps, False
        if os.environ.get("DSA_DEBUG"):
            print("  [rejected %s] %s" % (final["primary_action"], "; ".join(problems)))
        extra = [{"role": "assistant", "content": text},
                 {"role": "user", "content": "Rejected: " + "; ".join(problems) + ". Rewrite and return only the JSON object."}]
    return kit.baseline.TEMPL[final["primary_action"]].get(lang) or kit.baseline.TEMPL[final["primary_action"]]["en"], [], True


def confidence(final, analysis, env, degraded, fallback):
    c = 0.85 - 0.35 * degraded - 0.15 * fallback - 0.2 * bool(env["ask"]) - 0.25 * analysis["abstain"]
    c -= 0.15 * (analysis["proposed_action"] != final["primary_action"])
    return round(max(0.2, c), 2)


def signals_used(view, revealed):
    """Signal paths exactly as named in the kit's signal dictionary (what the submission schema accepts)."""
    valid = set(kit.ref("signal_dictionary.json")["signals"])
    used = []
    for k, v in view["signals"].items():
        if v is None or v == GATED:
            continue
        if k in valid:
            used.append(k)
        elif isinstance(v, dict):
            used += ["%s.%s" % (k, s) for s, x in v.items() if x not in (None, GATED) and "%s.%s" % (k, s) in valid]
    return used + sorted(revealed)


def answer_single_turn(case, model=None):
    """One answer per case, as in the submission format."""
    lang, audience = case["language"], case["audience"]
    gated = list(case["consent"]["requires_consent"])
    pre = set(case["consent"]["pre_granted"])

    revealed = set()
    analysis, degraded = analyze(build_view(case, revealed), gated, model)
    wanted = [p for p in analysis["needs_signals"] if p in gated][:3]
    if wanted and not degraded:
        revealed = set(wanted)
        analysis, degraded = analyze(build_view(case, revealed), [p for p in gated if p not in revealed], model)
    view = build_view(case, revealed)

    env = rules.evaluate(analysis["facts"], view["signals"], audience, assume_unknown_yes=True)
    final = rules.clamp({"primary_action": analysis["proposed_action"], "risk_level": analysis["risk_level"], "abstained": analysis["abstain"]},
                        env, audience)
    topics = env["ask_topics"][:MAX_QUESTIONS]
    cite_ids, passages = pick_passages(analysis["summary"], final["primary_action"], lang)
    advice, steps, fallback = write_advice(lang, audience, final, env, analysis, topics, passages, model)
    questions = [question_text(t, lang) for t in topics]
    if questions:
        advice += "\n" + "\n".join(questions)

    return {
        "case_id": case["case_id"], "mode": "single_turn", "risk_level": final["risk_level"], "primary_action": final["primary_action"],
        "advice_text": advice, "escalation_required": final["escalation_required"], "escalation_target": final["escalation_target"],
        "urgency": final["urgency"], "steps": steps, "questions_asked": questions, "question_topics": topics,
        "signals_used": signals_used(view, revealed), "consent_requested_for": sorted(revealed - pre), "citations": cite_ids,
        "confidence": confidence(final, analysis, env, degraded, fallback), "abstained": analysis["abstain"],
        "notes": json.dumps({"rules": env["reasons"], "proposed": analysis["proposed_action"], "degraded": degraded, "fallback": fallback,
                             "facts": {k: v for k, v in analysis["facts"].items() if v != "na"}}),
    }
