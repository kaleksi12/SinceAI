# SinceAI: Digital Security Assistant

Our entry to the DNA x Since AI 2026 challenge: an assistant inside a telecom operator's app that helps consumers and small businesses
with suspicious messages, calls, clicked links, breach notices and business incidents. It picks a safe action, a risk level and a
handoff to a human when needed, asks for consent before looking at private signals, and answers in Finnish, English or Swedish.

## How it works

1. **Analysis (LLM):** reads the user's words and visible signals and fills in yes/no/unknown facts (was a code shared, was money sent, ...).
2. **Safety rules (code, `assistant/rules.py`):** turn those facts into limits: a forced action, a minimum risk, escalation and the questions still worth asking.
3. **Writer (LLM) and checks:** writes the advice for the decided action; the kit's text checks reject unsafe claims, jargon and wrong language, with a template fallback.

The same pipeline serves the single-turn submission and the live chat (`assistant/bot.py`, `assistant/dialogue.py`).
`simset/` is the organisers' kit (data, evaluator, simulator). It is used as is and must not be edited.

## Setup

**Requirements:** Python 3 (developed on 3.12) and [Bun](https://bun.sh) (or npm) for the frontend.

Next, install the required Python libraries and create your ```.env``` file, to which you'll add your Featherless API key: 

```bash
pip install -r requirements.txt
cp .env.example .env          # then set FEATHERLESS_API_KEY (and optionally LLM_MODEL)
```

## Run the app

```bash
python3 -m uvicorn assistant.api:app --reload --port 8000     # backend
cd frontend && bun install && bun run dev          # frontend (npm install / npm run dev also works)
```

Open `http://localhost:8080/`. The frontend forwards `/api/...` calls to the backend on port 8000.

Each run writes its own folder under `runs/` (predictions, kit report, validation, baseline). The submission file is `test_predictions.jsonl`;
check it with `python3 simset/tools/validate.py --submission test_predictions.jsonl --cases simset/data/test/inputs.jsonl`.

Latest full dev run (588 cases, single-turn): 80.8% safe-action.
