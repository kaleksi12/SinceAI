"""Prompt optimization for the analysis guidelines, in the style of ProTeGi.

Method: Pryzant et al., "Automatic Prompt Optimization with 'Gradient Descent' and Beam Search" (EMNLP 2023,
arXiv:2305.03495). The authors' code is MIT-licensed (github.com/microsoft/LMOps, folder prompt_optimization);
this is a small re-implementation for our task, not a copy of that code.

What is optimized: the GUIDELINES text in assistant/prompts.py (how the analysis step uses yes/no/unknown/na and how it
judges benign cases). The JSON format, the fact definitions and the action list stay fixed.

One round:
  1. Score each beam prompt on a random minibatch of TRAIN cases and collect the cases it gets wrong.
  2. "Gradients": ask the LLM why the prompt caused those errors (a natural-language critique).
  3. "Edits": ask the LLM to rewrite the prompt against each critique -> new candidate prompts.
  4. Select: a UCB bandit spends a fixed number of single-case evaluations on beam + candidates; the best stay.
Finally the baseline and the winners are compared on VALIDATION cases from scenario families never used above.

Scoring uses the kit's scoring.score_case on a decision-only answer (no advice text): the final action must be
acceptable, the decisive question asked, no escalation missed, risk within one level, no false alarm on benign cases;
each unnecessary question costs 0.15. One LLM call per case (the analysis step), so a run is cheap compared to
the full pipeline.

    python scripts/optimize_prompt.py --dry-run
    python scripts/optimize_prompt.py                       # defaults: 3 rounds, beam 2
The winner is NOT applied automatically: read best_guidelines.txt, then decide.
"""
import argparse
import hashlib
import json
import math
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from assistant import bot, kit, llm, prompts, rules  # noqa: E402
from dsakit import scoring  # noqa: E402  (the kit's scoring, on sys.path via assistant.kit)

MAX_WORDS = 420  # candidates longer than this are rejected (the current guidelines are about 250 words)
UCB_C = 0.8  # exploration weight of the bandit
UNNECESSARY_PENALTY = 0.15
INTERV = scoring._intervention()

TASK = """A security assistant for telecom customers works in steps. An LLM reads the user's message and fills in facts (each "yes", "no", "unknown" or "na") plus a proposed action and a benign flag, following GUIDELINES (the text you may change). Fixed code then applies rules: facts such as a shared code, money sent, card details entered, credentials entered, remote access or an installed app force protective actions; every decisive fact marked "unknown" becomes a question to the user (at most two); "benign" lets a harmless case end with "no action needed". A decision counts as correct when: the final action is an acceptable one; the decisive question is asked when the right action depends on a fact only the user knows; harmless cases get no alarm and no escalation; and no unnecessary questions are asked."""


# --- scoring one case ------------------------------------------------------------------------------------------------

def evaluate_case(guidelines, case, model):
    """Run the analysis step with these guidelines, apply the rules, and score the decision against the ground truth."""
    view = bot.build_view(case, set())  # gated signals hidden, as in the first pass of the real pipeline
    analysis, degraded = bot.analyze(view, list(case["consent"]["requires_consent"]), model, guidelines=guidelines)
    audience = case["audience"]
    ask = rules.evaluate(analysis["facts"], view["signals"], audience, benign=analysis["benign"])["ask"][:bot.MAX_QUESTIONS]
    env = rules.evaluate(analysis["facts"], view["signals"], audience, assume=ask, benign=analysis["benign"])
    final = rules.clamp({"primary_action": analysis["proposed_action"], "risk_level": analysis["risk_level"], "abstained": analysis["abstain"]},
                        env, audience)
    topics = [rules.SLOT_TOPIC[s] for s in ask]
    sub = {"case_id": case["case_id"], "mode": "single_turn", "primary_action": final["primary_action"], "risk_level": final["risk_level"],
           "advice_text": "decision scoring only, no advice text is written in this experiment", "steps": [],
           "escalation_required": final["escalation_required"], "escalation_target": final["escalation_target"],
           "question_topics": topics, "questions_asked": [], "signals_used": [], "consent_requested_for": [], "confidence": 0.5}
    res = scoring.score_case(case, sub, INTERV)
    failure_types = {f["type"] for f in res["failures"]}
    decision_ok = bool(res["action_ok"] and res["asked_ok"] is not False and "missed_escalation" not in failure_types and res["risk_within_one"])
    false_alarm = bool(res.get("false_alarm"))
    unnecessary = res["unnecessary_questions"]
    score = (1.0 if decision_ok and not false_alarm else 0.0) - UNNECESSARY_PENALTY * min(unnecessary, 2)
    return {"case_id": case["case_id"], "score": score, "ok": decision_ok and not false_alarm, "benign": res["benign"], "false_alarm": false_alarm,
            "asked_ok": res["asked_ok"], "unnecessary": unnecessary, "esc_fp": bool(res["esc_expected"] is False and res["esc_given"]),
            "action": final["primary_action"], "risk": final["risk_level"], "escalated": final["escalation_required"], "topics": topics,
            "facts": {k: v for k, v in analysis["facts"].items() if v != "na"}, "proposed": analysis["proposed_action"],
            "wrong_action": not res["action_ok"], "degraded": degraded}


