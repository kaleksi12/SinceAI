# Data card — DNA Digital Security Assistant simulation set v2.0.1

## Motivation
Built by Since AI ry for the DNA challenge at Since AI Hackathon 2026 ("Digital Security Assistant: What Should I Do Now?"), so that teams can test whether an assistant gives safe, proportionate, understandable next steps to consumers and small businesses, asks only for what it needs, respects consent and hands off when it should. No DNA data was available or wanted.

## Composition
- 588 dev cases (ground truth, reference answers, simulation facts) and 335 test inputs (ground truth held by the organisers).
- 58 scenario families across five journeys; 9 families appear only in test.
- Twins: 54 pairs in dev with identical visible input and different right answers.
- Benign cases: 132 in dev (22 %).
- Languages of the user (dev + test): Finnish 61 %, English 33 %, Swedish 6 %. Scam texts are sometimes in a different language from the user's.
- Audiences (dev + test): consumer 69 %, small business 31 %.
- Test twins: only one branch of each twin group is in test, so twins cannot be spotted as duplicates.
- Each case: persona, opening message, artifact, simulated link check and call warning, subscription, device, operator-account and breach-monitoring signals, consent state, ground truth and, in dev, a simulated user.
- Guidance corpus: 55 passages, Finnish and English, `"official": false`.

## How it was made
Each family was written by hand: the situation, what the user received, how users describe it, what they know, and the safety logic (risk, urgency, action, acceptable alternatives, handoff, required steps, unsafe statements, decisive question, rationale, reference answers). A deterministic generator varies wording, persona, slot values (fictional brands, amounts, numbers, domains), language and signals, adds realistic noise (unlisted scam domains, unflagged scam calls, false-positive link verdicts), distractors, withheld signals and prompt-injection text. Same seed, same bytes.

Every reference answer is checked automatically at build time: it must contain each required step and none of the case's unsafe statements, as detected by the published patterns.

## Intended use
Practice and self-evaluation during the hackathon; a shared yardstick for judges, alongside human review and live testing.

## Not intended for
Training or validating a production security service; estimating real-world accuracy; evidence that any solution is safe. Ground truth is Since AI's reading of widely published consumer-safety practice, not an authority's ruling.

## Labelling rules worth knowing
- Unacted phishing: *medium* risk when the lure is a small payment or card details; *high* when it targets banking or identification credentials or a money transfer.
- Twins in single-turn: the expected action is one that is safe if the riskier hidden answer is true, plus the decisive question and the handoff the riskier branch needs.
- Device app lists and findings assume an optional operator security app on Android/Windows; they are null on iOS.
- Subscription events show the channel and how the requester was authenticated, never whether it was really the customer.

## Known limitations
- Generated variation around hand-written families: cases within a family are related; treat per-family results with caution.
- Text checks are regular expressions with known blind spots (paraphrase, unusual negation).
- The simulated user is literal and cooperative; it does not lie, forget or change topic.
- Swedish coverage is thin, and Swedish reference answers are not provided.
- Operator-side signals are invented plausible fields, not a description of any real system.

## Personal data and safety
No personal data. Names are common first names without surnames, attached to fictional situations. Organisation names are invented. Domains are reserved and cannot resolve. No malware, no working payloads, no real phishing pages.

## Licence and maintenance
Data and documentation CC BY 4.0, code MIT, © 2026 Since AI ry. Maintained by Since AI ry for the 2026 event. Report errors to riku.lauttia@sinceai.fi.
