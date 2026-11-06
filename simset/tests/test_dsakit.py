# -*- coding: utf-8 -*-
"""Unit tests for the participant package. Standard library only.

    python3 -m unittest discover -s tests -v
"""
import json
import os
import sys
import unittest

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)

from dsakit import minischema, scoring, textcheck  # noqa: E402
from dsakit.simulator import UserSimulator, visible_case, SENSITIVE_HIDDEN  # noqa: E402

DEV = scoring.load_jsonl(os.path.join(ROOT, "data/dev/cases.jsonl"))
TEST = scoring.load_jsonl(os.path.join(ROOT, "data/test/inputs.jsonl"))


def oracle(c):
    """Single-turn oracle: for twins, the provisional action that is safe if the riskier answer is true."""
    g = c["ground_truth"]
    st = g["single_turn"]
    twin = bool(g["twin_group"])
    lang = "en" if c["language"] == "en" else "fi"
    nec = g["necessary_signals"]
    return {"case_id": c["case_id"], "risk_level": st["risk_range"][1] if twin else g["risk_level"],
            "primary_action": st["acceptable_actions"][0] if twin else g["primary_action"],
            "advice_text": g["reference_answer_" + lang], "escalation_required": st["escalation_required"] if twin else g["escalation"]["required"],
            "escalation_target": g["escalation"]["target"], "question_topics": g["must_ask_topics"], "citations": g["guidance_refs"],
            "signals_used": ["artifact"] + nec, "consent_requested_for": [s for s in nec if s not in c["consent"]["pre_granted"]]}


class TestUnsafeDetection(unittest.TestCase):
    def test_negated_english(self):
        self.assertEqual(textcheck.find_unsafe("Do not pay the fee. Never share the code.", ["pay_the_fee", "share_code"]), [])

    def test_positive_english(self):
        hits = {h["claim"] for h in textcheck.find_unsafe("It is fine, you can pay the fee now.", ["pay_the_fee"])}
        self.assertIn("pay_the_fee", hits)

    def test_negated_finnish(self):
        self.assertEqual(textcheck.find_unsafe("Älä avaa linkkiä äläkä maksa maksua.", ["pay_the_fee", "open_link_to_check"]), [])

    def test_positive_finnish(self):
        hits = {h["claim"] for h in textcheck.find_unsafe("Voit maksaa sen, summa on pieni.", ["pay_the_fee"])}
        self.assertIn("pay_the_fee", hits)

    def test_approve_prompt(self):
        hits = {h["claim"] for h in textcheck.find_unsafe("Approve one so they stop.", ["approve_prompt"])}
        self.assertIn("approve_prompt", hits)
        self.assertEqual(textcheck.find_unsafe("Do not approve any of the requests.", ["approve_prompt"]), [])

    def test_uninstall_is_not_install(self):
        self.assertEqual(textcheck.find_unsafe("Uninstall the remote support program.", ["give_remote_access"]), [])

    def test_swedish_negation(self):
        self.assertEqual(textcheck.find_unsafe("Betala inte avgiften.", ["pay_the_fee"]), [])


class TestSteps(unittest.TestCase):
    def test_en(self):
        s = textcheck.find_steps("Do not open the link. Call your bank now and block the card.")
        self.assertTrue({"dont_open_link", "contact_bank_now", "block_card"} <= s)

    def test_fi(self):
        s = textcheck.find_steps("Laita puhelin lentotilaan äläkä käytä sillä verkkopankkia. Poista sovellus.")
        self.assertTrue({"disconnect_device", "avoid_banking_on_device", "remove_app_or_profile"} <= s)

    def test_sv(self):
        s = textcheck.find_steps("Öppna inte länken. Kontakta din bank.")
        self.assertTrue({"dont_open_link", "contact_bank_now"} <= s)


class TestTopicsAndLanguage(unittest.TestCase):
    def test_topics(self):
        self.assertIn("card_details_entered", textcheck.topics_in("Syötitkö sivulle korttitietoja?"))
        self.assertIn("code_shared", textcheck.topics_in("Did you read out the code to the caller?"))
        self.assertIn("self_initiated", textcheck.topics_in("Tilasitko itse uuden eSIMin?"))

    def test_language(self):
        self.assertEqual(textcheck.detect_language("Älä avaa linkkiä ja ota yhteyttä pankkiin."), "fi")
        self.assertEqual(textcheck.detect_language("Do not open the link and call your bank."), "en")
        self.assertEqual(textcheck.detect_language("Öppna inte länken och ring din bank."), "sv")


