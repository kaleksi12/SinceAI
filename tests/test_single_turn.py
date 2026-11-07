"""Single-turn decision layer (bot.single_turn_envelope / pick_questions), without the LLM."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from assistant import bot, rules  # noqa: E402


def an(facts, benign=False):
    f = {k: "na" for k in bot.BOOL_FACTS + list(bot.CHOICES)}
    f.update(facts)
    return {"facts": f, "benign": benign}


class SingleTurnTest(unittest.TestCase):
    def test_assumed_branch_does_not_replace_the_action(self):
        # "Should I give the code?": nothing done yet. Asking is fine, but 'delete this' must not become 'call your bank'.
        ask, env = bot.single_turn_envelope(an({"code_shared": "unknown", "code_for": "bank"}), {}, "consumer", "en")
        self.assertEqual(ask, ["code_shared"])
        self.assertIsNone(env["forced_action"])
        self.assertIn("contact_bank_and_block_cards", env["also_actions"])

    def test_known_fact_still_forces_the_action(self):
        _, env = bot.single_turn_envelope(an({"card_details_entered": "yes"}), {}, "consumer", "en")
        self.assertEqual(env["forced_action"], "contact_bank_and_block_cards")

    def test_unconfirmed_code_is_still_asked(self):
        ask, _ = bot.single_turn_envelope(an({"code_shared": "yes", "code_for": "operator"}), {}, "consumer", "en")
        self.assertEqual(ask, ["code_shared"])

    def test_handoff_of_the_riskier_branch_is_kept(self):
        _, env = bot.single_turn_envelope(an({"money_transferred": "unknown"}), {}, "small_business", "fi")
        final = rules.clamp({"primary_action": "verify_via_official_channel", "risk_level": "high"}, env, "small_business")
        self.assertEqual(final["primary_action"], "verify_via_official_channel")
        self.assertTrue(final["escalation_required"])

    def test_questions_stay_within_three_topics(self):
        for lang in ("fi", "en", "sv"):
            chosen = bot.pick_questions(["card_details_entered", "money_transferred", "credentials_entered"], lang)
            topics = set()
            for s in chosen:
                topics |= {rules.SLOT_TOPIC[s]} | bot.kit.textcheck.topics_in(bot.question_text(rules.SLOT_TOPIC[s], lang))
            self.assertLessEqual(len(topics), 3)


if __name__ == "__main__":
    unittest.main()
