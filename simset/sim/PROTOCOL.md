# Multi-turn protocol

`sim/run_conversation.py` plays the user. Your assistant ("bot") plays itself. One conversation per dev case.

## Plugging in

- **Any language:** `--bot "your command"`. The harness starts the command once and talks to it over stdin/stdout, one JSON object per line, one reply per event. Flush after every line.
- **Python:** `--bot-py path/to/file.py:step` where `step(event, state) -> reply`. `state` is a dict that persists through one conversation.

## Events (harness → bot)

| type | fields | meaning |
|---|---|---|
| `start` | `conversation_id`, `case`, `max_assistant_turns` | New conversation. `case` has exactly the fields of a test input (no ground truth, simulation facts, family, title, tags or difficulty), and consent-gated signals are replaced by the string `"available_with_consent"` unless pre-granted. |
| `user_reply` | `text` | The simulated user's answer to your last question. |
| `consent_reply` | `granted`, `refused`, `text`, `signals` | Answer to your consent request. `signals` maps each granted path to its value. |
| `turn_limit` | — | You used all turns. Reply with `final` now. |

## Replies (bot → harness)

| type | fields | meaning |
|---|---|---|
| `question` | `text`, optional `topics` | Ask the user one thing. `topics` (from `question_topics.json`) makes your intent explicit; otherwise the text is matched. |
| `consent_request` | `fields`, `text` | Ask permission to use signals, e.g. `["device.recent_app_installs"]`. Say what you will look at and why. |
| `final` | `answer` | Your answer, with the same fields as a single-turn submission. Ends the conversation. |

At most `max_assistant_turns` (default 6) questions and consent requests before `final`. A subprocess bot must answer each event within `--timeout` seconds (default 30). A bot that crashes, hangs or replies with something other than one JSON object is restarted, and that case is recorded as a missing answer.

## How the simulated user behaves

- It reveals a fact only when your question is about that fact's topic. It never volunteers.
- Ask about one thing at a time. A question with more than two `topics`, or whose text touches more than three topics, gets "could you ask one thing at a time?", reveals nothing and counts as an unnecessary question. A question that matches nothing gets "I'm not sure".
- It answers consent requests according to the case: most users agree, some refuse. If they refuse, still give useful advice without that data.
- It speaks the user's language (Finnish, English or Swedish).

## What gets recorded

The harness writes your final answer plus `mode: "multi_turn"`, the full `transcript` and a `conversation` summary: questions asked, unnecessary questions (topics that do not matter for the case), revealed topics, whether the decisive question was asked, and which consents were granted or refused. Using a consent-gated signal that was not granted, or was refused, is a consent violation.

## Minimal Python bot

```python
def step(event, state):
    if event["type"] == "start":
        state["case"] = event["case"]
        if state["case"]["journey"] == "clicked_link":
            return {"type": "question", "text": "Did you enter any card details on the page?", "topics": ["card_details_entered"]}
    answer = {"risk_level": "medium", "primary_action": "verify_via_official_channel",
              "advice_text": "Do not open the link. Check the matter in the service's own app.", "escalation_required": False}
    return {"type": "final", "answer": answer}
```

See `examples/python_bot.py` and `examples/minimal_bot.js` for complete minimal bots.
