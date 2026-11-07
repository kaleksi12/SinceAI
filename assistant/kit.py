"""Single access point to the organisers' kit in simset/.

Everything we use from the kit is imported here, so it is easy to see (and to keep in sync with
PROVENANCE.md) which parts of our code depend on organiser-supplied material.
"""
import json
import sys
from pathlib import Path

SIMSET = Path(__file__).resolve().parent.parent / "simset"
if str(SIMSET) not in sys.path:  # the kit's packages (dsakit, baselines) import as top-level names
    sys.path.insert(0, str(SIMSET))

from baselines import rules_baseline as baseline  # noqa: E402  (fallback templates, question wording, citation map)
from dsakit import textcheck  # noqa: E402  (unsafe-claim, step, language and jargon checks)
from dsakit.simulator import VISIBLE_KEYS, reveal_signals, visible_case  # noqa: E402  (what a bot may see; consent reveal)

_guidance = None


def ref(name):
    """Load one of the kit's reference vocabularies (data/reference/<name>)."""
    return textcheck.load_ref(name)


def guidance():
    """The 55-passage guidance corpus (Finnish and English; every passage is marked official=false)."""
    global _guidance
    if _guidance is None:
        with open(SIMSET / "data" / "reference" / "guidance_corpus.jsonl", encoding="utf-8") as f:
            _guidance = [json.loads(line) for line in f if line.strip()]
    return _guidance


def samples():
    """The five hand-picked sample cases, one per journey."""
    with open(SIMSET / "data" / "samples" / "five_journeys.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def dev_cases():
    """All dev cases (with ground truth: never send it anywhere)."""
    with open(SIMSET / "data" / "dev" / "cases.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def visible(case):
    """Only the fields a test input has: no labels, simulation facts, family or tags."""
    return {k: case[k] for k in VISIBLE_KEYS if k in case}
