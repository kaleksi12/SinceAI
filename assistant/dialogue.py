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
import sys
from pathlib import Path

# Allow this file to be loaded by path (the kit's runner does that) as well as imported as part of the package.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from assistant import bot, rules  # noqa: E402

MAX_CONSENT_FIELDS = 3  # never ask for more than this many signals at once

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
                     asked=[], lang=case.get("language"), last=None,
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
    return _advance(state, force_final=(kind == "turn_limit"))


def _advance(state, force_final):
    case = state["case"]
    gated = list(case["consent"]["requires_consent"])
    pre = set(case["consent"]["pre_granted"])

    # Analyse the conversation; if the LLM needs sensitive signals, release pre-allowed ones silently and ask for the rest.
    while True:
        view = bot.build_view(case, state["revealed"])
        left = [p for p in gated if p not in state["revealed"] and p not in state["refused"]]
        analysis, degraded = bot.analyze(view, left, state["model"], state["transcript"])
        wanted = [p for p in analysis["needs_signals"] if p in left][:MAX_CONSENT_FIELDS]
        if not wanted or degraded or force_final:
            break
        auto = [p for p in wanted if p in pre]  # allowed in the user's settings already: no need to ask again
        if auto:
            state["revealed"].update(auto)
            continue
        if state["consent_requested"]:  # one consent request per conversation: never ask again and again
            break
        lang = case.get("language") or analysis["language"] or state["lang"] or "en"
        state["lang"] = lang
        state["consent_requested"] |= set(wanted)
        text = CONSENT_TEXT[lang] % "; ".join(field_label(p, lang) for p in wanted)
        state["transcript"].append({"role": "assistant", "text": text})
        return {"type": "consent_request", "fields": wanted, "text": text}

    lang = case.get("language") or analysis["language"] or state["lang"] or "en"
    state["lang"] = lang
    audience = case["audience"]

    # Decisive facts still unknown (ordered by priority); ask about the first one we have not asked yet.
    unknown = rules.evaluate(analysis["facts"], view["signals"], audience)["ask"]
    pending = [s for s in unknown if rules.SLOT_TOPIC[s] not in state["asked"]]
    if pending and not force_final and len(state["asked"]) < bot.MAX_QUESTIONS:
        topic = rules.SLOT_TOPIC[pending[0]]
        state["asked"].append(topic)
        text = bot.question_text(topic, lang)
        state["transcript"].append({"role": "assistant", "text": text})
        return {"type": "question", "text": text, "topics": [topic]}

    # Final answer. A fact we already asked about but is still unclear is treated as the riskier branch.
    assume = [s for s in unknown if rules.SLOT_TOPIC[s] in state["asked"]]
    env = rules.evaluate(analysis["facts"], view["signals"], audience, assume=assume)
    answer = bot.compose_answer(dict(case, language=lang), analysis, degraded, view, state["revealed"], env, [],
                                state["model"], "multi_turn", state["consent_requested"])
    state["transcript"].append({"role": "assistant", "text": answer["advice_text"]})
    state["last"] = {"analysis": analysis, "answer": answer}
    return {"type": "final", "answer": answer}


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
