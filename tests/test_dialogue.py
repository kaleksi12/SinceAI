"""Tests for the live-chat engine and the HTTP API. The LLM calls are replaced by canned results."""
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402

from assistant import api, bot, dialogue  # noqa: E402

GATED = "available_with_consent"


def analysis(facts=None, needs=()):
    """A canned analysis result (what bot.analyze returns): (analysis dict, degraded flag)."""
    raw = {"summary": "test", "language": "en", "facts": facts or {}, "proposed_action": "verify_via_official_channel",
           "risk_level": "medium", "needs_signals": list(needs)}
    return bot._normalise(raw), False


def make_case(gated=(), pre=()):
    return {"case_id": "T-1", "audience": "consumer", "language": "en", "opening_message": "hello", "entry_point": "chat",
            "signals": {"subscription": {"recent_events": GATED}, "operator_account": {"recent_logins": GATED}},
            "consent": {"requires_consent": list(gated), "pre_granted": list(pre)}}


def fake_compose(case, analysis_, degraded, view, revealed, env, topics, model, mode, consent_requested):
    """Stands in for the LLM writer: reports which rules fired so tests can check the decision."""
    return {"advice_text": "final", "reasons": env["reasons"], "consent_requested_for": sorted(consent_requested)}


class DialogueTest(unittest.TestCase):
    def run_events(self, case, analyses, events):
        """Feed events to dialogue.step with canned analyses; return the list of replies."""
        queue = list(analyses)
        state, replies = {}, []
        with mock.patch.object(bot, "analyze", lambda *a, **k: queue.pop(0)), mock.patch.object(bot, "compose_answer", fake_compose):
            for ev in [{"type": "start", "case": case}] + events:
                replies.append(dialogue.step(ev, state))
        return replies

    def test_asks_one_question_then_uses_the_answer(self):
        replies = self.run_events(make_case(), [analysis({"code_shared": "unknown"}), analysis({"code_shared": "yes"})],
                                  [{"type": "user_reply", "text": "yes, I read it out"}])
        self.assertEqual((replies[0]["type"], replies[0]["topics"]), ("question", ["code_shared"]))
        self.assertEqual(replies[1]["type"], "final")
        self.assertEqual(replies[1]["answer"]["reasons"], ["R1"])

    def test_vague_answer_is_treated_as_the_riskier_branch(self):
        replies = self.run_events(make_case(), [analysis({"code_shared": "unknown"}), analysis({"code_shared": "unknown"})],
                                  [{"type": "user_reply", "text": "not sure"}])
        self.assertEqual(replies[1]["type"], "final")
        self.assertEqual(replies[1]["answer"]["reasons"], ["R1"])

    def test_never_asks_the_same_topic_twice(self):
        unknown = analysis({"code_shared": "unknown"})
        replies = self.run_events(make_case(), [unknown, unknown, unknown],
                                  [{"type": "user_reply", "text": "?"}, {"type": "user_reply", "text": "?"}])
        self.assertEqual([r["type"] for r in replies], ["question", "final", "final"])

    def test_consent_asked_once_and_pre_granted_signals_are_released_silently(self):
        case = make_case(["subscription.recent_events", "operator_account.recent_logins"], ["operator_account.recent_logins"])
        both = ["subscription.recent_events", "operator_account.recent_logins"]
        replies = self.run_events(case, [analysis(needs=both), analysis(needs=["subscription.recent_events"]), analysis()],
                                  [{"type": "consent_reply", "granted": [], "refused": ["subscription.recent_events"], "signals": {}}])
        self.assertEqual(replies[0]["type"], "consent_request")
        self.assertEqual(replies[0]["fields"], ["subscription.recent_events"])  # the pre-granted one is not asked about
        self.assertEqual(replies[1]["type"], "final")

    def test_turn_limit_forces_a_final_answer(self):
        unknown = analysis({"code_shared": "unknown"})
        replies = self.run_events(make_case(), [unknown, unknown], [{"type": "turn_limit"}])
        self.assertEqual([r["type"] for r in replies], ["question", "final"])


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        api._sessions.clear()

    def test_scenarios_list_free_text_and_five_journeys_without_ground_truth(self):
        data = self.client.get("/api/scenarios").json()
        self.assertEqual(len(data), 7)
        self.assertNotIn("ground_truth", str(data))

    def test_empty_first_message_is_rejected(self):
        self.assertEqual(self.client.post("/api/chat", json={"message": "  "}).status_code, 400)

    def test_unknown_session_is_404(self):
        self.assertEqual(self.client.post("/api/chat", json={"session_id": "nope", "message": "hi"}).status_code, 404)

    def test_debug_info_is_returned_only_when_requested(self):
        def fake_step(ev, st):
            st.update(lang="en", debug={"analysis": {"facts": {}}})
            return {"type": "question", "text": "Did you?", "topics": ["code_shared"]}
        with mock.patch.object(api.dialogue, "step", fake_step):
            plain = self.client.post("/api/chat", json={"message": "hi"}).json()
            debug = self.client.post("/api/chat", json={"message": "hi", "debug": True}).json()
        self.assertNotIn("debug", plain)
        self.assertEqual(debug["debug"], {"analysis": {"facts": {}}})

    def test_chat_returns_an_answer_card_with_disclaimer(self):
        final = {"type": "final", "answer": {"advice_text": "Do this.", "risk_level": "high", "urgency": "today", "primary_action": "contact_bank_and_block_cards",
                                             "steps": ["a"], "escalation_required": True, "escalation_target": "human_advisor",
                                             "citations": ["guidance_card_details_entered"], "signals_used": ["artifact"], "confidence": 0.8,
                                             "abstained": False}}
        with mock.patch.object(api.dialogue, "step", lambda ev, st: st.update(lang="en") or final):
            res = self.client.post("/api/chat", json={"message": "I typed my card number"}).json()
        self.assertEqual(res["type"], "answer")
        self.assertIn("not official DNA advice", res["answer"]["disclaimer"])
        self.assertEqual(res["answer"]["citations"][0]["id"], "guidance_card_details_entered")


if __name__ == "__main__":
    unittest.main()
