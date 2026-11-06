# Build report — v2.0.1 (2026-11-04)

| Item | Value |
|---|---|
| Dev cases | 588 (54 twin pairs, 132 benign) |
| Test inputs | 335 (answers held by organisers) |
| Scenario families | 58 (9 test-only) |
| Guidance passages | 55 (fi + en) |
| Vocabularies | 10 actions, 38 steps, 23 unsafe claims, 18 question topics, 14 signals |
| User languages | fi 61 %, en 33 %, sv 6 % |

## QA gates (all passed)

- Reference-answer gate: every reference answer (fi and en) of every case contains all of its required steps and none of its unsafe statements, as detected by the published patterns.
- Schema validation of every dev case and test input (`schema/`).
- Twin integrity: both cases of each twin pair have identical visible input and different branches.
- Leakage: test inputs carry no ground truth, simulation facts, family ids, titles or tags; no hold-out family appears in dev; the generator is not shipped.
- Reserved domains only; no live links.
- 22 unit tests (`python3 -m unittest discover -s tests`).
- Determinism: two independent builds produce byte-identical data.
- Clean-room run from the ZIP with `python3 -I`: validate, baselines, evaluator, multi-turn harness (Python and Node bots), unit tests.
- Oracle check: a single-turn oracle built from the ground truth scores ≥ 98 % safe-action pass; always-benign and always-escalate score low.
- Gaming probes on the rules baseline (same decisions, different form): listing every question topic, stuffing step phrases, omitting privacy fields and empty advice all lower the weighted proxy. Self-reported privacy fields (claiming no signals, blanket consent) can move it by up to about 4 points, which is why judges confirm consent behaviour in demos.
- Independent reviews (technical/adversarial and content/safety/language) were done before release; their findings were fixed and all checks re-run.

`tools/validate.py` output (before the manifest was written):

```
data: 588 dev cases, 335 test inputs, 54 twin groups in dev
OK
```

## Baselines (dev split)

| Baseline | Safe-action pass | False alarms on benign | Escalation recall | Asked decisive question | Required-step coverage | Weighted proxy |
|---|---|---|---|---|---|---|
| Always 'no action needed' | 26.5 % (23.1–30.1) | 0.0 % | 0.0 % | 0.0 % | 25.0 % | 48.8 |
| Always 'escalate to a human' | 0.0 % (0.0–0.0) | 100.0 % | 100.0 % | 0.0 % | 7.0 % | 39.5 |
| Rules baseline, single-turn | 60.5 % (57.0–64.5) | 28.0 % | 47.0 % | 70.0 % | 60.0 % | 67.1 |
| Rules baseline, multi-turn with simulated user | 65.3 % (61.6–69.0) | 28.0 % | 53.9 % | 65.0 % | 63.5 % | 69.1 |

95 % bootstrap intervals in brackets. Multi-turn is stricter for twins: the final answer must match the branch the user is actually in.

## Not done / limits

- No calibration against real DNA, operator or incident data (by design: none was provided or used).
- No LLM baseline is included; teams' own model-based systems are the comparison that matters.
- Text checks are heuristics; implementation (20 % of the brief) is never automated.
- Swedish reference answers are not provided.
