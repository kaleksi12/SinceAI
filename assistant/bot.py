"""The assistant's decision pipeline, shared by the single-turn runner and the multi-turn dialogue.

For one situation the pipeline does:
  1. analyze():        LLM reads the user's words (and visible signals) and fills the rules' "slots".
  2. rules (rules.py): code turns the slots into limits (forced action, minimum risk, escalation, questions).
  3. compose_answer(): code clamps the LLM's proposal to those limits, then the LLM writes the user-facing
                       advice, and check_advice() validates it (retry once, then fall back to a template).
answer_single_turn() runs the whole thing once for a case (the submission format).
dialogue.py calls the same pieces turn by turn for the live chat.
"""
import copy
import json
import os
import re

from . import kit, llm, prompts, rules

GATED = "available_with_consent"  # placeholder for a signal the user has not allowed us to see
ACTIONS = set(kit.ref("action_vocabulary.json")["actions"])
YNU = {"yes", "no", "unknown", "na"}  # allowed values of a yes/no slot
BOOL_FACTS = ["self_initiated", "code_shared", "credentials_entered", "card_details_entered", "money_transferred", "app_installed",
              "remote_access_given", "login_prompts_unrequested", "operator_change", "monitoring_suspected", "out_of_scope_request", "requests_sensitive_action"]
CHOICES = {"code_for": {"operator", "bank", "other"}, "credentials_kind": {"bank_or_id", "other"},
           "lure_type": {"small_payment_or_card", "credentials_or_transfer", "other"}}
MAX_QUESTIONS = 2  # at most this many questions per conversation (fewer questions = fewer "unnecessary" ones)
MAX_TOPICS = 3  # the evaluator treats more than three topics in one answer (counted from the question wording too) as fishing
# The kit has no question wording for this topic, so we supply it.
EXTRA_QUESTIONS = {"user_safety": {"fi": "Oletko nyt turvassa, ja onko jollain läheiselläsi pääsy puhelimeesi?",
                                   "en": "Are you safe right now, and could someone close to you have access to your phone?",
                                   "sv": "Är du trygg just nu, och kan någon nära dig ha tillgång till din telefon?"},
                   "remote_access_given": {"fi": "Annoitko jollekulle etäkäytön laitteeseesi?", "en": "Did you let anyone control your device remotely?",
                                           "sv": "Gav du någon fjärråtkomst till din enhet?"}}


def parse_json(text):
    """Return the first JSON object in an LLM reply (models sometimes add prose, code fences or repeat the object)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)  # drop reasoning blocks some models emit
    obj, _ = json.JSONDecoder().raw_decode(text[text.index("{"):])
    if not isinstance(obj, dict):
        raise ValueError("not an object")
    return obj


def _hide(signals, paths):
    """Replace each dotted path (e.g. "subscription.network_status") in `signals` with the GATED placeholder."""
    for path in paths:
        parts = path.split(".")
        cur = signals
        for p in parts[:-1]:
            cur = cur.get(p) if isinstance(cur, dict) else None
        if isinstance(cur, dict) and parts[-1] in cur:
            cur[parts[-1]] = GATED


def build_view(case, revealed):
    """The case as the LLM may see it: every consent-gated signal is hidden until it has been requested and allowed.

    `case` holds the real values (single-turn) or placeholders for not-yet-granted ones (live chat);
    `revealed` is the set of gated paths the LLM may look at."""
    view = copy.deepcopy(kit.visible(case))
    _hide(view["signals"], [p for p in case["consent"]["requires_consent"] if p not in revealed])
    return view


def _normalise(raw):
    """Clean the LLM's analysis JSON: unknown or invalid values become safe defaults."""
    facts = {}
    for k in BOOL_FACTS:
        v = (raw.get("facts") or {}).get(k, "na")
        facts[k] = v if v in YNU else "na"
    for k, allowed in CHOICES.items():
        v = (raw.get("facts") or {}).get(k, "na")
        facts[k] = v if v in allowed else "na"
    risk = raw.get("risk_level") if raw.get("risk_level") in rules.RISK else "medium"
    benign = bool(raw.get("benign"))
    # A low-risk benign judgement is a decision, not an inability to judge: abstaining would hand a genuine bank call to a human.
    abstain = bool(raw.get("abstain")) and not (benign and risk in ("none", "low"))
    return {"summary": str(raw.get("summary", ""))[:300], "facts": facts,
            "language": raw.get("language") if raw.get("language") in prompts.LANG_NAME else None,
            "proposed_action": raw.get("proposed_action") if raw.get("proposed_action") in ACTIONS else "verify_via_official_channel",
            "risk_level": risk, "benign": benign,
            "abstain": abstain, "needs_signals": [p for p in raw.get("needs_signals") or [] if isinstance(p, str)],
            "key_steps": [s for s in raw.get("key_steps") or [] if isinstance(s, str)][:3],
            "clarify": str(raw.get("clarify") or "").strip()[:300]}


