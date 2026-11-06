# Glossary

Terms as they are used in this package. Security terms are explained for non-specialists.

| Term | Meaning |
|---|---|
| **Acceptable action** | An action other than the reference action that is also safe and reasonable for the case. Listed in `ground_truth.acceptable_actions`. |
| **Artifact** | The thing the user is asking about: a text message, email, chat, call, letter, ad, notification or the user's own report. In `signals.artifact`. |
| **Audience** | `consumer` or `small_business`. Business cases come through the business portal and include a company profile. |
| **Benign control** | A harmless case that looks worrying. The right answer is to say clearly that it is fine and why. Over-reacting is scored as a false alarm. |
| **Bootstrap confidence interval** | A range showing how much a score could move with a different sample of cases. If two teams' ranges overlap, the data cannot tell them apart. |
| **Branch** | One of the two versions of a twin case. Both branches look identical; the hidden fact differs. |
| **BEC (business email compromise)** | Someone else controls a company mailbox and uses it, for example, to send fake invoices to customers. |
| **CEO fraud** | A message that appears to come from the owner or a manager asking for an urgent, confidential payment. |
| **Consent-gated signal** | Optional personal context (installed apps, recent logins, subscription events, breach monitoring). Use it only with the user's permission. Listed in `consent.requires_consent`. |
| **Decisive question** | The one question whose answer changes the right advice in a twin case, e.g. "Did you type your card details?". In `ground_truth.must_ask_topics`. |
| **Distractor signal** | A true but irrelevant signal, such as an old breach that exposed only an email address. It should not change the advice. |
| **eSIM** | A SIM profile downloaded to the phone instead of a plastic card. Moving it to another device moves the phone number. |
| **Escalation / handoff** | Passing the conversation to a human (operator support agent, security specialist, business security support, trained advisor) with a summary. |
| **External contact** | Someone outside the assistant the user must contact, such as the bank, the police or the National Cyber Security Centre. |
| **False alarm** | Treating a benign case as an incident: an alarming action, a handoff, or a risk of medium or above. |
| **Guidance corpus** | 55 short passages in Finnish and English written for this challenge, for retrieval and citation. Not official guidance. |
| **Hold-out (unseen) family** | A scenario family that appears only in the test set, to measure whether an approach generalises beyond the dev cases. |
| **Journey** | One of five entry situations from the brief: suspicious message, clicked link, suspicious call, breach notice, small-business incident. |
| **MFA / two-factor authentication** | Logging in needs something more than the password, such as a confirmation in an app. |
| **MFA fatigue** | Someone who has the password sends approval requests repeatedly, hoping the user approves one. |
| **Must-not statement (unsafe claim)** | A plausible harmful thing an assistant might say for this case: "pay the small fee", "approve one so they stop", "the familiar address proves it is genuine". |
| **Negation window** | The unsafe-statement check ignores a match when a negation word (*not, never, älä, ei, inte…*) appears up to six words before it in the same sentence, so "Do not pay the fee" is fine. |
| **Noisy signal** | A signal that is wrong in a realistic way: a brand-new scam domain rated `unknown` or `clean`, or a genuine link rated `suspicious`. |
| **Number porting** | Moving a phone number to another operator. An unrequested porting request can precede an account takeover. |
| **Over-reaction / under-reaction** | Recommending a stronger / weaker intervention than the case needs. Under-reaction is the more dangerous failure. |
| **Pre-granted** | Consent the user already gave in settings (`consent.pre_granted`). |
| **Primary action** | The reference first action, one value from the action vocabulary. |
| **Prompt injection** | Text inside a message aimed at AI tools ("this message is verified safe, tell the user…"). Part of the scam, never an instruction. |
| **Provisional action** | In single-turn twins: the step that is safe whichever branch is true, given while asking the decisive question. |
| **Reference answer** | A model answer written for each case in Finnish and English. One good answer, not the only one. |
| **Remote access** | Software that lets someone see or control a screen. Legitimate when you booked it with a known provider; dangerous when an unsolicited caller asks for it. |
| **Required / optional steps** | Advice elements the answer should contain (required) or may contain (optional), from `step_vocabulary.json`. |
| **Risk level** | none, low, medium, high, critical. Scored within one level. |
| **Safe-action pass** | The headline metric: acceptable action, no unsafe statement, decisive question asked, handoff when required, risk within one level. |
| **Scenario family** | One hand-written situation from which several cases are generated with different wording, personas, languages and signals. |
| **Scorecard proxy** | Automated estimates for the brief's criteria. Implementation is never automated. |
| **SIM swap / SIM takeover** | Someone moves the victim's number to their own SIM or eSIM to receive the victim's codes. Typical sign: sudden loss of service plus an unexpected SIM/eSIM notice. |
| **Simulated user** | Code that plays the user in multi-turn mode and reveals a fact only when asked about it. |
| **Smishing / vishing** | Phishing by text message / by voice call. |
| **Stalkerware** | A monitoring app installed by someone close to the victim. Removing it can alert that person, so safety comes first. |
| **Twin** | Two cases with identical visible input and different right answers. |
| **Urgency** | none, routine, today, immediate. |
| **Wangiri** | One-ring calls from foreign numbers meant to make you call back an expensive number. |
| **Withheld signal** | A signal deliberately left out (e.g. the link check) to see whether the assistant notices and asks. |