def summarise(results):
    """Headline numbers for a list of case results."""
    n = len(results)
    if not n:
        return {}
    benign = [r for r in results if r["benign"]]
    must = [r for r in results if r["asked_ok"] is not None]
    return {"cases": n, "pass_rate": round(sum(r["ok"] for r in results) / n, 3), "mean_score": round(sum(r["score"] for r in results) / n, 3),
            "false_alarm_rate": round(sum(r["false_alarm"] for r in benign) / len(benign), 3) if benign else None,
            "decisive_question_rate": round(sum(bool(r["asked_ok"]) for r in must) / len(must), 3) if must else None,
            "unnecessary_questions_per_case": round(sum(r["unnecessary"] for r in results) / n, 3),
            "escalation_false_positives": sum(r["esc_fp"] for r in results), "degraded_analyses": sum(r["degraded"] for r in results)}


def bootstrap_ci(values, reps=1000, seed=7):
    rnd = random.Random(seed)
    means = sorted(sum(rnd.choice(values) for _ in values) / len(values) for _ in range(reps))
    return [round(means[int(0.025 * reps)], 3), round(means[int(0.975 * reps) - 1], 3)]


# --- candidates and selection ----------------------------------------------------------------------------------------

class Cand:
    """One candidate guidelines text with the per-case results gathered so far."""

    def __init__(self, text, parent=None, origin=""):
        self.text, self.parent, self.origin = text, parent, origin
        self.id = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
        self.results = {}  # case_id -> result

    @property
    def mean(self):
        return sum(r["score"] for r in self.results.values()) / max(1, len(self.results))


def evaluate_many(jobs, model, workers):
    """jobs: [(Cand, case)]; evaluates in parallel and stores the results on the candidates."""
    with ThreadPoolExecutor(workers) as ex:
        for (cand, case), res in zip(jobs, ex.map(lambda j: evaluate_case(j[0].text, j[1], model), jobs)):
            cand.results[case["case_id"]] = res


def ensure_minibatch(cand, train, size, rng, model, workers):
    """Make sure a candidate has at least `size` evaluated train cases (random ones)."""
    todo = [c for c in train if c["case_id"] not in cand.results]
    rng.shuffle(todo)
    evaluate_many([(cand, c) for c in todo[:max(0, size - len(cand.results))]], model, workers)


def run_ucb(pool, train, pulls, rng, model, workers):
    """Spend `pulls` single-case evaluations on the pool, favouring promising or little-tested candidates (UCB)."""
    done = 0
    while done < pulls:
        pending = {c.id: 0 for c in pool}
        total = sum(len(c.results) for c in pool) + 1
        jobs, taken = [], {c.id: set() for c in pool}
        for _ in range(min(workers, pulls - done)):
            def index(c):
                n = len(c.results) + pending[c.id]
                return float("inf") if n < 2 else c.mean + UCB_C * math.sqrt(math.log(total) / n)
            for c in sorted(pool, key=index, reverse=True):
                left = [x for x in train if x["case_id"] not in c.results and x["case_id"] not in taken[c.id]]
                if left:
                    case = rng.choice(left)
                    taken[c.id].add(case["case_id"])
                    pending[c.id] += 1
                    jobs.append((c, case))
                    break
        if not jobs:
            break
        evaluate_many(jobs, model, workers)
        done += len(jobs)


# --- gradients and edits (LLM calls) ---------------------------------------------------------------------------------

def describe_error(case, r):
    g = case["ground_truth"]
    acceptable = g["single_turn"]["acceptable_actions"] if g.get("twin_group") else [g["primary_action"]] + list(g["acceptable_actions"])
    wrong = []
    if r["wrong_action"]:
        wrong.append("wrong action")
    if r["asked_ok"] is False:
        wrong.append("did not ask the decisive question")
    if r["false_alarm"]:
        wrong.append("false alarm on a harmless case")
    if r["unnecessary"]:
        wrong.append("asked %d unnecessary question(s)" % r["unnecessary"])
    return ("User message: \"%s\" (%s, %s)\nModel's facts: %s; proposed action: %s\nPipeline result: action=%s, risk=%s, escalation=%s, questions about %s\n"
            "Expected: acceptable actions %s; must ask about %s; harmless case: %s; topics that matter: %s\nWhat went wrong: %s\nReference rationale: %s"
            % (case["opening_message"][:350], case["language"], case["audience"], json.dumps(r["facts"], ensure_ascii=False), r["proposed"],
               r["action"], r["risk"], r["escalated"], r["topics"] or "nothing", sorted(set(acceptable)), g["must_ask_topics"] or "nothing",
               "yes" if g["is_benign_control"] else "no", g["relevant_topics"], "; ".join(wrong) or "score below 1", g["rationale_en"][:220]))


