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
| `requirements.txt` | Python dependencies: fastapi, uvicorn, openai (only as an OpenAI-compatible HTTP client), python-dotenv |
| `assistant/__init__.py` | Empty package for our code |
| `assistant/llm.py` | OpenAI-compatible client (Featherless) with an on-disk response cache in `.llm_cache/`; switches off hidden "thinking" for Qwen3.5+ models and never caches empty replies |
| `scripts/smoke_llm.py` | Lists models and tests key, JSON output and Finnish quality for one model |
| `assistant/rules.py` | Safety envelope R1-R12: yes/no/unknown facts -> forced action, risk floor, escalation, questions to ask. Rules derived from patterns in the dev set; vocabularies (actions, topics, escalation targets) are the kit's |
| `tests/test_rules.py` | Unit tests for the rules |
| `assistant/dialogue.py` | Live-chat engine: one `step(event, state)` function in the kit's multi-turn bot protocol (usable with the kit's `run_conversation.py` and by the API). Asks consent once, asks at most 2 questions, then answers; consent labels and texts in fi/en/sv are ours |
| `assistant/api.py` | FastAPI app for the web demo: `/api/health`, `/api/scenarios` (free text plus the kit's five sample journeys), `/api/chat`, `/api/escalate` (simulated handoff) |
| `tests/test_dialogue.py` | Unit tests for the dialogue engine and the API, with the LLM stubbed |
| `assistant/kit.py` | The one place that imports the organisers' kit (textcheck, baseline templates, vocabularies, guidance corpus, sample journeys, `visible_case` / `reveal_signals` from the simulator) |
| `assistant/prompts.py` | Analysis and writer prompts. The analysis GUIDELINES block is the winner of a prompt-optimization run (see `optimization/`). Step lists per action come from dev ground-truth frequencies; action, step, claim and jargon texts come from the kit |
| `assistant/bot.py` | Decision pipeline shared by single-turn and live chat: LLM analysis -> rules -> LLM wording -> validation (kit `textcheck` unsafe-claim, step, language and jargon checks) -> retry -> kit template fallback |
| `scripts/run_single.py` | Runs the bot over a cases file (optionally a seeded sample), single-turn or `--mode multi` (our dialogue engine against the kit's simulated user, using the kit's `run_conversation.py` harness unchanged), into a new `runs/<timestamp>_<label>/` folder: predictions, the kit's evaluate.py report (json and text), the kit's validate.py result, the kit baseline's predictions and report on the same cases, and run_meta.json. Calls the kit scripts unchanged as subprocesses |
| `scripts/compare_runs.py` | Prints several run folders side by side (reads the kit evaluator's `report.json` files) with the kit baseline |
| `scripts/optimize_prompt.py` | Prompt optimization of the analysis guidelines, a small re-implementation of the method in Pryzant et al. 2023 (arXiv:2305.03495; authors' MIT-licensed code at github.com/microsoft/LMOps, not copied). Scores decisions with the kit's `scoring.score_case`, splits dev cases by scenario family so validation families are never seen during optimization |
| `PROVENANCE.md` | This file |
| `README.md` | Created by the team on GitHub (placeholder for now) |

## Frontend (`frontend/`)
Generated with Lovable (TanStack Start, React, Tailwind, shadcn/Radix UI) and added by a teammate; the UI components in `frontend/src/components/ui/` and the Lovable support files (`routeTree.gen.ts`, error capture, config) are unchanged. We changed:
| Path | Change |
|---|---|
| `frontend/src/lib/chatService.ts` | Was a keyword-matching mock; now the typed client for `/api/chat`, `/api/scenarios` and `/api/escalate` |
| `frontend/src/routes/index.tsx` | Chat page rewritten: scenario picker, consent card, answer card, escalation, new-conversation button, errors. The mock conversation and the unsupported attachment upload are gone |
| `frontend/src/components/chat/AnswerCard.tsx`, `ConsentCard.tsx` | New: risk/steps/sources/escalation card and the Allow / Not now consent card |
| `frontend/src/components/chat/DebugPanel.tsx` | New: debug view that shows the raw JSON of every backend request and response (including the backend's `debug` object) instead of the chat bubbles; toggled with the bug icon in the header |
| `frontend/vite.config.ts` | Added a dev proxy from `/api` to the backend on port 8000 |
| `.gitignore` | Ignores `node_modules`, build output and `frontend/package-lock.json` (the project uses `bun.lock`) |

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

## Prompt optimization outputs
| Path | Purpose |
|---|---|
| `optimization/<timestamp>_<label>/` | One folder per optimizer run: config (family split), log of every critique and candidate score, all candidate prompts, baseline and best guidelines, validation results. Generated by `scripts/optimize_prompt.py`; the best guidelines are only applied to `assistant/prompts.py` after human review |