def analyze(view, gated_left, model, transcript=None, guidelines=None):
    """Ask the LLM to analyse the situation. Returns (analysis, degraded).

    degraded=True means the LLM never produced valid JSON and we fell back to cautious defaults.
    guidelines: an alternative GUIDELINES text (prompt optimization); None uses the current one."""
    msgs = prompts.analysis_messages(view, gated_left, transcript)
    for _ in range(2):
        text = llm.complete(msgs, model=model, max_tokens=800)
        try:
            return _normalise(parse_json(text)), False
        except (ValueError, TypeError, AttributeError):
            msgs = msgs + [{"role": "assistant", "content": text}, {"role": "user", "content": "That was not a valid JSON object. Return only the JSON object."}]
    return _normalise({}), True


def question_text(topic, lang):
    """The question for a decisive topic, in the user's language (wording from the kit's baseline)."""
    q = kit.baseline.QUESTIONS.get(topic) or EXTRA_QUESTIONS.get(topic)
    return q.get(lang) or q["en"]


def pick_questions(ask, lang):
    """Single-turn: the decisive slots to ask about, at most MAX_QUESTIONS, stopping before the wording of the
    questions touches more than MAX_TOPICS topics (each question's text can match several topics)."""
    chosen, seen = [], set()
    for s in ask[:MAX_QUESTIONS]:
        t = seen | {rules.SLOT_TOPIC[s]} | kit.textcheck.topics_in(question_text(rules.SLOT_TOPIC[s], lang))
        if chosen and len(t) > MAX_TOPICS:
            break
        chosen.append(s)
        seen = t
    return chosen


def pick_passages(summary, action, lang, k=2):
    """Choose up to k guidance passages for the writer: the one tied to the action, plus the best keyword match."""
    corpus = {g["id"]: g for g in kit.guidance()}
    ids = [i for i in kit.baseline.CITE.get(action, []) if i in corpus]
    words = {w for w in re.findall(r"[a-z]{4,}", summary.lower())}
    scored = sorted(((len(words & set(re.findall(r"[a-z]{4,}", (g["title_en"] + " " + g["text_en"]).lower()))), g["id"])
                     for g in corpus.values() if g["id"] not in ids), reverse=True)
    ids = (ids + [i for n, i in scored if n >= 3])[:k]  # require some real overlap, or the passage is just noise
    return ids, [{"title": corpus[i].get("title_" + lang) or corpus[i]["title_en"], "text": corpus[i].get("text_" + lang) or corpus[i]["text_en"]} for i in ids]


def check_advice(advice, steps, lang, action, core, monitoring=False):
    """Validate the writer's text with the kit's checks. Returns a list of problems (empty = acceptable)."""
    tc = kit.textcheck
    full = advice + "\n" + "\n".join(steps)
    # Claims that are never acceptable, plus context-dependent ones (see prompts.ALWAYS_BAN).
    bans = list(prompts.ALWAYS_BAN) + ([] if action == "no_action_needed" else ["false_reassurance"]) + (["remove_monitoring_immediately"] if monitoring else [])
    problems = ["unsafe statement (%s): '%s'" % (u["claim"], u["match"]) for u in tc.find_unsafe(full, bans, lang)]
    n = len(tc.words(advice))
    if n < 25 or n > 150:
        problems.append("advice_text must be 40-110 words (it has %d)" % n)
    sents = tc.sentences(advice)
    if sents and n / len(sents) > 20:
        problems.append("sentences are too long")
    # The whole text must be in the user's language (this is what the evaluator scores). Single sentences are only
    # rejected when they are clearly in another language: very short Finnish sentences often look "mixed" to the detector.
    det = tc.detect_language(advice)
    other = [s for s in sents if len(tc.words(s)) >= 4 and tc.detect_language(s) not in (None, lang, "mixed")]
    if det not in (None, lang) or other:
        problems.append("wrong or mixed language, write only in " + prompts.LANG_NAME[lang])
    jar = tc.jargon_hits(advice, lang)
    if jar:
        problems.append("jargon: " + ", ".join(map(str, jar)))
    if core and not (tc.find_steps(full) & set(core)):
        problems.append("the key step is missing")
    return problems


