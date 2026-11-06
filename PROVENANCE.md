# Provenance

What comes from the organisers and what we wrote. Updated with every change.

## From the organisers (Since AI ry, DNA challenge)
`simset/` is an unchanged copy of `DNA_Digital_Security_Assistant_SimSet_v2.0.1` (code MIT, data CC BY 4.0, see `simset/LICENSE`). We import and run it; we do not edit it.

| Path | What it is |
|---|---|
| `simset/data/dev`, `simset/data/test` | 588 dev cases with answers, 335 test inputs without |
| `simset/data/reference/` | Action, step, topic and unsafe-claim vocabularies, signal dictionary, 55-passage guidance corpus |
| `simset/eval/evaluate.py`, `simset/dsakit/` | Evaluator and its scoring and text-check logic |
| `simset/sim/` | Simulated user for multi-turn runs and its protocol |
| `simset/baselines/rules_baseline.py` | Keyword baseline to beat (templates reusable as fallback) |
| `simset/examples/`, `simset/schema/`, `simset/templates/`, `simset/tools/`, `simset/tests/` | Example bots, JSON schemas, results template, validator, tests |
| Brief (`DNA_x_SinceAI_2026_Challenge_Brief_EN_FINAL.*`) | Challenge description, outside this repo |

## Written by us
| Path | Purpose |
|---|---|
| `.gitignore` | Keeps `.env`, `out/` and caches out of git |
| `.gitattributes` | Leaves `simset/` bytes untouched so its `MANIFEST.json` checksums stay valid |
| `.env.example` | Template for the API key, base URL and model |
| `requirements.txt` | Python dependencies: fastapi, uvicorn, openai, python-dotenv |
| `assistant/__init__.py` | Empty package for our code |
| `assistant/llm.py` | OpenAI-compatible client (Featherless) with an on-disk response cache in `.llm_cache/` |
| `scripts/smoke_llm.py` | Lists models and tests key, JSON output and Finnish quality for one model |
| `assistant/rules.py` | Safety envelope R1-R12: yes/no/unknown facts -> forced action, risk floor, escalation, questions to ask. Rules derived from patterns in the dev set; vocabularies (actions, topics, escalation targets) are the kit's |
| `tests/test_rules.py` | 15 unit tests for the rules |
| `assistant/kit.py` | The one place that imports the organisers' kit (textcheck, baseline templates, vocabularies, guidance corpus) |
| `assistant/prompts.py` | Analysis and writer prompts. Step lists per action come from dev ground-truth frequencies; action, step, claim and jargon texts come from the kit |
| `assistant/bot.py` | Single-turn pipeline: LLM analysis -> rules -> LLM wording -> validation (kit `textcheck` unsafe-claim, step, language and jargon checks) -> retry -> kit template fallback |
| `scripts/run_single.py` | Runs the bot over a cases file (optionally a seeded sample) into a new `runs/<timestamp>_<label>/` folder: predictions, the kit's evaluate.py report (json and text), the kit's validate.py result, the kit baseline's predictions and report on the same cases, and run_meta.json. Calls the kit scripts unchanged as subprocesses |
| `PROVENANCE.md` | This file |
| `README.md` | Created by the team on GitHub (placeholder for now) |

## Generated (not committed)
| Path | Purpose |
|---|---|
| `out/baseline_dev.jsonl` | Baseline predictions on dev, used to reproduce the published numbers |
| `out/*.jsonl` | Scratch predictions from early runs (git-ignored, superseded by `runs/`) |
| `runs/<timestamp>_<label>/` | One folder per run (committed except `cases.jsonl`, which is a regenerable copy of kit cases). Reports inside are produced by the kit's `evaluate.py`; the predictions are ours |
| `.llm_cache/` | Cached LLM replies (git-ignored) |

## Third-party services
| Service | Role |
|---|---|
| Featherless.ai (open-weights models, OpenAI-compatible API) | LLM calls via `assistant/llm.py`; smoke-tested, first runs use `Qwen/Qwen3-30B-A3B-Instruct-2507` |
