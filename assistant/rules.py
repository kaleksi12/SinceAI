"""Safety envelope: generic rules over yes/no/unknown facts that constrain what the LLM may decide.

Slot values: "yes", "no", "unknown" (relevant but not stated) or "na" (not relevant, the default).
Only "unknown" decisive slots lead to questions.
"""

RISK = ["none", "low", "medium", "high", "critical"]
URGENCY = {"none": "none", "low": "routine", "medium": "routine", "high": "today", "critical": "immediate"}

# Priority order for questions; money_transferred is asked under the kit topic "payment_status".
DECISIVE = ["self_initiated", "code_shared", "credentials_entered", "card_details_entered",
            "money_transferred", "app_installed", "remote_access_given"]
SLOT_TOPIC = {s: s for s in DECISIVE}
SLOT_TOPIC["money_transferred"] = "payment_status"

# Actions that always need a human handoff (per dev-set labelling).
ALWAYS_ESCALATE = {"isolate_device_and_scan", "escalate_to_human"}

LURE_FLOOR = {"small_payment_or_card": "medium", "credentials_or_transfer": "high"}


def _max_risk(*levels):
    return max(levels, key=RISK.index)


def _derive_operator_change(signals):
    """True if granted subscription signals show a SIM/eSIM change, subscription order or loss of service."""
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


def evaluate(facts, signals=None, audience="consumer", assume_unknown_yes=False):
    """Return the envelope for one situation.

    assume_unknown_yes=True answers as if the riskier branch were true (single-turn twins, or out of turns)."""
    f = {k: facts.get(k, "na") for k in
         ("self_initiated", "code_shared", "code_for", "credentials_entered", "credentials_kind", "card_details_entered",
          "money_transferred", "app_installed", "remote_access_given", "operator_change", "monitoring_suspected",
          "out_of_scope_request", "requests_sensitive_action", "lure_type")}
    smb = audience == "small_business"
    signal_change, used = _derive_operator_change(signals)
    if signal_change:
        f["operator_change"] = "yes"

    ask = [s for s in DECISIVE if f[s] == "unknown"]
    eff = dict(f)
    if assume_unknown_yes:
        for s in DECISIVE:
            if eff[s] == "unknown":
                eff[s] = "no" if s == "self_initiated" else "yes"

    triggers = []  # (rule, action, risk, escalate, target), in priority order

    def add(rule, action, risk, escalate=False, target=None):
        triggers.append((rule, action, risk, escalate, target))

    if eff["out_of_scope_request"] == "yes":
        add("R7", "decline_out_of_scope", "medium")
    if eff["monitoring_suspected"] == "yes":
        add("R6", "escalate_to_human", "high", True, "human_advisor")
    if eff["operator_change"] == "yes" and eff["self_initiated"] != "yes":
        add("R5", "contact_operator_support", "critical", True, "business_security_support" if smb else "operator_support_agent")
    if eff["code_shared"] == "yes":
        action = "contact_operator_support" if eff["code_for"] == "operator" else "contact_bank_and_block_cards"
        add("R1", action, "critical", smb, "business_security_support" if smb else None)
    if eff["money_transferred"] == "yes":
        add("R2", "contact_bank_and_block_cards", "critical", True, "business_security_support" if smb else "human_advisor")
    elif eff["card_details_entered"] == "yes":
        add("R2", "contact_bank_and_block_cards", "critical")
    if eff["remote_access_given"] == "yes" or eff["app_installed"] == "yes":
        add("R4", "isolate_device_and_scan", "high", True, "business_security_support" if smb else "security_specialist")
    if eff["credentials_entered"] == "yes":
        if eff["credentials_kind"] == "bank_or_id":
            add("R3", "contact_bank_and_block_cards", "critical")
        else:
            add("R3", "change_password_and_enable_mfa", "high")

    env = {"ask": ask, "ask_topics": [SLOT_TOPIC[s] for s in ask], "reasons": [t[0] for t in triggers],
           "signals_used": used, "forced_action": None, "also_actions": [], "risk_floor": "none",
           "escalate": False, "target": None,
           "lure_floor": LURE_FLOOR.get(f["lure_type"], "none"),
           "benign_allowed": not triggers and not ask and f["requests_sensitive_action"] != "yes"}
    if triggers:
        env["forced_action"] = triggers[0][1]
        env["also_actions"] = [a for a in dict.fromkeys(t[1] for t in triggers) if a != triggers[0][1]]
        env["risk_floor"] = _max_risk(*(t[2] for t in triggers))
        esc = [t for t in triggers if t[3]]
        env["escalate"] = bool(esc)
        env["target"] = esc[0][4] if esc else None
    return env


def clamp(proposal, env, audience="consumer"):
    """Apply the envelope to an LLM proposal and return the constrained decision fields."""
    action = proposal.get("primary_action")
    risk = proposal.get("risk_level") if proposal.get("risk_level") in RISK else "medium"
    if env["forced_action"]:
        action = env["forced_action"]
        risk = _max_risk(risk, env["risk_floor"])
        escalate, target = env["escalate"], env["target"]
    else:
        if proposal.get("abstained"):
            action, risk = "escalate_to_human", _max_risk(risk, "high")
        elif action == "no_action_needed" and not env["benign_allowed"]:
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