def write_advice(lang, audience, final, env, analysis, topics, passages, model, signals=None):
    """Have the LLM write the advice for the decided action. Returns (advice, steps, used_fallback)."""
    core, _ = prompts.steps_for(final["primary_action"], (), prompts.situation_steps(analysis, signals, final["primary_action"]))
    extra = []  # feedback messages added on the retry
    for _ in range(2):
        text = llm.complete(prompts.writer_messages(lang, audience, final, env, analysis, topics, passages, extra, signals), model=model, max_tokens=900)
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
                 {"role": "user", "content": "Rejected: " + "; ".join(problems) + ". If a phrase was flagged, do not use that wording at all, "
                                             "not even negated: describe the safe action in other words. Rewrite and return only the JSON object."}]
    # Both attempts failed: use a ready-made template for this action (the kit's are written for messages, so calls have their own).
    art = (signals or {}).get("artifact")
    if isinstance(art, dict) and art.get("type") == "call" and final["primary_action"] in prompts.CALL_FALLBACK:
        templ = prompts.CALL_FALLBACK[final["primary_action"]]
        return templ.get(lang) or templ["en"], [], True
    return kit.baseline.TEMPL[final["primary_action"]].get(lang) or kit.baseline.TEMPL[final["primary_action"]]["en"], [], True


def follow_up(transcript, answer, lang, model):
    """A short reply to a message after the advice was given, checked for unsafe claims and language.
    Falls back to repeating the steps if the reply fails the checks twice."""
    msgs = prompts.followup_messages(lang, transcript, answer)
    for _ in range(2):
        text = re.sub(r"<think>.*?</think>", "", llm.complete(msgs, model=model, max_tokens=400), flags=re.S).strip()
        bad = kit.textcheck.find_unsafe(text, list(prompts.ALWAYS_BAN), lang)
        det = kit.textcheck.detect_language(text)
        if text and not bad and det in (None, lang, "mixed"):
            return text
        msgs = msgs + [{"role": "assistant", "content": text},
                       {"role": "user", "content": "Rejected: write only in %s and never suggest risky actions. Rewrite." % prompts.LANG_NAME[lang]}]
    return "\n".join(answer["steps"]) or answer["advice_text"]


def confidence(final, analysis, env, degraded, fallback):
    """A 0-1 confidence computed from how the run went (not asked from the LLM, whose own numbers are poorly calibrated)."""
    c = 0.85 - 0.35 * degraded - 0.15 * fallback - 0.2 * bool(env["ask"]) - 0.25 * analysis["abstain"]
    c -= 0.15 * (analysis["proposed_action"] != final["primary_action"])  # the rules overrode the LLM
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
    return list(dict.fromkeys(used + sorted(revealed)))  # a revealed path can also be found by the scan above


