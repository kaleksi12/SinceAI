#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Run your assistant in multi-turn conversations against the simulated user.

Two ways to plug in your assistant:

  1. Any language, over stdin/stdout (one JSON object per line):
       python3 sim/run_conversation.py --cases data/dev/cases.jsonl --bot "node examples/minimal_bot.js" --out mt.jsonl

  2. A Python function step(event, state) -> reply:
       python3 sim/run_conversation.py --cases data/dev/cases.jsonl --bot-py examples/python_bot.py:step --out mt.jsonl

Then score the transcripts like any submission:
       python3 eval/evaluate.py --cases data/dev/cases.jsonl --submission mt.jsonl

Protocol (see sim/PROTOCOL.md):
  harness -> bot  {"type":"start","conversation_id":...,"case":{visible case},"max_assistant_turns":6}
  bot -> harness  {"type":"question","text":"...","topics":[optional]}
                | {"type":"consent_request","fields":["device.recent_app_installs"],"text":"..."}
                | {"type":"final","answer":{submission fields}}
  harness -> bot  {"type":"user_reply","text":"..."}
                | {"type":"consent_reply","granted":[...],"refused":[...],"text":"...","signals":{path: value}}
                | {"type":"turn_limit"}   (send your final answer now)

Consent-gated signals arrive as "available_with_consent" until you ask and the
simulated user agrees. Works on the dev split only: test cases have no
simulation facts in the participant package.
"""
import argparse
import importlib.util
import json
import os
import select
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ROOT)

from dsakit import scoring  # noqa: E402
from dsakit.simulator import UserSimulator, visible_case  # noqa: E402


class BotError(Exception):
    pass


class SubprocessBot:
    def __init__(self, cmd, timeout=30):
        self.cmd, self.timeout = cmd, timeout
        self._start()

    def _start(self):
        self.p = subprocess.Popen(self.cmd, shell=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1)

    def restart(self):
        try:
            self.p.kill()
        except Exception:
            pass
        self._start()

    def send(self, event, state):
        try:
            self.p.stdin.write(json.dumps(event, ensure_ascii=False) + "\n")
            self.p.stdin.flush()
        except (BrokenPipeError, OSError):
            raise BotError("bot process is not accepting input")
        ready, _, _ = select.select([self.p.stdout], [], [], self.timeout)
        if not ready:
            raise BotError("bot did not reply within %ss" % self.timeout)
        line = self.p.stdout.readline()
        if not line:
            raise BotError("bot process closed its output")
        try:
            reply = json.loads(line)
        except json.JSONDecodeError:
            raise BotError("bot replied with invalid JSON: %r" % line[:120])
        return reply

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=5)
        except Exception:
            self.p.kill()


class PyBot:
    def __init__(self, spec):
        path, func = spec.rsplit(":", 1)
        s = importlib.util.spec_from_file_location("team_bot", path)
        m = importlib.util.module_from_spec(s)
        s.loader.exec_module(m)
        self.f = getattr(m, func)

    def send(self, event, state):
        try:
            return self.f(event, state)
        except Exception as e:
            raise BotError("bot raised %s: %s" % (type(e).__name__, str(e)[:120]))

    def restart(self):
        pass

    def close(self):
        pass


def run_one(bot, case, max_turns):
    sim = UserSimulator(case)
    state = {}
    transcript = [{"role": "user", "type": "opening", "text": case["opening_message"]}]
    event = {"type": "start", "conversation_id": case["case_id"], "case": visible_case(case), "max_assistant_turns": max_turns}
    final = None
    turns = 0
    while True:
        reply = bot.send(event, state)
        if not isinstance(reply, dict):
            raise BotError("bot reply is not a JSON object")
        rtype = reply.get("type")
        if rtype == "final":
            ans = reply.get("answer")
            if not isinstance(ans, dict):
                raise BotError("final answer is not a JSON object")
            final = dict(ans)
            transcript.append({"role": "assistant", "type": "final", "text": str(final.get("advice_text", ""))})
            break
        turns += 1
        if turns > max_turns:
            transcript.append({"role": "system", "type": "turn_limit"})
            event = {"type": "turn_limit"}
            reply = bot.send(event, state)
            if isinstance(reply, dict) and reply.get("type") == "final" and isinstance(reply.get("answer"), dict):
                final = dict(reply["answer"])
                transcript.append({"role": "assistant", "type": "final", "text": final.get("advice_text", "")})
            break
        if rtype == "question":
            transcript.append({"role": "assistant", "type": "question", "text": reply.get("text", ""), "topics": reply.get("topics") or []})
            ans = sim.answer(reply.get("text", ""), reply.get("topics"))
            transcript.append({"role": "user", "type": "answer", "text": ans})
            event = {"type": "user_reply", "text": ans}
        elif rtype == "consent_request":
            transcript.append({"role": "assistant", "type": "consent_request", "text": reply.get("text", ""), "fields": reply.get("fields") or []})
            c = sim.consent(reply.get("fields") or [])
            transcript.append({"role": "user", "type": "consent_reply", "text": c["text"], "granted": c["granted"], "refused": c["refused"]})
            event = {"type": "consent_reply", "granted": c["granted"], "refused": c["refused"], "text": c["text"], "signals": c.get("signals", {})}
        else:
            transcript.append({"role": "system", "type": "invalid_reply", "value": str(reply)[:200]})
            event = {"type": "user_reply", "text": sim.sim["unknown_reply"]}
    summ = sim.summary()
    summ["asked_topics_flat"] = sorted(set(sum(sim.asked_topics, [])) - {"__too_many__"})
    out = final or {"primary_action": "escalate_to_human", "risk_level": "medium", "advice_text": "", "escalation_required": True, "abstained": True}
    out["case_id"] = case["case_id"]
    out["mode"] = "multi_turn"
    out["transcript"] = transcript
    out["conversation"] = summ
    out.setdefault("questions_asked", [t["text"] for t in transcript if t.get("type") == "question"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cases", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bot", help="shell command that speaks the JSON-lines protocol")
    g.add_argument("--bot-py", help="path/to/file.py:function implementing step(event, state)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="only the first N cases")
    ap.add_argument("--journey", default=None, help="only one journey")
    ap.add_argument("--max-turns", type=int, default=6)
    ap.add_argument("--show", action="store_true", help="print each transcript")
    ap.add_argument("--timeout", type=int, default=30, help="seconds to wait for each bot reply (subprocess bots)")
    a = ap.parse_args()

    cases = scoring.load_jsonl(a.cases)
    if cases and "simulation" not in cases[0]:
        sys.exit("These cases have no simulation block. Multi-turn runs work on data/dev/cases.jsonl.")
    if a.journey:
        cases = [c for c in cases if c["journey"] == a.journey]
    if a.limit:
        cases = cases[:a.limit]
    bot = SubprocessBot(a.bot, a.timeout) if a.bot else PyBot(a.bot_py)
    n = errors = 0
    with open(a.out, "w", encoding="utf-8") as f:
        for c in cases:
            try:
                res = run_one(bot, c, a.max_turns)
            except BotError as e:
                errors += 1
                print("  %s: %s (recorded as a missing answer)" % (c["case_id"], e))
                bot.restart()
                res = {"case_id": c["case_id"], "mode": "multi_turn", "primary_action": "escalate_to_human", "risk_level": "medium",
                       "advice_text": "", "escalation_required": False, "abstained": True, "notes": "harness error: %s" % e,
                       "conversation": {"questions": 0, "unnecessary_questions": 0, "asked_topics_flat": [], "must_ask_satisfied": False,
                                        "consent_granted": [], "consent_refused": []}}
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            n += 1
            if a.show:
                print("=== %s (%s)" % (c["case_id"], c["journey"]))
                for t in res["transcript"]:
                    print("  %-9s %-15s %s" % (t["role"], t["type"], (t.get("text") or "")[:140]))
    bot.close()
    print("wrote %d conversations to %s%s" % (n, a.out, (" (%d bot errors)" % errors) if errors else ""))


if __name__ == "__main__":
    main()
