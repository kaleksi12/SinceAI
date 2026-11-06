#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reference baselines. They read only what an assistant may see (no ground
truth) and exist to show what the evaluator rewards and punishes.

    python3 baselines/rules_baseline.py --cases data/dev/cases.jsonl --out b_rules.jsonl
    python3 baselines/rules_baseline.py --cases data/test/inputs.jsonl --out test_predictions.jsonl
    python3 baselines/rules_baseline.py --cases data/dev/cases.jsonl --strategy always_no_action --out b0.jsonl
    python3 sim/run_conversation.py --cases data/dev/cases.jsonl --bot-py baselines/rules_baseline.py:step --out b_rules_mt.jsonl

The rules are a keyword-and-signal decision list written in an afternoon. A
good team should beat them clearly, especially on twins, benign controls,
unseen families and clarity.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)

GATED = "available_with_consent"

TEMPL = {
    "no_action_needed": {
        "fi": "Tämä vaikuttaa aidolta eikä vaadi toimenpiteitä. Siinä ei pyydetä tunnuksia, koodeja tai maksua. Jos haluat varmistaa, tarkista asia palvelun omasta sovelluksesta.",
        "en": "This looks genuine and no action is needed. It does not ask for credentials, codes or payment. If you want to be sure, check it in the service's own app.",
        "sv": "Det här verkar äkta och du behöver inte göra något. Det ber inte om koder eller betalning. Kontrollera gärna i tjänstens egen app.",
    },
    "do_not_interact_and_delete": {
        "fi": "Älä avaa linkkiä, älä vastaa äläkä maksa mitään. Viesti on todennäköisesti huijaus. Poista viesti tai ilmoita se roskapostiksi.",
        "en": "Do not open the link, do not reply and do not pay anything. The message is most likely a scam. Delete it or report it as spam.",
        "sv": "Öppna inte länken, svara inte och betala inget. Meddelandet är troligen bedrägeri. Radera det eller rapportera det som skräppost.",
    },
    "verify_via_official_channel": {
        "fi": "Älä avaa linkkiä äläkä käytä viestin yhteystietoja. Tarkista asia organisaation omasta sovelluksesta tai numerosta, jonka tiedät jo. Älä maksa ennen kuin asia on varmistettu.",
        "en": "Do not open the link or use the contact details in the message. Check the matter in the organisation's own app or on a number you already know. Do not pay before it is verified.",
        "sv": "Öppna inte länken och använd inte kontaktuppgifterna i meddelandet. Kontrollera i organisationens egen app eller på ett nummer du redan känner. Betala inte innan det är kontrollerat.",
    },
    "contact_bank_and_block_cards": {
        "fi": "Ota heti yhteyttä pankkiisi kortissa olevasta numerosta ja sulje kortti. Älä anna koodeja kenellekään. Tarkista tilitapahtumat ja tee tarvittaessa rikosilmoitus.",
        "en": "Contact your bank now on the number on your card and block the card. Do not share codes with anyone. Check your transactions and file a police report if needed.",
        "sv": "Kontakta din bank nu på numret på kortet och spärra kortet. Dela inga koder. Kontrollera transaktionerna och gör en polisanmälan vid behov.",
    },
    "change_password_and_enable_mfa": {
        "fi": "Vaihda salasana heti luotettavalla laitteella ja kirjaudu ulos kaikista istunnoista. Vaihda sama salasana myös muissa palveluissa. Ota kaksivaiheinen tunnistautuminen käyttöön.",
        "en": "Change the password now from a trusted device and sign out of all sessions. Change the same password on other services too. Turn on two-factor authentication.",
        "sv": "Byt lösenordet nu på en betrodd enhet och logga ut från alla sessioner. Byt samma lösenord i andra tjänster. Aktivera tvåstegsverifiering.",
    },
    "contact_operator_support": {
        "fi": "Ota heti yhteyttä operaattorin asiakaspalveluun ja pyydä lukitsemaan liittymä ja SIM-muutokset. Älä kerro koodeja kenellekään. Ota sen jälkeen yhteyttä pankkiisi.",
        "en": "Contact the operator's customer service now and ask them to lock the subscription and SIM changes. Do not share codes with anyone. Then contact your bank.",
        "sv": "Kontakta operatörens kundtjänst nu och be dem spärra abonnemanget och SIM-ändringar. Dela inga koder. Kontakta sedan din bank.",
    },
    "isolate_device_and_scan": {
        "fi": "Katkaise laitteen verkkoyhteys heti, esimerkiksi lentotilalla, äläkä käytä sillä verkkopankkia. Poista epäilyttävä sovellus tai ohjelma ja tarkistuta laite. Vaihda tärkeät salasanat toisella laitteella.",
        "en": "Disconnect the device from the network now, for example with flight mode, and do not use online banking on it. Remove the suspicious app or program and get the device checked. Change important passwords from another device.",
        "sv": "Koppla bort enheten från nätet nu, till exempel med flygläge, och använd inte internetbanken på den. Ta bort den misstänkta appen och låt kontrollera enheten. Byt viktiga lösenord på en annan enhet.",
    },
    "escalate_to_human": {
        "fi": "Tämä tilanne kannattaa käydä läpi ihmisen kanssa. Ohjaan sinut asiantuntijalle ja välitän tiedot, ettei sinun tarvitse aloittaa alusta.",
        "en": "This situation is best handled with a person. I am connecting you to a specialist and passing on what we know so you don't need to start again.",
        "sv": "Den här situationen hanteras bäst av en person. Jag kopplar dig till en expert.",
    },
    "decline_out_of_scope": {
        "fi": "En voi auttaa tässä. Voit tehdä rikosilmoituksen poliisille, ja autan mielelläni oman turvallisuutesi kanssa.",
        "en": "I can't help with that. You can file a report with the police, and I'm happy to help with your own safety.",
        "sv": "Jag kan inte hjälpa till med det. Du kan göra en polisanmälan.",
    },
}
CITE = {"no_action_needed": ["guidance_proportionate_advice"], "do_not_interact_and_delete": ["guidance_smishing_basics"],
        "verify_via_official_channel": ["guidance_sender_id_spoofing"], "contact_bank_and_block_cards": ["guidance_card_details_entered"],
        "change_password_and_enable_mfa": ["guidance_credential_compromise"], "contact_operator_support": ["guidance_sim_swap"],
        "isolate_device_and_scan": ["guidance_device_compromise"], "escalate_to_human": ["guidance_handing_off"], "decline_out_of_scope": ["guidance_out_of_scope"]}
