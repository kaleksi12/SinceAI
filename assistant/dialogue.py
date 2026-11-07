"""The live-chat engine: multi-turn conversation following the organisers' bot protocol.

step(event, state) is the single entry point. It speaks the kit's protocol (simset/sim/PROTOCOL.md), so the same
code is used by
  * the web API (api.py), where a person types, and
  * the kit's simulated user: python simset/sim/run_conversation.py --bot-py assistant/dialogue.py:step ...

Events in:  start (the case), user_reply (text), consent_reply (granted/refused/signals), turn_limit.
Replies out: question, consent_request, or final (the answer in the submission format).

Each turn the whole conversation so far is analysed again by the LLM (bot.analyze), then code decides what to do:
  1. If it needs a sensitive signal the user has not allowed yet: ask for consent (once per conversation).
  2. Else if a decisive fact is still unknown: ask one question (at most MAX_QUESTIONS per conversation).
  3. Else give the final answer. Facts we asked about but never got a clear answer to are treated as the riskier branch.
"""
import copy
import re
import sys
from pathlib import Path

# Allow this file to be loaded by path (the kit's runner does that) as well as imported as part of the package.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from assistant import bot, rules  # noqa: E402

MAX_CONSENT_FIELDS = 3  # never ask for more than this many signals at once
MAX_CLARIFY = 1  # free text only: open "what happened?" questions before we must answer
# Live chat: a user who says they do not know gets the answer now (for the riskier branch) instead of more questions.
DONT_KNOW = re.compile(r"\b(do ?n[o']?t know|dunno|not sure|no idea|can'?t remember|do ?n[o']?t remember)\b|\ben (tiedä|tie|muista|ole varma)\b|"
                       r"\bei (hajua|aavistustakaan)\b|\bvet inte\b|\bingen aning\b|\bminns inte\b", re.I)
CONFUSED = re.compile(r"^\W*(what|huh|eh|sorry|pardon|what do you mean|mitä|mitä tarkoitat|häh|en ymmärrä|i don'?t understand|vad|va|förstår inte)?\W*$|"
                      r"\b(how is (this|that|it) relevant|why (do you ask|are you asking|does (it|that|this) matter)|what does (that|this|it) have to do|"
                      r"miksi kysyt|mitä (se|tämä) liittyy|miten (se|tämä) liittyy|varför frågar du)\b", re.I)

# What we tell the user we would look at, per consent-gated signal path (the kit's signal_dictionary has English only).
FIELD_LABELS = {
    "subscription.recent_events": {"en": "recent SIM/eSIM and order events on your subscription",
                                   "fi": "liittymäsi viimeaikaiset SIM/eSIM- ja tilaustapahtumat",
                                   "sv": "senaste SIM-/eSIM- och beställningshändelser på ditt abonnemang"},
    "subscription.network_status": {"en": "whether your line has network service right now",
                                    "fi": "onko liittymälläsi tällä hetkellä verkkoyhteys",
                                    "sv": "om din linje har nätverksuppkoppling just nu"},
    "device.recent_app_installs": {"en": "apps installed on this device in the last 14 days",
                                   "fi": "tälle laitteelle viimeisen 14 päivän aikana asennetut sovellukset",
                                   "sv": "appar installerade på den här enheten de senaste 14 dagarna"},
    "device.security_findings": {"en": "findings from the operator's security app",
                                 "fi": "operaattorin tietoturvasovelluksen havainnot",
                                 "sv": "fynd från operatörens säkerhetsapp"},
    "operator_account.recent_logins": {"en": "recent logins to your operator account",
                                       "fi": "operaattoritilisi viimeaikaiset kirjautumiset",
                                       "sv": "senaste inloggningarna på ditt operatörskonto"},
    "credential_exposure": {"en": "the result of a breach check for your email address",
                            "fi": "sähköpostiosoitteesi tietovuototarkistuksen tulos",
                            "sv": "resultatet av en dataläckskontroll för din e-postadress"},
    "business.staff_accounts": {"en": "your company's user list and last activity",
                                "fi": "yrityksesi käyttäjälista ja viimeisin aktiivisuus",
                                "sv": "ditt företags användarlista och senaste aktivitet"},
}
CONSENT_TEXT = {
    "en": "To give you better advice, may I look at: %s? I will only use it in this conversation.",
    "fi": "Voinko antaa parempaa neuvontaa katsomalla: %s? Käytän tietoa vain tämän keskustelun ajan.",
    "sv": "För att ge bättre råd, får jag titta på: %s? Jag använder det bara i den här konversationen.",
}


