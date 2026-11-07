"""The safety envelope: generic rules that limit what the LLM is allowed to decide.

How it is used (see bot.py and dialogue.py):
  1. The LLM reads the user's words and fills in "slots": yes/no/unknown/na facts such as
     "was a code shared?" or "was money sent?".
  2. evaluate() turns those facts into limits: a forced action, a minimum risk level,
     whether a human handoff is needed, and which decisive facts are still unknown (to ask about).
  3. clamp() applies those limits to the LLM's own proposal, so the final answer can never be
     less safe than the rules allow, and a benign case is not alarmed without evidence.

Slot values:
  "yes" / "no"  the user's words or the data state it explicitly
  "unknown"     relevant to this situation but not stated yet (the only value that leads to a question)
  "na"          not relevant (the default)
The action, step and escalation-target names come from the organisers' vocabularies (simset/data/reference).
"""

# Ordered from least to most severe, so max() by index gives the more severe level.
RISK = ["none", "low", "medium", "high", "critical"]
URGENCY = {"none": "none", "low": "routine", "medium": "routine", "high": "today", "critical": "immediate"}

# Facts that can decide between a safe and a dangerous branch, in the order we prefer to ask about them.
DECISIVE = ["self_initiated", "code_shared", "credentials_entered", "card_details_entered",
            "money_transferred", "app_installed", "remote_access_given"]
# Slot name -> the kit's question topic (money_transferred is scored under "payment_status").
SLOT_TOPIC = {s: s for s in DECISIVE}
SLOT_TOPIC["money_transferred"] = "payment_status"

# In the dev data these actions always carry a human handoff.
ALWAYS_ESCALATE = {"isolate_device_and_scan", "escalate_to_human"}

# When nothing has been done yet, how risky is the lure itself (the kit's labelling rule).
LURE_FLOOR = {"small_payment_or_card": "medium", "credentials_or_transfer": "high"}


def _max_risk(*levels):
    return max(levels, key=RISK.index)


def _derive_operator_change(signals):
    """True if granted subscription signals show a SIM/eSIM change, a subscription order or lost service.

    Returns (found, list of signal paths we looked at). Hidden signals are the string
    "available_with_consent", not a dict/list, so they are ignored here automatically."""
    used, hit = [], False
    sub = (signals or {}).get("subscription")
    if not isinstance(sub, dict):
        return False, used
    events = sub.get("recent_events")
    if isinstance(events, list):
        used.append("subscription.recent_events")
        hit |= any(e.get("type") in ("esim_activation", "esim_transfer_code_sent", "new_subscription_order") for e in events if isinstance(e, dict))
    net = sub.get("network_status")
    if isinstance(net, dict):
        used.append("subscription.network_status")
        hit |= net.get("service") == "no_service"
    return hit, used


