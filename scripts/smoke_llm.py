"""Check the Featherless key, JSON output and Finnish quality.

    python scripts/smoke_llm.py --list            # list model ids
    python scripts/smoke_llm.py --model <id>      # test one model
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from assistant import llm  # noqa: E402

PROMPT = [
    {"role": "system", "content": "You are a security assistant. Reply with a single JSON object and nothing else."},
    {"role": "user", "content": 'Käyttäjä kirjoittaa: "Sain tekstiviestin, jossa pyydetään maksamaan 2,95 euron tullimaksu linkin kautta." '
     'Vastaa suomeksi JSON-muodossa {"action": "do_not_interact_and_delete" tai "verify_via_official_channel", "advice": "kaksi lyhyttä lausetta"}.'},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--model")
    a = ap.parse_args()
    if a.list:
        ids = llm.list_models()
        print(len(ids), "models")
        print("\n".join(ids))
        return
    t = time.time()
    text = llm.complete(PROMPT, model=a.model)
    print("latency %.1fs" % (time.time() - t))
    print(text)
    try:
        json.loads(text[text.index("{"):text.rindex("}") + 1])
        print("JSON: ok")
    except ValueError:
        print("JSON: FAILED")


if __name__ == "__main__":
    main()