def field_label(path, lang):
    return FIELD_LABELS.get(path, {}).get(lang) or FIELD_LABELS.get(path, {}).get("en") or path


def _set_path(signals, path, value):
    """Store a released signal value at its dotted path, e.g. signals["subscription"]["network_status"]."""
    parts = path.split(".")
    cur = signals
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = cur[p] = {}
        cur = nxt
    cur[parts[-1]] = value


def step(event, state):
    """Handle one event and return the bot's reply. `state` persists through one conversation."""
    kind = event["type"]
    if kind == "start":
        case = copy.deepcopy(event["case"])
        state.clear()
        state.update(case=case, model=event.get("model"), revealed=set(), refused=set(), consent_requested=set(),
                     asked=[], clarified=0, lang=case.get("language"), last=None, live=bool(event.get("live")), awaiting=False,
                     transcript=[{"role": "user", "text": case["opening_message"]}])
    elif kind == "user_reply":
        state["transcript"].append({"role": "user", "text": event["text"]})
    elif kind == "consent_reply":
        # The values of the signals the user allowed arrive with the event; refused ones never do.
        for path, value in (event.get("signals") or {}).items():
            _set_path(state["case"]["signals"], path, value)
        state["revealed"] |= set(event.get("granted") or [])
        state["refused"] |= set(event.get("refused") or [])
        if event.get("text"):
            state["transcript"].append({"role": "user", "text": event["text"]})
    reply = None
    if state["live"] and kind in ("start", "user_reply") and not state["awaiting"]:
        reply = _route(state)
    q = state.get("last_question")
    if state["live"] and kind == "user_reply" and state["awaiting"] and q and not q.get("explained") and CONFUSED.search(event["text"]):
        # "what??" is not an answer: explain why we ask and ask the same thing again, in other words.
        q["explained"] = True  # only once: a second "what?" gets the answer for the riskier branch
        text = bot.phrase_question(q["topic"], state["transcript"], state["lang"] or "en", state["case"]["audience"], state["model"], explain=True) \
            if q["topic"] else q["text"]
        state["transcript"].append({"role": "assistant", "text": text})
        return {"type": "question", "text": text, "topics": [q["topic"]] if q["topic"] else []}
    dont_know = state["live"] and kind == "user_reply" and state["awaiting"] and bool(DONT_KNOW.search(event["text"]) or CONFUSED.search(event["text"]))
    reply = reply or _advance(state, force_final=(kind == "turn_limit") or dont_know)
    state["awaiting"] = reply["type"] in ("question", "consent_request")  # the next message answers our question
    return reply


def _drop_off_topic_facts(facts):
    """Live chat: the model marks facts "unknown" that the story never touches, and each one becomes a question
    (and, after "I don't know", a worst-case action). Only keep the ones the story makes relevant."""
    if facts["code_shared"] == "unknown" and facts["code_for"] == "na":
        facts["code_shared"] = "na"  # nobody asked for a code
    if facts["self_initiated"] == "unknown" and "yes" not in (facts["operator_change"], facts["login_prompts_unrequested"]):
        facts["self_initiated"] = "na"  # "did you order this change?" only fits when something changed


