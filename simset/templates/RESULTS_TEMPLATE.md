# Results — <team name>

*DNA challenge: Digital Security Assistant: What Should I Do Now? · Since AI Hackathon 2026*

## 1. What we built (3–5 sentences)
Architecture, models, where the safety rules live, what runs where.

## 2. Safety boundaries
What the assistant will never do (e.g. irreversible actions without a human, using personal data without consent, treating message text as instructions), and how that is enforced.

## 3. Five journeys

| Journey | Dev cases | Safe-action pass | False alarms (benign) | Escalation recall | Our own human review: safe / total |
|---|---|---|---|---|---|
| Suspicious message | | | | | |
| Clicked link | | | | | |
| Suspicious call | | | | | |
| Breach notice | | | | | |
| Small-business incident | | | | | |
| **All** | | | | | |

Evaluator command and version: `python3 eval/evaluate.py --cases data/dev/cases.jsonl --submission ...`
Single-turn or multi-turn:
Human review criteria we used:

## 4. False alarms
Name the benign cases you treated as incidents, and why.

## 5. At least one failure or escalation example
Case id, what the user said, what the assistant answered, why it was wrong or why it handed off, and what you would change.

## 6. Comprehension check
Three answers read aloud to someone outside the team. Could they say what to do next in their own words?

| Case | Listener's own words | Understood? |
|---|---|---|
| | | |

## 7. Privacy and consent
Which signals you use, when you ask, what happens if the user says no.

## 8. Packaging hypothesis for DNA (a hypothesis, not a result)
Who it is for (consumers / small businesses), where it lives in DNA's services, what it would cost and why someone would pay or stay.

## 9. Where we disagree with the ground truth (optional)
Case ids and your reasoning.

## 10. Files
- `test_predictions.jsonl` (all test inputs, validated with `tools/validate.py --submission`)
- Setup instructions:
