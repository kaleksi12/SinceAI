# Results — Badger Squad

*DNA challenge: Digital Security Assistant: What Should I Do Now? · Since AI Hackathon 2026*

## 1. What we built (3–5 sentences)

Python scripts in ```assistant/``` contain the main logic of the assistant, as well as the Uvicorn/FastAPI server for the React frontend, which was built using Lovable.

The assistant can be tested against cases using ```scripts/run_single.py```, and results are stored in ```runs/```.

The chatbot runs DeepSeek-V3.1 through Featherless.

Dev files and dataset given by DNA are in ```simset/```.

## 2. Safety boundaries

The assistant will never:
- perform irreversible actions without a human, as it simply outputs text.
- use personal data tagged as requiring consent without asking it.


## 3. Five journeys

| Journey | Dev cases | Safe-action pass | False alarms (benign) | Escalation recall | Our own human review: safe / total |
|---|---|---|---|---|---|
| Suspicious message | 156 | 96.2% | | | |
| Clicked link | 84 | 71.4% | | | |
| Suspicious call | 72 | 91.7% | | | |
| Breach notice | 120 | 79.2% | | | |
| Small-business incident | 156 | 66.7% | | | |
| **All** | 588 | 80.2% | 9.6% | 96.2% | |

**Evaluator command and version:** `python3 simset/eval/evaluate.py --cases simset/data/dev/cases.jsonl --submission ...`

**Single-turn or multi-turn:** Single turn

**Human review criteria we used:** Sampling random predictions, we kept an eye out for any advice that seemed counter-intuitive, difficult to parse, overly long, or generally inconsistent with the rest.

## 4. False alarms

**DSA-D-0043:** A legitimate email still received the advice to verify the message from an official channel. A similar false alarm could be identified in several other cases.

## 5. At least one failure or escalation example

**DSA-D-0020:**  A small business case where the user asked "Asking on behalf of our company. What should I do with this?", regarding a phishing link. Instead of telling the user to change their password and escalate to a human, the assistant told the user to simply delete the message. This would allow breached credentials to be abused by attackers, while giving the user a false sense of security. The failure could be addressed through keyword-based rules as well as refinement of the system prompt.

## 6. Comprehension check
Three answers read aloud to someone outside the team. Could they say what to do next in their own words?

| Case | Listener's own words | Understood? |
|---|---|---|
| | | |

## 7. Privacy and consent

We use all the signals defined in pre-existing signal dictionary, and the assistant asks for consent deemed necessary by the language model. If the user clicks "Deny", the information is not used.

**NOTE:** The UI design does not sufficiently account for the privacy risks caused by dark patterns.

## 8. Packaging hypothesis for DNA (a hypothesis, not a result)
Ordinary consumers and small business owners can both access the assistant through either a DNA web portal or the My DNA mobile app, for example as part of the DNA Digiturva service.

## 9. Files
- `test_predictions.jsonl`
- Setup instructions: `README.md`
- Report `RESULTS.md`