RISK = {"no_action_needed": "none", "do_not_interact_and_delete": "medium", "verify_via_official_channel": "high", "contact_bank_and_block_cards": "critical",
        "change_password_and_enable_mfa": "high", "contact_operator_support": "critical", "isolate_device_and_scan": "critical", "escalate_to_human": "high",
        "decline_out_of_scope": "medium"}
ESC = {"contact_operator_support": "operator_support_agent", "isolate_device_and_scan": "security_specialist", "escalate_to_human": "human_advisor"}

QUESTIONS = {
    "card_details_entered": {"fi": "Syötitkö sivulle korttitietoja tai maksoitko jotain?", "en": "Did you enter card details or pay anything on the page?", "sv": "Skrev du in kortuppgifter eller betalade du något?"},
    "code_shared": {"fi": "Kerroitko soittajalle jonkin koodin?", "en": "Did you give the caller any code?", "sv": "Gav du uppringaren någon kod?"},
    "self_initiated": {"fi": "Tilasitko tai teitkö tämän muutoksen itse?", "en": "Did you order or make this change yourself?", "sv": "Beställde eller gjorde du ändringen själv?"},
    "payment_status": {"fi": "Onko maksu jo maksettu?", "en": "Has the payment already been made?", "sv": "Är betalningen redan gjord?"},
    "credentials_entered": {"fi": "Kirjauduitko verkkopankkiin tai syötitkö salasanan?", "en": "Did you log in to your bank or type a password?", "sv": "Loggade du in på banken eller skrev du ett lösenord?"},
    "app_installed": {"fi": "Avasitko asiakirjan ja sallitko sisällön tai asensitko jotain?", "en": "Did you open the document and enable content or install anything?", "sv": "Öppnade du dokumentet eller installerade något?"},
    "link_details": {"fi": "Voitko kertoa linkin osoitteen?", "en": "Can you tell me the link address?", "sv": "Kan du berätta länkens adress?"},
}


def low(s):
    return (s or "").lower()


def has(t, *words):
    return any(re.search(w, t) for w in words)