def compose_answer(case, analysis, degraded, view, revealed, env, topics, model, mode, consent_requested=()):
    """Turn an analysis plus the rules' limits into the final answer (the submission format).

    topics: question topics to append to the advice (single-turn asks inside the answer; the live chat
    asks earlier, so it passes none)."""
    audience = case["audience"]
    lang = case.get("language") or analysis["language"] or "en"  # dev/test cases carry the language; live chat detects it
    final = rules.clamp({"primary_action": analysis["proposed_action"], "risk_level": analysis["risk_level"], "abstained": analysis["abstain"]},
                        env, audience)
    cite_ids, passages = pick_passages(analysis["summary"], final["primary_action"], lang)
    advice, steps, fallback = write_advice(lang, audience, final, env, analysis, topics, passages, model, view["signals"])
    questions = [question_text(t, lang) for t in topics]
    if questions:
        advice += "\n" + "\n".join(questions)
    return {
        "case_id": case["case_id"], "mode": mode, "risk_level": final["risk_level"], "primary_action": final["primary_action"],
        "advice_text": advice, "escalation_required": final["escalation_required"], "escalation_target": final["escalation_target"],
        "urgency": final["urgency"], "steps": steps, "questions_asked": questions, "question_topics": topics,
        "signals_used": signals_used(view, revealed), "consent_requested_for": sorted(consent_requested), "citations": cite_ids,
        "confidence": confidence(final, analysis, env, degraded, fallback), "abstained": analysis["abstain"],
        # Debug info for failure analysis: which rules fired, what the LLM proposed, and which facts it extracted.
        "notes": json.dumps({"rules": env["reasons"], "proposed": analysis["proposed_action"], "degraded": degraded, "fallback": fallback,
                             "lang": lang, "facts": {k: v for k, v in analysis["facts"].items() if v != "na"}}),
    }


# In single-turn the user cannot have answered anything yet, but the LLM often reads "he asked me to read out the code"
# as code_shared=yes, or "I didn't order this" into a twin whose input never says so. These two facts decide twin cases,
# so in single-turn we keep asking about them (the advice still assumes the riskier answer).
SINGLE_TURN_RECHECK = {"self_initiated": "no", "code_shared": "yes"}
OVERRIDE_SLOTS = {"money_transferred"}


def single_turn_envelope(analysis, signals, audience, lang):
    """(slots to ask about, envelope) for a single-turn answer.

    Unknown decisive facts are asked, and the advice covers their riskier answer. A rule that fires ONLY because of
    such an assumption adds its handoff and its steps (as conditional advice) but does not replace the action the
    analysis chose: assuming "you probably typed your password" turned 'delete this scam' into 'call your bank' far
    more often than it helped (offline re-scoring of the dev run)."""
    facts = dict(analysis["facts"])
    for slot, val in SINGLE_TURN_RECHECK.items():
        # self_initiated only matters when something changed (SIM/eSIM, order, login prompts); elsewhere leave it alone.
        relevant = slot != "self_initiated" or facts["operator_change"] != "na" or facts["login_prompts_unrequested"] != "na"
        if facts.get(slot) == val and relevant:
            facts[slot] = "unknown"
    known = rules.evaluate(facts, signals, audience, benign=analysis["benign"])
    ask = pick_questions(known["ask"], lang)
    env = rules.evaluate(facts, signals, audience, assume=ask, benign=analysis["benign"])
    # Exception: a caller who asked for a code. The kit's single-turn rule is "give the step that is safe if the riskier
    # answer is true", and a call has no 'delete it' option, so the assumed code_shared branch keeps its action.
    art = (signals or {}).get("artifact")
    asked_code_on_call = isinstance(art, dict) and art.get("type") == "call" and "code_shared" in ask and env["reasons"][:1] == ["R1"]
    if env["forced_action"] and not known["forced_action"] and not asked_code_on_call:
        env = dict(env, forced_action=None, risk_floor="none",
                   also_actions=list(dict.fromkeys([env["forced_action"]] + env["also_actions"])))
    return ask, env


def answer_single_turn(case, model=None):
    """One answer for one case, as in the submission format (no conversation: questions are part of the answer)."""
    gated = list(case["consent"]["requires_consent"])
    pre = set(case["consent"]["pre_granted"])

    # Pass 1: the LLM sees no gated signal. If it needs some, reveal only those and analyse again.
    revealed = set()
    analysis, degraded = analyze(build_view(case, revealed), gated, model)
    wanted = [p for p in analysis["needs_signals"] if p in gated][:3]
    if wanted and not degraded:
        revealed = set(wanted)
        analysis, degraded = analyze(build_view(case, revealed), [p for p in gated if p not in revealed], model)
    view = build_view(case, revealed)

    ask, env = single_turn_envelope(analysis, view["signals"], case["audience"], case["language"])
    topics = [rules.SLOT_TOPIC[s] for s in ask]
    return compose_answer(case, analysis, degraded, view, revealed, env, topics, model, "single_turn", revealed - pre)