def meta_call(system, user, model):
    """An LLM call for the optimizer itself; temperature 0.7 so repeated variants differ (variant number is in the prompt)."""
    return llm.complete([{"role": "system", "content": system}, {"role": "user", "content": user}], model=model, temperature=0.7, max_tokens=1800)


def make_gradient(cand, errors, cases_by_id, variant, n_variants, model):
    examples = "\n\n".join("Example %d\n%s" % (i + 1, describe_error(cases_by_id[r["case_id"]], r)) for i, r in enumerate(errors))
    system = "You help improve the guidelines of an LLM-based security assistant.\n\n" + TASK
    user = ("CURRENT GUIDELINES:\n%s\n\nThese are cases where the assistant's decision was wrong or poor:\n\n%s\n\n"
            "List up to 4 specific problems in the guidelines (missing, vague or misleading wording) that explain these errors. "
            "Describe general patterns, not the individual examples, and do not mention specific message texts. "
            "This is variant %d of %d: look at the errors from a different angle than the other variants would. Numbered list, plain text."
            % (cand.text, examples, variant + 1, n_variants))
    return meta_call(system, user, model)


def make_edit(cand, critique, variant, n_variants, model):
    system = "You rewrite the guidelines of an LLM-based security assistant.\n\n" + TASK
    user = ("CURRENT GUIDELINES:\n%s\n\nPROBLEMS FOUND:\n%s\n\nRewrite the guidelines to fix these problems. Rules: keep the same purpose and the "
            "yes/no/unknown/na scheme and the benign flag; keep rules that already work; write general rules only (no example-specific details); "
            "stay under %d words; start with the line \"Guidelines:\"; output only the new guidelines text. "
            "This is rewrite %d of %d: if there are several reasonable fixes, choose a different one than the other rewrites would."
            % (cand.text, critique, MAX_WORDS, variant + 1, n_variants))
    text = meta_call(system, user, model).strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1].strip()
    if not text.startswith("Guidelines:"):
        text = "Guidelines:\n" + text
    return text


def valid_candidate(text, seen):
    """Cheap sanity checks so a broken rewrite never reaches the bandit."""
    return (len(text.split()) <= MAX_WORDS and '"unknown"' in text and "benign" in text and '"na"' in text
            and hashlib.sha1(text.encode("utf-8")).hexdigest()[:8] not in seen)