def decide(case, facts=None):
    """facts: {topic: answer text} learned in conversation (multi-turn)."""
    facts = facts or {}
    sig = case["signals"]
    op = low(case["opening_message"])
    body = low((sig.get("artifact") or {}).get("body"))
    lc = sig.get("link_check") if isinstance(sig.get("link_check"), dict) else None
    cw = sig.get("call_warning") if isinstance(sig.get("call_warning"), dict) else None
    sub = sig.get("subscription") or {}
    events = sub.get("recent_events") if isinstance(sub.get("recent_events"), list) else []
    net = sub.get("network_status") if isinstance(sub.get("network_status"), dict) else {}
    ans = low(" ".join(facts.values()))
    used = ["artifact"] + (["link_check"] if lc else []) + (["call_warning"] if cw else [])
    ask = []
    yes_input = has(op + " " + ans, r"syötin|kirjoitin|annoin|luin|entered|typed|gave|read (him|her|them|out)|maksoin jo|already paid|i paid|kirjauduin|logged in|painoin|clicked it|asensin|installed")
    neg_input = has(ans, r"en syöttänyt|en antanut|en lukenut|en kirjautunut|didn't (type|give|read|log)|en ole (vielä )?maksanut|haven't paid|did not|en avannut asiakirjaa|i only opened")
    if isinstance(sub.get("recent_events"), list):
        used.append("subscription.recent_events")
    if net:
        used.append("subscription.network_status")

    if has(op, r"kuka omistaa|omistaa numeron|who owns|osoite, operaattorilla|find out who|julkaista"):
        return "decline_out_of_scope", used, ask
    if has(op, r"\bex\b|entinen kumppani|seurantasovellu|tracking app|valvo"):
        return "escalate_to_human", used, ask
    if has(op + body, r"salattu|encrypted|bitcoin|lunnai|krypterade"):
        return "isolate_device_and_scan", used, ask
    if any(e.get("type") == "esim_activation" for e in events) or net.get("service") == "no_service":
        if has(ans, r"itse|myself|mieheni|partner|minä tein|i did"):
            return "no_action_needed", used, ask
        if not facts:
            ask.append("self_initiated")
        return "contact_operator_support", used, ask
    if any(e.get("type") == "new_subscription_order" and e.get("delivery") != "office_address" for e in events):
        if has(ans, r"tilanneensa|ordered them|tilasin"):
            return "contact_operator_support", used, ask
        if not facts:
            ask.append("self_initiated")
        return "contact_operator_support", used, ask
    if has(op, r"etätuki|ohjasi|remote|controlled my"):
        if not facts:
            ask.append("credentials_entered")
        if has(ans, r"kirjauduin|logged in|i did"):
            return "contact_bank_and_block_cards", used, ask
        return "isolate_device_and_scan", used, ask
    if has(op, r"asensin|installed|latasin"):
        return "isolate_device_and_scan", used, ask
    if has(op, r"hyväksyntäpyyn|approval request|godkänna"):
        return "change_password_and_enable_mfa", used, ask
    if case["journey"] == "smb_incident":
        if has(op + body, r"toimitusjohtaja|ceo|pomo|vd\b"):
            if not facts:
                ask.append("payment_status")
            if has(ans, r"maksoin|already paid|betalade"):
                return "contact_bank_and_block_cards", used, ask
            return "verify_via_official_channel", used, ask
        if has(op + body, r"tilinumero|bank account|kontonummer|uudelle tilille"):
            return "verify_via_official_channel", used, ask
        if has(op, r"zip|liite|attachment"):
            if not facts:
                ask.append("app_installed")
            if has(ans, r"salli|enable|painoin"):
                return "isolate_device_and_scan", used, ask
            return "do_not_interact_and_delete", used, ask
        if has(op, r"salasan|password|kirjautui|signed in|entinen työntekijä|former employee|edelleenlähety|forwarding"):
            return "change_password_and_enable_mfa", used, ask
    if case["journey"] == "suspicious_call" or (cw is not None):
        if has(op + body, r"koodi|code|kod"):
            if not facts:
                ask.append("code_shared")
            gave = has(ans, r"luin|read him|läste") and not neg_input
            if has(op + body, r"operaattori|operator|sim"):
                return ("contact_operator_support" if gave else "verify_via_official_channel"), used, ask
            return ("contact_bank_and_block_cards" if gave else "verify_via_official_channel"), used, ask
        if has(op + body, r"turvatili|safe account|siirsin|moved some"):
            return "contact_bank_and_block_cards", used, ask
        if cw and cw.get("warning") in ("possible_spam",) and not has(op + body, r"koodi|maks|pay|code"):
            return "no_action_needed", used, ask
        return "do_not_interact_and_delete", used, ask
    if case["journey"] == "clicked_link":
        if has(op, r"tunnukse|credentials|pankkitunnu|koder"):
            return "contact_bank_and_block_cards", used, ask
        if has(op, r"salasan|password|lösenord"):
            return "change_password_and_enable_mfa", used, ask
        if lc and lc.get("verdict") == "clean":
            return "no_action_needed", used, ask
        if not facts and not yes_input:
            ask.append("card_details_entered")
        if (yes_input and not neg_input) or has(ans, r"syötin|typed|skrev"):
            return "contact_bank_and_block_cards", used, ask
        return "do_not_interact_and_delete", used, ask
    if case["journey"] == "breach_notice":
        if has(body, r"vain|only|ei vuotanut|no passwords|inga lösenord") and not has(body, r"salatut salasanat|hashed passwords"):
            return "no_action_needed", used, ask
        if has(body + op, r"salasan|password|lösenord|kirjauduttu|signed in"):
            return "change_password_and_enable_mfa", used, ask
        return "verify_via_official_channel", used, ask
    # suspicious message
    if lc is None and (sig.get("signal_availability") or case.get("signal_availability", {})).get("link_check") == "not_provided":
        ask.append("link_details")
    if lc and lc.get("verdict") in ("malicious", "suspicious"):
        if has(body, r"pankki|bank|tunnistau|kirjaudu|log in"):
            return "verify_via_official_channel", used, ask
        return "do_not_interact_and_delete", used, ask
    if not (sig.get("artifact") or {}).get("links") and not has(body, r"maksa|pay|betala|rahaa|money"):
        return "no_action_needed", used, ask
    return "verify_via_official_channel", used, ask


