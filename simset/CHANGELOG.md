# Changelog

## 2.0.1 — 2026-11-04
- Scorecard weights aligned with DNA's final brief (4 Nov 2026): correctness 25, clarity 20, uncertainty and escalation 20, working implementation and evidence 20, privacy and consent 15. The automated proxy now covers 80 of the 100 points.
- Scorecard keys in the JSON report renamed to weight-independent names (`correctness`, `clarity`, `uncertainty_escalation`, `privacy_consent`, `implementation`).
- DNA contact during the event: Micke Rantanen.
- No changes to the cases or their answers apart from the version field.

## 2.0.0 — 2026-11-03
Replaces v1.0.1. Not backward compatible in file layout; v1 submission fields are still accepted.

- 588 dev cases and 335 test inputs (was 55 cases, all with answers). Test answers held by the organisers.
- 58 scenario families (was 18); 9 families appear only in test.
- Signals are generated from each scenario instead of at random (v1 could say "I installed an app" with an empty app list).
- Realistic signal noise, distractor signals, withheld signals and prompt-injection text.
- Twin cases: identical input, different right answer, decided by one fact only the user knows.
- New benign look-alikes (own login prompt, booked remote support, verified supplier change, genuine bank call and notices).
- Simulated user and multi-turn harness (Python function or any language over JSON lines); consent-gated signals.
- Consent model: `consent.requires_consent`, `consent.pre_granted`; submissions report `signals_used`.
- Evaluator: stricter safe-action pass; scorecard mapped to the brief's weights; negation-aware unsafe-statement detection in Finnish, English and Swedish; step detection; clarity proxies; bootstrap confidence intervals; seen/unseen family split.
- Guidance corpus: 55 passages in Finnish and English (was 30, English).
- New actions: `decline_out_of_scope`. New fields: `urgency`, `escalation.acceptable_targets`, `single_turn`, `necessary_signals`, `reference_answer_fi/en`.
- Swedish-speaking users added.
- Build-time QA: every reference answer must pass its own case's step and unsafe-statement checks.
