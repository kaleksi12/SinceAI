# -*- coding: utf-8 -*-
"""Smallest useful multi-turn bot, for copying. Replace `think()` with your
own logic or a model call.

    python3 sim/run_conversation.py --cases data/dev/cases.jsonl \
        --bot-py examples/python_bot.py:step --out mt.jsonl --limit 20 --show

step(event, state) receives one harness event and returns one reply:
  {"type": "question", "text": "...", "topics": ["card_details_entered"]}   (topics optional)
  {"type": "consent_request", "fields": ["device.recent_app_installs"], "text": "..."}
  {"type": "final", "answer": {...submission fields...}}
"""


def think(case, facts):
    """Return (question_topic_or_None, answer_dict). Toy logic only."""
    lang = case.get("language", "fi")
    if case["journey"] == "clicked_link" and "card_details_entered" not in facts:
        return "card_details_entered", None
    entered = any(w in facts.get("card_details_entered", "").lower() for w in ("syötin", "typed", "yes", "joo", "skrev"))
    if entered:
        action, risk = "contact_bank_and_block_cards", "critical"
        text = {"fi": "Sulje kortti heti pankin sovelluksessa tai soita pankin sulkupalveluun.",
                "en": "Block the card now in your bank's app or call the bank's card-blocking line."}.get(lang)
    else:
        action, risk = "verify_via_official_channel", "medium"
        text = {"fi": "Älä avaa linkkiä. Tarkista asia palvelun omasta sovelluksesta.",
                "en": "Do not open the link. Check the matter in the service's own app."}.get(lang)
    return None, {"risk_level": risk, "primary_action": action, "advice_text": text or "",
                  "escalation_required": False, "signals_used": ["artifact"], "consent_requested_for": [], "confidence": 0.5}


QUESTION_TEXT = {"card_details_entered": {"fi": "Syötitkö sivulle korttitietoja?", "en": "Did you enter any card details on the page?",
                                          "sv": "Skrev du in kortuppgifter på sidan?"}}


def step(event, state):
    if event["type"] == "start":
        state.clear()
        state.update(case=event["case"], facts={}, last=None)
    elif event["type"] == "user_reply" and state.get("last"):
        state["facts"][state["last"]] = event["text"]
    topic, answer = think(state["case"], state["facts"])
    if topic and event["type"] != "turn_limit":
        state["last"] = topic
        lang = state["case"].get("language", "fi")
        return {"type": "question", "text": QUESTION_TEXT[topic].get(lang, QUESTION_TEXT[topic]["en"]), "topics": [topic]}
    if answer is None:
        answer = {"risk_level": "medium", "primary_action": "escalate_to_human", "advice_text": "", "escalation_required": True, "abstained": True}
    answer["question_topics"] = list(state["facts"])
    return {"type": "final", "answer": answer}