def evaluate(facts, signals=None, audience="consumer", assume=(), benign=False):
    """Return the envelope (the limits) for one situation.

    assume: slot names to treat as the RISKIER answer while they are still "unknown". Used for the
    slots we are asking about right now (single-turn: advise for the worse branch and ask; multi-turn:
    after the user was asked but stayed vague). Unknown slots that are not assumed trigger nothing.
    benign: the LLM judged the case harmless; together with self_initiated=yes it stops R3 (a normal login
    the user is doing themselves must not be treated as typing credentials into a scam)."""
    # Missing slots default to "na" (not relevant).
    f = {k: facts.get(k, "na") for k in
         ("self_initiated", "code_shared", "code_for", "credentials_entered", "credentials_kind", "card_details_entered",
          "money_transferred", "app_installed", "remote_access_given", "login_prompts_unrequested", "operator_change",
          "monitoring_suspected", "out_of_scope_request", "requests_sensitive_action", "lure_type")}
    smb = audience == "small_business"
    # Evidence in granted signals can confirm a SIM/eSIM event even if the user did not mention it.
    signal_change, used = _derive_operator_change(signals)
    if signal_change:
        f["operator_change"] = "yes"

    # Decisive facts we still do not know, in priority order: these become questions.
    ask = [s for s in DECISIVE if f[s] == "unknown"]
    # When nothing has been done yet, the lure tells which question matters most (card lure -> card details first).
    first = {"small_payment_or_card": ("card_details_entered", "money_transferred"), "credentials_or_transfer": ("credentials_entered",)}.get(f["lure_type"], ())
    ask.sort(key=lambda s: s not in first)  # stable sort: only moves the lure-relevant slots to the front
    # "eff" is what the triggers below look at: assumed slots take their riskier value.
    eff = dict(f)
    for s in assume:
        if eff.get(s) == "unknown":
            eff[s] = "no" if s == "self_initiated" else "yes"

    triggers = []  # (rule id, forced action, risk floor, escalate?, escalation target), highest priority first

    def add(rule, action, risk, escalate=False, target=None):
        triggers.append((rule, action, risk, escalate, target))

    # R7: asked to trace/expose/retaliate against someone: out of scope, decline and point to the police.
    if eff["out_of_scope_request"] == "yes":
        add("R7", "decline_out_of_scope", "medium")
    # R6: someone close may be monitoring the phone: needs a human and safety planning, never "remove it now".
    if eff["monitoring_suspected"] == "yes":
        add("R6", "escalate_to_human", "high", True, "human_advisor")
    # R5: SIM/eSIM change or lost service the user did not start: likely takeover, operator must lock the number.
    if eff["operator_change"] == "yes" and eff["self_initiated"] != "yes":
        add("R5", "contact_operator_support", "critical", True, "business_security_support" if smb else "operator_support_agent")
    # R1: a code or PIN was shared: critical. Operator codes go to the operator, others to the bank.
    if eff["code_shared"] == "yes":
        action = "contact_operator_support" if eff["code_for"] == "operator" else "contact_bank_and_block_cards"
        add("R1", action, "critical", smb, "business_security_support" if smb else None)
    # R2: money already sent (escalate) or card details entered (bank + block cards).
    if eff["money_transferred"] == "yes":
        add("R2", "contact_bank_and_block_cards", "critical", True, "business_security_support" if smb else "human_advisor")
    elif eff["card_details_entered"] == "yes":
        add("R2", "contact_bank_and_block_cards", "critical")
    # R4: remote access given or an app installed: the device may be controlled, isolate it.
    if eff["remote_access_given"] == "yes" or eff["app_installed"] == "yes":
        add("R4", "isolate_device_and_scan", "high", True, "business_security_support" if smb else "security_specialist")
    # R3: credentials typed into something suspicious: bank/ID logins go to the bank, others change the password.
    # Not applied when the LLM judged the case benign and the user started the login themselves.
    if eff["credentials_entered"] == "yes" and not (benign and eff["self_initiated"] == "yes"):
        if eff["credentials_kind"] == "bank_or_id":
            add("R3", "contact_bank_and_block_cards", "critical")
        else:
            add("R3", "change_password_and_enable_mfa", "high")
    # R3b: login approval prompts the user did not start: someone probably has the password.
    if eff["login_prompts_unrequested"] == "yes":
        add("R3", "change_password_and_enable_mfa", "high")

    env = {"ask": ask, "ask_topics": [SLOT_TOPIC[s] for s in ask], "reasons": [t[0] for t in triggers],
           "signals_used": used, "forced_action": None, "also_actions": [], "risk_floor": "none",
           "escalate": False, "target": None,
           # R8: the lure's own risk level, applied by clamp() unless the answer is "no action needed".
           "lure_floor": LURE_FLOOR.get(f["lure_type"], "none"),
           # R9 (benign guard): "no action needed" is only allowed with no triggered rule, no open
           # decisive question, and a message that does not ask for money, logins, codes or installs.
           "benign_allowed": not triggers and not ask and f["requests_sensitive_action"] != "yes"}
    if triggers:
        # The highest-priority trigger decides the action; the others are kept as extra steps to mention.
        env["forced_action"] = triggers[0][1]
        env["also_actions"] = [a for a in dict.fromkeys(t[1] for t in triggers) if a != triggers[0][1]]
        env["risk_floor"] = _max_risk(*(t[2] for t in triggers))
        esc = [t for t in triggers if t[3]]
        env["escalate"] = bool(esc)
        env["target"] = esc[0][4] if esc else None
    return env


def clamp(proposal, env, audience="consumer"):
    """Apply the envelope to the LLM's proposal (primary_action, risk_level, abstained).

    Returns the final primary_action, risk_level, urgency, escalation_required and escalation_target."""
    action = proposal.get("primary_action")
    risk = proposal.get("risk_level") if proposal.get("risk_level") in RISK else "medium"
    if env["forced_action"]:
        # A rule fired: its action wins, risk can only go up, escalation follows the rules.
        action = env["forced_action"]
        risk = _max_risk(risk, env["risk_floor"])
        escalate, target = env["escalate"], env["target"]
    else:
        if proposal.get("abstained"):
            # The LLM could not judge safely: hand over to a human.
            action, risk = "escalate_to_human", _max_risk(risk, "high")
        elif action == "no_action_needed" and not env["benign_allowed"]:
            # Not clearly benign: never reassure, at least verify through an official channel.
            action, risk = "verify_via_official_channel", _max_risk(risk, "medium")
        if action == "no_action_needed":
            risk = risk if risk in ("none", "low") else "low"
        elif env["lure_floor"] != "none":
            risk = _max_risk(risk, env["lure_floor"])
        escalate = action in ALWAYS_ESCALATE
        target = None
        if escalate:
            target = "business_security_support" if audience == "small_business" else (
                "security_specialist" if action == "isolate_device_and_scan" else "human_advisor")
    return {"primary_action": action, "risk_level": risk, "urgency": URGENCY[risk],
            "escalation_required": escalate, "escalation_target": target if escalate else None}
