// Minimal bot in Node.js speaking the JSON-lines protocol of sim/run_conversation.py.
//   python3 sim/run_conversation.py --cases data/dev/cases.jsonl --bot "node examples/minimal_bot.js" --out mt.jsonl --limit 10 --show
// Reads one JSON event per line on stdin, writes one JSON reply per line on stdout.
// Replace decide() with your own logic or a call to your model/service.
const readline = require("readline");
const rl = readline.createInterface({ input: process.stdin });
let state = {};

function decide(c, facts) {
  const lang = c.language || "fi";
  const asked = Object.keys(facts);
  if (c.journey === "suspicious_call" && !asked.includes("code_shared")) {
    return { type: "question", topics: ["code_shared"],
      text: { fi: "Kerroitko soittajalle jonkin koodin?", en: "Did you give the caller any code?", sv: "Gav du uppringaren någon kod?" }[lang] };
  }
  const gave = /luin|read him|yes|joo|läste/i.test(facts.code_shared || "");
  const answer = gave
    ? { primary_action: "contact_bank_and_block_cards", risk_level: "critical",
        advice_text: lang === "fi" ? "Soita heti pankkiisi kortissa olevaan numeroon ja pyydä sulkemaan tunnukset." : "Call your bank now on the number on your card and ask them to block your credentials." }
    : { primary_action: "verify_via_official_channel", risk_level: "medium",
        advice_text: lang === "fi" ? "Älä soita takaisin. Tarkista asia itse pankin omasta sovelluksesta." : "Do not call back. Check the matter yourself in the bank's own app." };
  return { type: "final", answer: Object.assign(answer, { escalation_required: false, signals_used: ["artifact", "call_warning"],
    consent_requested_for: [], question_topics: asked, confidence: 0.5 }) };
}

rl.on("line", (line) => {
  const ev = JSON.parse(line);
  if (ev.type === "start") state = { case: ev.case, facts: {}, last: null };
  else if (ev.type === "user_reply" && state.last) state.facts[state.last] = ev.text;
  let reply = decide(state.case, state.facts);
  if (ev.type === "turn_limit" && reply.type !== "final") reply = { type: "final", answer: { primary_action: "escalate_to_human", risk_level: "medium", advice_text: "", escalation_required: true } };
  if (reply.type === "question") state.last = reply.topics[0];
  process.stdout.write(JSON.stringify(reply) + "\n");
});