def answer_for(case, action, used, ask, mode="single_turn"):
    lang = case.get("language", "fi")
    sensitive = set(case.get("consent", {}).get("requires_consent", []))
    pre = set(case.get("consent", {}).get("pre_granted", []))
    sens_used = [u for u in used if u in sensitive]
    adv = TEMPL[action].get(lang) or TEMPL[action]["en"]
    out = {
        "case_id": case["case_id"], "mode": mode, "risk_level": RISK[action], "primary_action": action, "advice_text": adv, "steps": [],
        "questions_asked": [QUESTIONS[t][lang] if lang in QUESTIONS[t] else QUESTIONS[t]["en"] for t in ask], "question_topics": list(ask),
        "escalation_required": action in ESC, "escalation_target": ESC.get(action), "citations": CITE[action],
        "signals_used": used, "consent_requested_for": [u for u in sens_used if u not in pre],
        "confidence": 0.6, "abstained": False,
    }
    return out


def strategy_answer(case, strategy):
    if strategy == "always_no_action":
        return answer_for(case, "no_action_needed", ["artifact"], [])
    if strategy == "always_escalate":
        a = answer_for(case, "escalate_to_human", ["artifact"], [])
        a["risk_level"] = "critical"
        return a
    action, used, ask = decide(case)
    return answer_for(case, action, used, ask)


# --- multi-turn: step(event, state) for sim/run_conversation.py ----------------
def step(event, state):
    t = event["type"]
    if t == "start":
        state.clear()
        state["case"] = event["case"]
        state["facts"] = {}
        state["asked"] = []
    elif t == "user_reply":
        state["facts"][state["asked"][-1]] = event.get("text", "")
    elif t == "consent_reply":
        for path, val in (event.get("signals") or {}).items():
            cur = state["case"]["signals"]
            parts = path.split(".")
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = val
        state["consented"] = True
    case = state["case"]
    sub = case["signals"].get("subscription", {})
    gated = [k for k in ("recent_events", "network_status") if sub.get(k) == GATED]
    if gated and not state.get("consented") and t != "turn_limit":
        lang = case.get("language", "fi")
        txt = {"fi": "Saanko katsoa liittymäsi viimeaikaiset tapahtumat ja yhteyden tilan?", "en": "May I look at recent events on your subscription and its network status?",
               "sv": "Får jag titta på senaste händelser för ditt abonnemang?"}.get(lang)
        state["consented"] = True
        return {"type": "consent_request", "fields": ["subscription." + g for g in gated], "text": txt}
    action, used, ask = decide(case, state["facts"])
    pending = [a for a in ask if a not in state["asked"]]
    if pending and t != "turn_limit" and len(state["asked"]) < 2:
        topic = pending[0]
        state["asked"].append(topic)
        lang = case.get("language", "fi")
        return {"type": "question", "text": QUESTIONS[topic].get(lang, QUESTIONS[topic]["en"]), "topics": [topic]}
    ans = answer_for(case, action, used, [], mode="multi_turn")
    ans["question_topics"] = list(state["asked"])
    return {"type": "final", "answer": ans}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--strategy", default="rules", choices=["rules", "always_no_action", "always_escalate"])
    a = ap.parse_args()
    n = 0
    with open(a.cases, encoding="utf-8") as f, open(a.out, "w", encoding="utf-8") as o:
        for line in f:
            if not line.strip():
                continue
            c = json.loads(line)
            c = {k: v for k, v in c.items() if k not in ("ground_truth", "simulation")}  # never peek
            o.write(json.dumps(strategy_answer(c, a.strategy), ensure_ascii=False) + "\n")
            n += 1
    print("wrote %d predictions (%s) to %s" % (n, a.strategy, a.out))


if __name__ == "__main__":
    main()