class TestSimulator(unittest.TestCase):
    def setUp(self):
        self.case = next(c for c in DEV if c["ground_truth"]["twin_group"] and c["ground_truth"]["must_ask_topics"] == ["card_details_entered"])

    def test_reveals_only_when_asked(self):
        sim = UserSimulator(self.case)
        self.assertEqual(sim.answer("What is the weather like?"), self.case["simulation"]["unknown_reply"])
        fact = self.case["simulation"]["facts"]["card_details_entered"]
        self.assertIn(fact, sim.answer("Did you enter your card details?", ["card_details_entered"]))
        self.assertTrue(sim.summary()["must_ask_satisfied"])

    def test_visible_case_hides(self):
        v = visible_case(self.case)
        self.assertNotIn("ground_truth", v)
        self.assertNotIn("simulation", v)
        hidden = [p for p in self.case["consent"]["requires_consent"] if p not in self.case["consent"]["pre_granted"]]
        top, key = hidden[0].split(".", 1) if "." in hidden[0] else (hidden[0], None)
        val = v["signals"][top][key] if key else v["signals"][top]
        self.assertEqual(val, SENSITIVE_HIDDEN)

    def test_consent_refusal(self):
        c = next((c for c in DEV if c["simulation"]["consent_policy"] == "refuse"), None)
        if c is None:
            self.skipTest("no refusing user in dev")
        sim = UserSimulator(c)
        res = sim.consent(c["consent"]["requires_consent"][:1])
        self.assertEqual(res["granted"], [])


class TestScoring(unittest.TestCase):
    def test_oracle_high(self):
        rep, _ = scoring.evaluate(DEV, [oracle(c) for c in DEV], with_ci=False)
        self.assertGreaterEqual(rep["headline"]["safe_action_pass_pct"], 95.0)
        self.assertEqual(rep["headline"]["unsafe_statement_rate_pct"], 0.0)

    def test_empty_zero(self):
        rep, _ = scoring.evaluate(DEV, [], with_ci=False)
        self.assertEqual(rep["headline"]["safe_action_pass_pct"], 0.0)

    def test_always_benign_is_bad(self):
        subs = [{"case_id": c["case_id"], "risk_level": "none", "primary_action": "no_action_needed", "advice_text": "Nothing to do.",
                 "escalation_required": False} for c in DEV]
        rep, _ = scoring.evaluate(DEV, subs, with_ci=False)
        self.assertLess(rep["headline"]["safe_action_pass_pct"], 35.0)

    def test_consent_violation_detected(self):
        c = next(c for c in DEV if c["ground_truth"]["necessary_signals"] and not c["consent"]["pre_granted"])
        s = oracle(c)
        s["consent_requested_for"] = []
        rep, rows = scoring.evaluate([c], [s], with_ci=False)
        self.assertTrue(rows[0]["consent_violation"])


class TestData(unittest.TestCase):
    def test_schemas(self):
        cs = json.load(open(os.path.join(ROOT, "schema/case.schema.json"), encoding="utf-8"))
        ts = json.load(open(os.path.join(ROOT, "schema/test_input.schema.json"), encoding="utf-8"))
        for c in DEV:
            self.assertEqual(minischema.validate(c, cs), [], c["case_id"])
        for c in TEST:
            self.assertEqual(minischema.validate(c, ts), [], c["case_id"])

    def test_reference_answers_pass_own_checks(self):
        for c in DEV:
            g = c["ground_truth"]
            for lang in ("fi", "en"):
                txt = g["reference_answer_" + lang]
                found = textcheck.find_steps(txt)
                self.assertTrue(set(g["required_steps"]) <= found, (c["case_id"], lang, set(g["required_steps"]) - found))
                self.assertEqual(textcheck.find_unsafe(txt, g["must_not"]), [], (c["case_id"], lang))

    def test_no_ground_truth_in_test(self):
        for c in TEST:
            self.assertNotIn("ground_truth", c)
            self.assertNotIn("simulation", c)
            self.assertNotIn("scenario_family", c)


if __name__ == "__main__":
    unittest.main()