def _lang(state, analysis=None):
    """The reply language. Live chat: the language of the user's latest message when it can be detected (people type
    their own text over a Finnish sample, or switch language); otherwise the case's, the analysis' or the last one."""
    if state.get("live"):
        user = [t["text"] for t in state["transcript"] if t["role"] == "user"]
        det = bot.kit.textcheck.detect_language(user[-1]) if user else None
        if det in ("fi", "en", "sv"):
            return det
    return state["case"].get("language") or (analysis or {}).get("language") or state["lang"] or "en"


def _route(state):
    """Live chat only (the web demo, never the kit's simulation): small talk, general security questions and
    follow-ups after an answer get a short grounded reply; only a (new) incident goes through the decision pipeline.
    Returns None for an incident. A long first message is clearly a situation: skip the extra LLM call."""
    text = state["transcript"][-1]["text"]
    if not state["last"] and len(text.split()) >= 12:
        return None
    lang = _lang(state) if state["live"] and bot.kit.textcheck.detect_language(text) else state["lang"]
    r = bot.route(state["transcript"], state["last"] and state["last"]["answer"], lang, state["model"])
    if not r:
        return None
    state["lang"] = r["language"]
    state["transcript"].append({"role": "assistant", "text": r["reply"]})
    state["debug"] = {"route": r["intent"], "language": state["lang"]}
    return {"type": "message", "text": r["reply"]}


def _advance(state, force_final):
    case = state["case"]
    gated = list(case["consent"]["requires_consent"])
    pre = set(case["consent"]["pre_granted"])

    # Analyse the conversation; if the LLM needs sensitive signals, release pre-allowed ones silently and ask for the rest.
    while True:
        view = bot.build_view(case, state["revealed"])
        left = [p for p in gated if p not in state["revealed"] and p not in state["refused"]]
        analysis, degraded = bot.analyze(view, left, state["model"], state["transcript"])
        if state.get("live"):
            _drop_off_topic_facts(analysis["facts"])
        wanted = [p for p in analysis["needs_signals"] if p in left][:MAX_CONSENT_FIELDS]
        if not wanted or degraded or force_final:
            break
        auto = [p for p in wanted if p in pre]  # allowed in the user's settings already: no need to ask again
        if auto:
            state["revealed"].update(auto)
            continue
        if state["consent_requested"]:  # one consent request per conversation: never ask again and again
            break
        lang = _lang(state, analysis)
        state["lang"] = lang
        state["consent_requested"] |= set(wanted)
        text = CONSENT_TEXT[lang] % "; ".join(field_label(p, lang) for p in wanted)
        state["transcript"].append({"role": "assistant", "text": text})
        state["debug"] = _debug(state, analysis, degraded)
        return {"type": "consent_request", "fields": wanted, "text": text}

    lang = _lang(state, analysis)
    state["lang"] = lang
    audience = case["audience"]

    # After an answer, a new message is usually a follow-up ("how do I do that?", "thanks"): reply to it in context
    # instead of producing a whole new advice card, unless what the user said changes the decision.
    if state["last"] and not force_final:
        env_now = rules.evaluate(analysis["facts"], view["signals"], audience, assume=env_assumed(analysis, state), benign=analysis["benign"])
        now = rules.clamp({"primary_action": analysis["proposed_action"], "risk_level": analysis["risk_level"], "abstained": analysis["abstain"]}, env_now, audience)
        prev = state["last"]["answer"]
        if now["primary_action"] == prev["primary_action"] and now["escalation_required"] == prev["escalation_required"]:
            text = bot.follow_up(state["transcript"], prev, lang, state["model"])
            state["transcript"].append({"role": "assistant", "text": text})
            state["debug"] = _debug(state, analysis, degraded, env_now)
            return {"type": "message", "text": text}

    env0 = rules.evaluate(analysis["facts"], view["signals"], audience, benign=analysis["benign"])

    # Free text only (the web demo): if the user has not said what happened yet, ask an open question first.
    # Not when we already know enough to ask a decisive question or a rule fired; never in the kit's simulation.
    if (case["case_id"].startswith("DEMO-") and analysis["clarify"] and not state["last"] and not force_final
            and not env0["ask"] and not env0["forced_action"]
            and state["clarified"] < MAX_CLARIFY and analysis["proposed_action"] != "decline_out_of_scope"):
        state["clarified"] += 1
        state["last_question"] = {"topic": None, "text": analysis["clarify"]}
        state["transcript"].append({"role": "assistant", "text": analysis["clarify"]})
        state["debug"] = _debug(state, analysis, degraded)
        return {"type": "question", "text": analysis["clarify"], "topics": []}

    # Decisive facts still unknown (ordered by priority); ask about the first one we have not asked yet.
    # Live chat counts the open question too: at most MAX_QUESTIONS questions before the answer.
    unknown = env0["ask"]
    pending = [s for s in unknown if rules.SLOT_TOPIC[s] not in state["asked"]]
    if pending and not force_final and len(state["asked"]) + (state["clarified"] if state.get("live") else 0) < bot.MAX_QUESTIONS:
        topic = rules.SLOT_TOPIC[pending[0]]
        state["asked"].append(topic)
        # Live chat: the question is phrased for this conversation (e.g. about "your employee", not "you").
        text = bot.phrase_question(topic, state["transcript"], lang, audience, state["model"]) if state.get("live") else bot.question_text(topic, lang)
        state["last_question"] = {"topic": topic, "text": text}
        state["transcript"].append({"role": "assistant", "text": text})
        state["debug"] = _debug(state, analysis, degraded, env0)
        return {"type": "question", "text": text, "topics": [topic]}

    # Final answer. A fact we already asked about but is still unclear is treated as the riskier branch.
    assume = env_assumed(analysis, state, unknown)
    env = rules.evaluate(analysis["facts"], view["signals"], audience, assume=assume, benign=analysis["benign"])
    answer = bot.compose_answer(dict(case, language=lang), analysis, degraded, view, state["revealed"], env, [],
                                state["model"], "multi_turn", state["consent_requested"])
    state["transcript"].append({"role": "assistant", "text": answer["advice_text"]})
    state["last"] = {"analysis": analysis, "answer": answer}
    state["debug"] = _debug(state, analysis, degraded, env)
    return {"type": "final", "answer": answer}


