/**
 * Chat API service.
 *
 * This module is the single boundary between the chat UI and the bot backend.
 * It currently returns hardcoded mock responses after a 1-second delay.
 * Swap the internals of sendMessageToBot for a real HTTP call to the Python
 * backend later — the UI only depends on the BotResponse shape.
 */

export interface ChatState {
  /** True once a high-risk threat has been flagged in this conversation. */
  highRisk: boolean;
  /** True once the conversation has been escalated to a human agent. */
  escalated: boolean;
}

export interface BotResponse {
  text: string;
  /** True when the bot detects a high-risk threat in the user's message. */
  highRisk: boolean;
}

const highRiskKeywords = [
  "scam",
  "fraud",
  "password",
  "phishing",
  "suspicious link",
  "bank credentials",
  "huijaus",
  "salasana",
];

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

export async function sendMessageToBot(message: string, _state: ChatState): Promise<BotResponse> {
  // Simulate network latency
  await delay(1000);

  const highRisk = highRiskKeywords.some((kw) => message.toLowerCase().includes(kw));

  if (highRisk) {
    return {
      text: "This message looks suspicious. Do not reply to it or share any personal information. If you like, I can escalate the case to a human specialist.",
      highRisk: true,
    };
  }

  return {
    text: "Thanks for your message! I'm processing your request and will get back to you shortly.",
    highRisk: false,
  };
}
