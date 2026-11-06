"""Single access point to the organisers' kit in simset/."""
import json
import sys
from pathlib import Path

SIMSET = Path(__file__).resolve().parent.parent / "simset"
if str(SIMSET) not in sys.path:
    sys.path.insert(0, str(SIMSET))

from baselines import rules_baseline as baseline  # noqa: E402
from dsakit import textcheck  # noqa: E402
from dsakit.simulator import VISIBLE_KEYS  # noqa: E402

_guidance = None


def ref(name):
    return textcheck.load_ref(name)


def guidance():
    global _guidance
    if _guidance is None:
        with open(SIMSET / "data" / "reference" / "guidance_corpus.jsonl", encoding="utf-8") as f:
            _guidance = [json.loads(line) for line in f if line.strip()]
    return _guidance


def visible(case):
    """Only the fields a test input has: no labels, simulation facts, family or tags."""
    return {k: case[k] for k in VISIBLE_KEYS if k in case}
