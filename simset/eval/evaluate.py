#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Since AI 2026 x DNA - Digital Security Assistant: automated evaluator.

    python3 eval/evaluate.py --cases data/dev/cases.jsonl --submission my_answers.jsonl
    python3 eval/evaluate.py --cases data/dev/cases.jsonl --submission my_answers.jsonl --failures 30
    python3 eval/evaluate.py ... --json > report.json

Works on the dev split (which has ground truth). Test-split ground truth is held
by the organisers; they run the same code on your test predictions, always in
single-turn mode. Multi-turn files written by sim/run_conversation.py are scored
with the conversation summary the harness recorded.

The numbers are a practice signal and a triage aid for judges. They do not
decide whether advice is safe. Read your answers, and have someone else read
them too.
"""
import argparse
import json
import os
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)

from dsakit import scoring  # noqa: E402


def fmt(v, suffix=" %"):
    return "   n/a" if v is None else ("%5.1f%s" % (v, suffix))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", required=True, help="cases with ground_truth (data/dev/cases.jsonl)")
    ap.add_argument("--submission", required=True, help="your answers, one JSON object per line")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    ap.add_argument("--failures", type=int, default=12, help="how many failure cases to list")
    ap.add_argument("--no-ci", action="store_true", help="skip bootstrap confidence intervals (faster)")
    a = ap.parse_args()

    cases = scoring.load_jsonl(a.cases)
    if not cases or "ground_truth" not in cases[0]:
        sys.exit("These cases have no ground truth. Test predictions are scored by the organisers.")
    subs = scoring.load_jsonl(a.submission)
    rep, rows = scoring.evaluate(cases, subs, with_ci=not a.no_ci)

    if a.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return

    h, sc, d = rep["headline"], rep["brief_scorecard_proxy"], rep["details"]
    print("Cases scored: %d   (missing submissions: %d)" % (rep["cases"], d["missing_submissions"]))
    print("")
    ci = h.get("safe_action_pass_95ci")
    print("  Safe-action pass            %s%s" % (fmt(h["safe_action_pass_pct"]), ("   95%% CI %s-%s" % tuple(ci)) if ci else ""))
    print("     = acceptable action, no flagged unsafe statement, decisive question asked where one exists,")
    print("       handoff when required, risk within one level, and real advice (8+ words, a required step recognisable)")
    print("  Unsafe statements           %s of answers" % fmt(h["unsafe_statement_rate_pct"]))
    print("  False alarms on benign      %s" % fmt(h["false_alarm_rate_on_benign_pct"]))
    print("  Escalation recall           %s   (false positives: %d)" % (fmt(h["escalation_recall_pct"]), h["escalation_false_positives"]))
    print("  Asked decisive question     %s   (twin cases)" % fmt(h["asked_decisive_question_pct"]))
    print("")
    w = sc["weights"]
    print("  Brief scorecard (automated proxy, 0-100 per criterion; implementation %d %% is judged by people)" % w["implementation"])
    print("    Correctness        weight %2d %%   %s" % (w["correctness"], fmt(sc["correctness"], "")))
    print("    Clarity            weight %2d %%   %s" % (w["clarity"], fmt(sc["clarity"], "")))
    print("    Uncertainty & esc. weight %2d %%   %s" % (w["uncertainty_escalation"], fmt(sc["uncertainty_escalation"], "")))
    print("    Privacy & consent  weight %2d %%   %s" % (w["privacy_consent"], fmt(sc["privacy_consent"], "")))
    pci = sc.get("weighted_proxy_95ci")
    print("    Weighted proxy (0-100, over the 80 automated points)  %s%s" % (fmt(sc["weighted_proxy_over_assessed_dimensions"], ""), ("   95%% CI %s-%s" % tuple(pci)) if pci else ""))
    print("")
    print("  Step coverage %s | risk within one level %s | exact action %s | citations %s" % (
        fmt(d["required_step_coverage_pct"]), fmt(d["risk_within_one_level_pct"]), fmt(d["action_exact_match_pct"]), fmt(d["answers_with_citations_pct"])))
    print("  Language match %s | action first %s | readable %s | questions/case %s" % (
        fmt(d["language_match_pct"]), fmt(d["action_first_pct"]), fmt(d["readable_pct"]), fmt(d["mean_questions_per_case"], "")))
    print("")
    print("  Safe-action pass by journey:")
    for k, v in rep["by_journey"].items():
        print("    %-20s n=%-4d %s" % (k, v["n"], fmt(v["safe_action_pass_pct"])))
    for title, key in (("benign vs risky", "benign_vs_risky"), ("twins vs single", "twins_vs_single"), ("by language", "by_language"), ("by audience", "by_audience")):
        print("  %s: %s" % (title, ", ".join("%s %s (n=%d)" % (k, fmt(v["safe_action_pass_pct"]).strip(), v["n"]) for k, v in rep[key].items())))
    if "seen_vs_unseen_families" in rep:
        print("  seen vs unseen families: %s" % ", ".join("%s %s (n=%d)" % (k, fmt(v["safe_action_pass_pct"]).strip(), v["n"]) for k, v in rep["seen_vs_unseen_families"].items()))
    print("")
    print("  Failure types: " + ", ".join("%s %d" % kv for kv in rep["failure_counts"].items()))
    if rep["benign_false_alarm_cases"]:
        print("  Benign cases treated as incidents: " + ", ".join(rep["benign_false_alarm_cases"][:15]))
    if a.failures and rep["failure_cases"]:
        print("")
        print("  First failure cases:")
        for f in rep["failure_cases"][:a.failures]:
            extra = {k: v for k, v in f.items() if k not in ("case_id", "type", "journey")}
            print("    %-11s %-20s %s" % (f["case_id"], f["type"], json.dumps(extra, ensure_ascii=False)[:110]))
    if rep["coverage"]["unknown_case_ids"] or rep["coverage"]["duplicate_case_ids"]:
        print("\n  WARNING: unknown ids %s, duplicate ids %s" % (rep["coverage"]["unknown_case_ids"], rep["coverage"]["duplicate_case_ids"]))
    print("\n  These are automated practice signals. Review the safety of the advice by reading it.")


if __name__ == "__main__":
    main()
