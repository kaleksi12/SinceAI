"""Run the single-turn bot and write everything about the run into its own folder under runs/.

    python scripts/run_single.py --cases simset/data/dev/cases.jsonl --sample 60 --model <id>

Each run folder holds: predictions.jsonl, cases.jsonl (the cases that were run), report.json and report.txt
(the kit's evaluate.py), validation.txt (the kit's validate.py), baseline_predictions.jsonl, baseline_report.json
and baseline_report.txt (the kit's rules baseline on the same cases) and run_meta.json.
Test inputs have no ground truth, so only predictions, cases, validation and run_meta are written for them.
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from assistant import bot, llm  # noqa: E402

EVALUATE = ROOT / "simset" / "eval" / "evaluate.py"
VALIDATE = ROOT / "simset" / "tools" / "validate.py"
BASELINE = ROOT / "simset" / "baselines" / "rules_baseline.py"


def safe_answer(case, model):
    try:
        return bot.answer_single_turn(case, model)
    except Exception as e:  # keep the run going; the evaluator counts a missing answer
        print("  %s failed: %s: %s" % (case["case_id"], type(e).__name__, str(e)[:120]))
        return None


def run_tool(script, *args):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    res = subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, encoding="utf-8", env=env)
    return res.stdout + res.stderr, res.stdout


def git_state():
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", "assistant", "scripts"], capture_output=True, text=True, cwd=ROOT).stdout.strip())
        return rev + ("+uncommitted changes" if dirty else "")
    except OSError:
        return "unknown"


def evaluate_into(run_dir, cases_path, preds_path, prefix):
    text, _ = run_tool(EVALUATE, "--cases", str(cases_path), "--submission", str(preds_path), "--failures", "100")
    (run_dir / (prefix + "report.txt")).write_text(text, encoding="utf-8")
    _, js = run_tool(EVALUATE, "--cases", str(cases_path), "--submission", str(preds_path), "--json", "--failures", "100")
    (run_dir / (prefix + "report.json")).write_text(js, encoding="utf-8")
    return json.loads(js)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--model")
    ap.add_argument("--name", help="label for the run folder (default: model name and number of cases)")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--sample", type=int, default=0, help="random sample of N cases (seed 7)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    model = a.model or os.environ.get("LLM_MODEL", "unknown")
    cases = [json.loads(line) for line in open(a.cases, encoding="utf-8") if line.strip()]
    if a.sample:
        cases = random.Random(7).sample(cases, a.sample)
    if a.limit:
        cases = cases[:a.limit]
    has_truth = "ground_truth" in cases[0]

    label = a.name or "%s_%s" % (re.sub(r"[^A-Za-z0-9.]+", "-", model.split("/")[-1]), len(cases))
    run_dir = Path(a.runs_dir) / ("%s_%s" % (datetime.now().strftime("%Y%m%d-%H%M%S"), label))
    run_dir.mkdir(parents=True)

    t0 = time.time()
    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(lambda c: safe_answer(c, model), cases))
    ok = [r for r in results if r]
    seconds = round(time.time() - t0)

    preds, cases_path = run_dir / "predictions.jsonl", run_dir / "cases.jsonl"
    preds.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ok), encoding="utf-8")
    cases_path.write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases), encoding="utf-8")

    meta = {"started": datetime.now().isoformat(timespec="seconds"), "model": model, "cases_file": str(a.cases), "n_cases": len(cases),
            "sample": a.sample, "answers": len(ok), "workers": a.workers, "seconds": seconds, "llm_calls": llm.stats["calls"],
            "cache_hits": llm.stats["cache_hits"], "writer_fallbacks": sum(1 for r in ok if json.loads(r["notes"])["fallback"]),
            "degraded_analyses": sum(1 for r in ok if json.loads(r["notes"])["degraded"]), "git": git_state()}
    (run_dir / "run_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    val_args = ["--submission", str(preds)] + (["--cases", str(cases_path)] if has_truth else [])
    (run_dir / "validation.txt").write_text(run_tool(VALIDATE, *val_args)[0], encoding="utf-8")

    print("run folder: %s" % run_dir)
    print("answers %d/%d | llm calls %d, cache hits %d | writer fallbacks %d | %ds" % (len(ok), len(cases), meta["llm_calls"], meta["cache_hits"],
                                                                                     meta["writer_fallbacks"], seconds))
    print("validation:", (run_dir / "validation.txt").read_text(encoding="utf-8").strip().splitlines()[-1])
    if not has_truth:
        return
    base = run_dir / "baseline_predictions.jsonl"
    run_tool(BASELINE, "--cases", str(cases_path), "--out", str(base))
    ours, theirs = evaluate_into(run_dir, cases_path, preds, ""), evaluate_into(run_dir, cases_path, base, "baseline_")
    rows = [("safe-action pass %", "safe_action_pass_pct"), ("false alarms on benign %", "false_alarm_rate_on_benign_pct"),
            ("escalation recall %", "escalation_recall_pct"), ("asked decisive question %", "asked_decisive_question_pct"),
            ("unsafe statements %", "unsafe_statement_rate_pct")]
    print("%-28s %10s %10s" % ("", "bot", "baseline"))
    for name, key in rows:
        print("%-28s %10s %10s" % (name, ours["headline"][key], theirs["headline"][key]))
    key = "weighted_proxy_over_assessed_dimensions"
    print("%-28s %10s %10s" % ("weighted proxy", ours["brief_scorecard_proxy"][key], theirs["brief_scorecard_proxy"][key]))


if __name__ == "__main__":
    main()
