import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from assistant.rules import clamp, evaluate  # noqa: E402


class RulesTest(unittest.TestCase):
    def test_code_shared_forces_bank_critical(self):
        env = evaluate({"code_shared": "yes"})
        self.assertEqual(env["forced_action"], "contact_bank_and_block_cards")
        self.assertEqual(env["risk_floor"], "critical")

    def test_operator_code_goes_to_operator(self):
        env = evaluate({"code_shared": "yes", "code_for": "operator"})
        self.assertEqual(env["forced_action"], "contact_operator_support")

    def test_unknown_asks_and_is_not_forced_in_multi_turn(self):
        env = evaluate({"card_details_entered": "unknown"})
        self.assertIsNone(env["forced_action"])
        self.assertEqual(env["ask"], ["card_details_entered"])
        self.assertFalse(env["benign_allowed"])

    def test_unknown_assumed_yes_in_single_turn(self):
        env = evaluate({"money_transferred": "unknown"}, assume_unknown_yes=True)
        self.assertEqual(env["forced_action"], "contact_bank_and_block_cards")
        self.assertEqual(env["ask_topics"], ["payment_status"])
        self.assertEqual(env["target"], "human_advisor")

    def test_business_money_escalates_to_business_support(self):
        env = evaluate({"money_transferred": "yes"}, audience="small_business")
        self.assertEqual(env["target"], "business_security_support")

    def test_self_initiated_sim_change_is_not_forced(self):
        env = evaluate({"operator_change": "yes", "self_initiated": "yes"})
        self.assertIsNone(env["forced_action"])
        self.assertTrue(env["benign_allowed"])

    def test_sim_event_from_signals(self):
        sig = {"subscription": {"recent_events": [{"type": "esim_activation"}], "network_status": {"service": "no_service"}}}
        env = evaluate({"self_initiated": "unknown"}, sig, assume_unknown_yes=True)
        self.assertEqual(env["forced_action"], "contact_operator_support")
        self.assertEqual(env["signals_used"], ["subscription.recent_events", "subscription.network_status"])

    def test_ungranted_signals_are_ignored(self):
        sig = {"subscription": {"recent_events": "available_with_consent", "network_status": "available_with_consent"}}
        env = evaluate({}, sig)
        self.assertIsNone(env["forced_action"])
        self.assertEqual(env["signals_used"], [])

    def test_monitoring_outranks_money(self):
        env = evaluate({"monitoring_suspected": "yes", "money_transferred": "yes"})
        self.assertEqual(env["forced_action"], "escalate_to_human")
        self.assertEqual(env["also_actions"], ["contact_bank_and_block_cards"])

    def test_out_of_scope_declines_without_escalation(self):
        d = clamp({"primary_action": "verify_via_official_channel", "risk_level": "high"}, evaluate({"out_of_scope_request": "yes"}))
        self.assertEqual(d["primary_action"], "decline_out_of_scope")
        self.assertFalse(d["escalation_required"])

    def test_no_action_downgraded_when_not_benign(self):
        env = evaluate({"requests_sensitive_action": "yes"})
        d = clamp({"primary_action": "no_action_needed", "risk_level": "none"}, env)
        self.assertEqual(d["primary_action"], "verify_via_official_channel")
        self.assertEqual(d["risk_level"], "medium")

    def test_benign_no_action_stays_low_and_unescalated(self):
        d = clamp({"primary_action": "no_action_needed", "risk_level": "high", "abstained": False}, evaluate({}))
        self.assertEqual((d["primary_action"], d["risk_level"], d["escalation_required"]), ("no_action_needed", "low", False))

    def test_lure_floor_raises_risk(self):
        env = evaluate({"lure_type": "credentials_or_transfer"})
        d = clamp({"primary_action": "do_not_interact_and_delete", "risk_level": "low"}, env)
        self.assertEqual(d["risk_level"], "high")

    def test_abstain_escalates_to_human(self):
        d = clamp({"primary_action": "verify_via_official_channel", "risk_level": "low", "abstained": True}, evaluate({}))
        self.assertEqual((d["primary_action"], d["escalation_target"]), ("escalate_to_human", "human_advisor"))

    def test_isolate_device_always_escalates(self):
        d = clamp({"primary_action": "isolate_device_and_scan", "risk_level": "high"}, evaluate({}), audience="small_business")
        self.assertEqual(d["escalation_target"], "business_security_support")


if __name__ == "__main__":
    unittest.main()