# --- main ------------------------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", default=str(ROOT / "simset" / "data" / "dev" / "cases.jsonl"))
    ap.add_argument("--model", default="deepseek-ai/DeepSeek-V3.1")
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--beam", type=int, default=2, help="how many prompts survive each round")
    ap.add_argument("--grads", type=int, default=2, help="critiques per beam prompt per round")
    ap.add_argument("--edits", type=int, default=2, help="rewrites per critique")
    ap.add_argument("--minibatch", type=int, default=24, help="train cases a beam prompt is scored on before it is criticised")
    ap.add_argument("--errors", type=int, default=8, help="error examples shown to the critic")
    ap.add_argument("--pulls", type=int, default=96, help="single-case evaluations the bandit spends per round")
    ap.add_argument("--val-size", type=int, default=120, help="held-out cases for the final comparison")
    ap.add_argument("--train-frac", type=float, default=0.6, help="share of scenario families used for optimization")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--name", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cases = [json.loads(line) for line in open(a.cases, encoding="utf-8") if line.strip()]
    by_id = {c["case_id"]: c for c in cases}
    rng = random.Random(a.seed)
    # Split by scenario family: the validation families are never seen during optimization (the test set has unseen families too).
    families = sorted({c["scenario_family"] for c in cases})
    rng.shuffle(families)
    k = round(len(families) * a.train_frac)
    train_f, val_f = set(families[:k]), set(families[k:])
    train = [c for c in cases if c["scenario_family"] in train_f]
    val_all = [c for c in cases if c["scenario_family"] in val_f]
    val = rng.sample(val_all, min(a.val_size, len(val_all)))
    est = a.rounds * (a.beam * a.minibatch + a.beam * a.grads * (1 + a.edits) + a.pulls) + (a.beam + 1) * len(val)
    print("families: %d train / %d validation | cases: %d train / %d validation (using %d) | about %d LLM calls" %
          (len(train_f), len(val_f), len(train), len(val_all), len(val), est))
    if a.dry_run:
        return

    out = ROOT / "optimization" / ("%s_%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), a.name or a.model.split("/")[-1]))
    out.mkdir(parents=True)
    log = open(out / "log.jsonl", "w", encoding="utf-8")

    def note(**kw):
        log.write(json.dumps(kw, ensure_ascii=False) + "\n")
        log.flush()
        print("  " + ", ".join("%s=%s" % kv for kv in kw.items() if kv[0] != "text"))

    (out / "config.json").write_text(json.dumps({**vars(a), "train_families": sorted(train_f), "validation_families": sorted(val_f)}, indent=2), encoding="utf-8")
    baseline = Cand(prompts.GUIDELINES, origin="baseline")
    (out / "baseline_guidelines.txt").write_text(baseline.text, encoding="utf-8")
    everyone = {baseline.id: baseline}
    beam = [baseline]
    t0 = time.time()

    for rnd in range(a.rounds):
        print("=== round %d/%d (%.0f min elapsed)" % (rnd + 1, a.rounds, (time.time() - t0) / 60))
        new = []
        for cand in beam:
            ensure_minibatch(cand, train, a.minibatch, rng, a.model, a.workers)
            errors = [r for r in cand.results.values() if r["score"] < 1.0]
            rng.shuffle(errors)
            errors.sort(key=lambda r: r["ok"])  # real mistakes first, then merely unnecessary questions
            errors = errors[:a.errors]
            note(event="beam", round=rnd + 1, cand=cand.id, evaluated=len(cand.results), mean=round(cand.mean, 3), errors_shown=len(errors))
            if not errors:
                continue
            for v in range(a.grads):
                critique = make_gradient(cand, errors, by_id, v, a.grads, a.model)
                note(event="critique", round=rnd + 1, cand=cand.id, variant=v + 1, text=critique[:600])
                for e in range(a.edits):
                    text = make_edit(cand, critique, e, a.edits, a.model)
                    if valid_candidate(text, everyone):
                        child = Cand(text, parent=cand.id, origin="round%d critique%d rewrite%d" % (rnd + 1, v + 1, e + 1))
                        everyone[child.id] = child
                        new.append(child)
                    else:
                        note(event="rejected_rewrite", round=rnd + 1, words=len(text.split()))
        pool = beam + new
        run_ucb(pool, train, a.pulls, rng, a.model, a.workers)
        ranked = sorted(pool, key=lambda c: (len(c.results) >= 6, c.mean), reverse=True)  # barely-tested candidates cannot win
        beam = ranked[:a.beam]
        for c in ranked:
            note(event="candidate", round=rnd + 1, cand=c.id, parent=c.parent, evaluated=len(c.results), mean=round(c.mean, 3), kept=c in beam)

    # Final comparison on held-out families.
    finalists = [baseline] + [c for c in beam if c is not baseline]
    print("=== validation on %d held-out cases (%d families)" % (len(val), len({c["scenario_family"] for c in val})))
    val_results = {}
    for c in finalists:
        with ThreadPoolExecutor(a.workers) as ex:
            res = list(ex.map(lambda case, c=c: evaluate_case(c.text, case, a.model), val))
        val_results[c.id] = res
        s = summarise(res)
        s["pass_rate_95ci"] = bootstrap_ci([float(r["ok"]) for r in res])
        print("  %s: %s" % (c.id, s))
    best = max((c for c in finalists), key=lambda c: summarise(val_results[c.id])["mean_score"])
    base_res = {r["case_id"]: r["ok"] for r in val_results[baseline.id]}
    best_res = {r["case_id"]: r["ok"] for r in val_results[best.id]}
    wins = sum(best_res[i] and not base_res[i] for i in base_res)
    losses = sum(base_res[i] and not best_res[i] for i in base_res)

    summary = {"minutes": round((time.time() - t0) / 60, 1), "llm_calls": llm.stats["calls"], "cache_hits": llm.stats["cache_hits"],
               "best": best.id, "best_is_baseline": best is baseline, "validation": {c.id: summarise(val_results[c.id]) for c in finalists},
               "best_vs_baseline_on_validation": {"cases_best_fixes": wins, "cases_best_breaks": losses},
               "train_means": {c.id: round(c.mean, 3) for c in finalists}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out / "best_guidelines.txt").write_text(best.text, encoding="utf-8")
    (out / "candidates.jsonl").write_text("".join(json.dumps({"id": c.id, "parent": c.parent, "origin": c.origin, "evaluated": len(c.results), "train_mean": round(c.mean, 3),
                                                                 "text": c.text}, ensure_ascii=False) + "\n" for c in everyone.values()), encoding="utf-8")
    (out / "validation_results.json").write_text(json.dumps(val_results, ensure_ascii=False), encoding="utf-8")
    print("best candidate: %s (baseline: %s) | fixes %d, breaks %d validation cases | written to %s" % (best.id, best is baseline, wins, losses, out))


if __name__ == "__main__":
    main()
