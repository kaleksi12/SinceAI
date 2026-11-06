"""Run the single-turn bot over a cases file and write a submission file.

    python scripts/run_single.py --cases simset/data/dev/cases.jsonl --out out/dev_single.jsonl --sample 60 --model <id>
"""
import argparse
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from assistant import bot, kit, llm  # noqa: E402


def safe_answer(case, model):
    try:
        return bot.answer_single_turn(case, model)
    except Exception as e:  # keep the run going; the evaluator counts a missing answer
        print("  %s failed: %s: %s" % (case["case_id"], type(e).__name__, str(e)[:120]))
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model")
    ap.add_argument("--sample", type=int, default=0, help="random sample of N cases (seed 7)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()

    cases = [json.loads(line) for line in open(a.cases, encoding="utf-8") if line.strip()]
    if a.sample:
        cases = random.Random(7).sample(cases, a.sample)
    if a.limit:
        cases = cases[:a.limit]
    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(lambda c: safe_answer(c, a.model), cases))
    ok = [r for r in results if r]
    with open(a.out, "w", encoding="utf-8") as f:
        for r in ok:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    fb = sum(1 for r in ok if json.loads(r["notes"])["fallback"])
    dg = sum(1 for r in ok if json.loads(r["notes"])["degraded"])
    print("wrote %d/%d answers to %s | llm calls %d, cache hits %d | writer fallbacks %d, degraded analyses %d"
          % (len(ok), len(cases), a.out, llm.stats["calls"], llm.stats["cache_hits"], fb, dg))
    with open(Path(a.out).with_suffix(".cases.jsonl"), "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