def env_assumed(analysis, state, unknown=None):
    """Facts we already asked about that are still unclear: treated as the riskier branch."""
    unknown = unknown if unknown is not None else [s for s in rules.DECISIVE if analysis["facts"].get(s) == "unknown"]
    return [s for s in unknown if rules.SLOT_TOPIC[s] in state["asked"]]


def _debug(state, analysis, degraded, env=None):
    """Internals of the latest turn: what the LLM extracted, which rules fired, consent and question state.

    Not part of the protocol; the API returns it only when the client asks for it (frontend debug view)."""
    out = {"language": state["lang"], "analysis": analysis, "analysis_degraded": degraded, "questions_asked_so_far": list(state["asked"]),
           "signals_released": sorted(state["revealed"]), "signals_refused": sorted(state["refused"]),
           "consent_requested": sorted(state["consent_requested"])}
    if env:
        out["rules"] = {k: env[k] for k in ("reasons", "forced_action", "also_actions", "risk_floor", "escalate", "target", "ask", "lure_floor", "benign_allowed")}
    return out


def handoff_summary(state):
    """What would be passed to a human agent if the user chooses to escalate (shown to the user first)."""
    last = state.get("last")
    if not last:
        return None
    a, ans = last["analysis"], last["answer"]
    return {
        "situation": a["summary"],
        "language": state["lang"],
        "audience": state["case"]["audience"],
        "facts": {k: v for k, v in a["facts"].items() if v not in ("na", "unknown")},
        "risk_level": ans["risk_level"],
        "recommended_action": ans["primary_action"],
        "escalation_target": ans["escalation_target"],
        "signals_shared": ans["signals_used"],
        "conversation": [t for t in state["transcript"] if t["role"] == "user"],
    }
