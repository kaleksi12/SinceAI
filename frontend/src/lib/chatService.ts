/**
 * Chat API client: the single boundary between the chat UI and the Python backend (assistant/api.py).
 *
 * The backend decides everything (what to ask, whether consent is needed, what the advice is, whether a
 * human should be involved). The UI only sends what the user typed or clicked and renders the three reply types:
 *   - "question"        the assistant needs one more fact from the user
 *   - "consent_request" the assistant asks permission to look at optional, sensitive data
 *   - "answer"          the final advice, with risk, steps, sources and an escalation flag
 *
 * Requests go to relative /api URLs; vite.config.ts proxies them to the backend during development.
 */

export type Audience = "consumer" | "small_business";
export type RiskLevel = "none" | "low" | "medium" | "high" | "critical";

/** A demo starting point: free text, or one of the organisers' sample journeys (those carry sensitive signals). */
export interface Scenario {
  id: string;
  label: string;
  audience: Audience;
  language: string | null;
  openingMessage: string;
}

/** One optional data source the assistant asks permission to use. */
export interface ConsentField {
  path: string;
  /** Plain-language description in the user's language. */
  label: string;
}

export interface Citation {
  id: string;
  title: string;
}

/** The structured part of a final answer, shown as a card under the advice text. */
export interface AnswerCard {
  riskLevel: RiskLevel;
  urgency: "none" | "routine" | "today" | "immediate";
  primaryAction: string;
  steps: string[];
  /** True when the backend decided a human should be involved. */
  escalationRequired: boolean;
  escalationTarget: string | null;
  citations: Citation[];
  /** Which data sources the advice was based on (transparency for the user). */
  signalsUsed: string[];
  confidence: number;
  abstained: boolean;
  disclaimer: string;
}

export type BotResponse =
  | { type: "question"; sessionId: string; text: string }
  | { type: "consent_request"; sessionId: string; text: string; fields: ConsentField[] }
  | { type: "answer"; sessionId: string; text: string; answer: AnswerCard };

/** Result of handing the case to a (simulated) human agent. */
export interface EscalationResult {
  text: string;
  target: string;
  /** What is shared with the agent; shown to the user so the handoff is transparent. */
  summary: Record<string, unknown>;
}

/** An error with a message that is safe to show to the user. */
export class ChatError extends Error {}

/** One request/response pair with the backend, kept for the debug view. */
export interface Exchange {
  id: number;
  time: string;
  method: string;
  url: string;
  request: unknown;
  /** HTTP status; 0 means the backend could not be reached. */
  status: number;
  response: unknown;
  ms: number;
}

const exchangeListeners = new Set<(e: Exchange) => void>();
let nextExchangeId = 1;

/** Subscribe to every backend exchange (returns the unsubscribe function). */
export function onExchange(listener: (e: Exchange) => void): () => void {
  exchangeListeners.add(listener);
  return () => exchangeListeners.delete(listener);
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const started = performance.now();
  const record = (status: number, response: unknown) => {
    let sent: unknown = null;
    try {
      sent = typeof init?.body === "string" ? JSON.parse(init.body) : null;
    } catch {
      sent = init?.body ?? null;
    }
    const exchange: Exchange = {
      id: nextExchangeId++,
      time: new Date().toLocaleTimeString(),
      method: init?.method ?? "GET",
      url,
      request: sent,
      status,
      response,
      ms: Math.round(performance.now() - started),
    };
    exchangeListeners.forEach((listener) => listener(exchange));
  };

  let res: Response;
  try {
    res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    record(0, { error: "Cannot reach the backend" });
    throw new ChatError("Cannot reach the assistant. Is the backend running?");
  }
  // Read the body once as text so it can be both shown in the debug view and parsed.
  const raw = await res.text();
  let body: unknown = raw;
  try {
    body = JSON.parse(raw);
  } catch {
    /* keep the raw text */
  }
  record(res.status, body);
  if (!res.ok) {
    // FastAPI sends {"detail": "..."} for errors we raise on purpose.
    const detail = (body as { detail?: unknown } | null)?.detail;
    throw new ChatError(typeof detail === "string" ? detail : `Request failed (${res.status}).`);
  }
  return body as T;
}

/* The backend uses snake_case; these types mirror its JSON and are converted to the camelCase types above. */
type RawAnswer = {
  risk_level: RiskLevel;
  urgency: AnswerCard["urgency"];
  primary_action: string;
  steps: string[];
  escalation_required: boolean;
  escalation_target: string | null;
  citations: Citation[];
  signals_used: string[];
  confidence: number;
  abstained: boolean;
  disclaimer: string;
};
type RawResponse = {
  session_id: string;
  type: BotResponse["type"];
  text: string;
  consent_request?: { fields: ConsentField[] };
  answer?: RawAnswer;
};

function toBotResponse(raw: RawResponse): BotResponse {
  const base = { sessionId: raw.session_id, text: raw.text };
  if (raw.type === "consent_request") return { type: "consent_request", ...base, fields: raw.consent_request?.fields ?? [] };
  if (raw.type === "answer" && raw.answer) {
    const a = raw.answer;
    return {
      type: "answer",
      ...base,
      answer: {
        riskLevel: a.risk_level,
        urgency: a.urgency,
        primaryAction: a.primary_action,
        steps: a.steps,
        escalationRequired: a.escalation_required,
        escalationTarget: a.escalation_target,
        citations: a.citations,
        signalsUsed: a.signals_used,
        confidence: a.confidence,
        abstained: a.abstained,
        disclaimer: a.disclaimer,
      },
    };
  }
  return { type: "question", ...base };
}

/** The demo starting points offered in the scenario picker. */
export async function getScenarios(): Promise<Scenario[]> {
  const raw = await request<
    { id: string; label: string; audience: Audience; language: string | null; opening_message: string }[]
  >("/api/scenarios");
  return raw.map((s) => ({ id: s.id, label: s.label, audience: s.audience, language: s.language, openingMessage: s.opening_message }));
}

/**
 * Send one user message.
 * Without sessionId this starts a conversation (scenarioId / audience then apply); with it, the message answers the
 * assistant's last question or adds more detail.
 */
export async function sendMessage(args: {
  sessionId?: string | undefined;
  message: string;
  scenarioId?: string | undefined;
  audience?: Audience | undefined;
}): Promise<BotResponse> {
  const raw = await request<RawResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({
      session_id: args.sessionId,
      message: args.message,
      scenario_id: args.scenarioId,
      audience: args.audience,
      debug: true, // the backend then also returns its internals, which the debug view shows
    }),
  });
  return toBotResponse(raw);
}

/** Answer a consent request: which of the asked-for data sources the user allows and which they refuse. */
export async function sendConsent(sessionId: string, granted: string[], refused: string[]): Promise<BotResponse> {
  const raw = await request<RawResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ session_id: sessionId, consent: { granted, refused }, debug: true }),
  });
  return toBotResponse(raw);
}

/** Hand the conversation to a (simulated) human agent. */
export async function escalate(sessionId: string): Promise<EscalationResult> {
  return request<EscalationResult>("/api/escalate", { method: "POST", body: JSON.stringify({ session_id: sessionId }) });
}
