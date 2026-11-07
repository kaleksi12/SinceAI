import { createFileRoute } from "@tanstack/react-router";
import { ArrowLeft, Bug, House, LayoutGrid, FileText, Ticket, Ellipsis, SendHorizontal, Paperclip, LoaderCircle, RotateCcw } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { AnswerCard } from "@/components/chat/AnswerCard";
import { ConsentCard } from "@/components/chat/ConsentCard";
import { DebugPanel } from "@/components/chat/DebugPanel";
import {
  ChatError,
  escalate,
  getScenarios,
  onExchange,
  sendConsent,
  sendMessage,
  type AnswerCard as AnswerData,
  type BotResponse,
  type ConsentField,
  type Exchange,
  type Scenario,
} from "@/lib/chatService";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Security Assistant" },
      { name: "description", content: "Security Assistant – your mobile security helper." },
      { property: "og:title", content: "Security Assistant" },
      { property: "og:description", content: "Security Assistant – your mobile security helper." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Index,
});

// The bottom navigation only dresses the page up as an operator app; none of it is wired to anything.
const navItems = [
  { label: "Home", icon: House },
  { label: "Services", icon: LayoutGrid },
  { label: "Bills", icon: FileText },
  { label: "Benefits", icon: Ticket },
  { label: "More", icon: Ellipsis },
];

/** One bubble in the conversation. Optional parts render extra cards under the text. */
type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
  /** Final advice: risk badge, steps, sources, escalation button. */
  answer?: AnswerData | undefined;
  /** A consent request; `choice` is set once the user has answered it. */
  consent?: { fields: ConsentField[]; choice?: "granted" | "refused" | undefined } | undefined;
  /** What was shared with a human agent after an escalation. */
  handoff?: Record<string, unknown> | undefined;
};

const greeting: ChatMessage = {
  id: 0,
  role: "assistant",
  text: "Hi! I'm your Security Assistant. Describe what happened (a message, a call, a link you opened, a payment…) and I'll tell you what to do next. You can write in Finnish, English or Swedish.",
};

function Index() {
  const [messages, setMessages] = useState<ChatMessage[]>([greeting]);
  const [draft, setDraft] = useState("");
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Set after the first reply; its presence means "a conversation is in progress".
  const [sessionId, setSessionId] = useState<string | undefined>();
  const [escalated, setEscalated] = useState(false);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [scenarioId, setScenarioId] = useState("free_consumer");
  // Debug view: show the raw JSON exchanged with the backend instead of the chat bubbles.
  const [debug, setDebug] = useState(false);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const nextId = useRef(1);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Load the demo starting points once. Failure is fine: free text still works.
  useEffect(() => {
    getScenarios().then(setScenarios).catch(() => undefined);
  }, []);

  // Collect every backend exchange (also while the debug view is off, so switching it on shows the whole history).
  useEffect(() => onExchange((e) => setExchanges((prev) => (e.url === "/api/scenarios" ? prev : [...prev, e]))), []);

  // Keep the newest message in view.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, exchanges, debug, waiting]);

  const scenario = scenarios.find((s) => s.id === scenarioId);
  // While a consent question is open the user must answer it with the buttons.
  const consentOpen = messages.some((m) => m.consent && !m.consent.choice);
  // The debug view has no bubbles, so the buttons that need a click are shown separately.
  const pendingConsent = messages.find((m) => m.consent && !m.consent.choice);
  const escalationOffered = messages.some((m) => m.answer?.escalationRequired);

  const push = (msg: Omit<ChatMessage, "id">) => setMessages((prev) => [...prev, { ...msg, id: nextId.current++ }]);

  /** Show the backend's reply as an assistant bubble (with a consent or answer card when it has one). */
  const showReply = (reply: BotResponse) => {
    setSessionId(reply.sessionId);
    push({
      role: "assistant",
      text: reply.text,
      answer: reply.type === "answer" ? reply.answer : undefined,
      consent: reply.type === "consent_request" ? { fields: reply.fields } : undefined,
    });
  };

  /** Run a backend call with the shared waiting / error handling. */
  const run = async (call: () => Promise<void>) => {
    setWaiting(true);
    setError(null);
    try {
      await call();
    } catch (e) {
      setError(e instanceof ChatError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setWaiting(false);
    }
  };

  const onScenarioChange = (id: string) => {
    setScenarioId(id);
    // A sample journey prefills its example message (editable); free text clears the box.
    setDraft(scenarios.find((s) => s.id === id)?.openingMessage ?? "");
  };

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || waiting || consentOpen) return;
    push({ role: "user", text });
    setDraft("");
    await run(async () => {
      showReply(
        await sendMessage({
          sessionId,
          message: text,
          // The scenario and audience only matter for the first message of a conversation.
          scenarioId: sessionId ? undefined : scenarioId,
          audience: sessionId ? undefined : (scenario?.audience ?? "consumer"),
        }),
      );
    });
  };

  const onConsent = async (messageId: number, fields: ConsentField[], granted: boolean) => {
    if (!sessionId) return;
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId && m.consent ? { ...m, consent: { ...m.consent, choice: granted ? "granted" : "refused" } } : m)),
    );
    const paths = fields.map((f) => f.path);
    await run(async () => {
      showReply(await sendConsent(sessionId, granted ? paths : [], granted ? [] : paths));
    });
  };

  const onEscalate = async () => {
    if (!sessionId) return;
    await run(async () => {
      const result = await escalate(sessionId);
      setEscalated(true);
      push({ role: "assistant", text: result.text, handoff: result.summary });
    });
  };

  const reset = () => {
    setMessages([greeting]);
    setExchanges([]);
    setSessionId(undefined);
    setEscalated(false);
    setError(null);
    setDraft(scenario?.openingMessage ?? "");
  };

  return (
    <div className="mx-auto flex h-screen max-w-md flex-col bg-background">
      <header className="sticky top-0 z-10 flex h-14 shrink-0 items-center gap-6 bg-primary px-4 text-primary-foreground">
        <button aria-label="Back" onClick={() => history.back()} className="p-1">
          <ArrowLeft className="h-6 w-6" />
        </button>
        <h1 className="font-display flex-1 text-xl font-bold">Security Assistant</h1>
        <button
          aria-label="Debug view"
          aria-pressed={debug}
          title={debug ? "Back to the chat view" : "Show the JSON objects instead of the messages"}
          onClick={() => setDebug((d) => !d)}
          className={`rounded p-1 ${debug ? "bg-primary-foreground text-primary" : ""}`}
        >
          <Bug className="h-5 w-5" />
        </button>
        <button aria-label="New conversation" title="New conversation" onClick={reset} className="p-1">
          <RotateCcw className="h-5 w-5" />
        </button>
      </header>

      <main className="flex min-h-0 flex-1 flex-col bg-content">
        {/* Demo helper: pick a sample journey (it carries sensitive signals so the consent flow can be shown) or free text. */}
        {!sessionId && (
          <div className="border-b border-border bg-background px-4 py-2 text-xs text-muted-foreground">
            <label className="flex items-center gap-2">
              Start from
              <select
                value={scenarioId}
                onChange={(e) => onScenarioChange(e.target.value)}
                className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1 text-foreground"
              >
                {(scenarios.length ? scenarios : [{ id: "free_consumer", label: "Free text: consumer" }]).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {debug && (
            <div className="space-y-3">
              <DebugPanel exchanges={exchanges} />
              {pendingConsent?.consent && (
                <div className="rounded-lg border border-border bg-background p-2 text-xs">
                  <p className="whitespace-pre-line text-foreground">{pendingConsent.text}</p>
                  <ConsentCard
                    fields={pendingConsent.consent.fields}
                    choice={pendingConsent.consent.choice}
                    disabled={waiting}
                    onAnswer={(granted) => onConsent(pendingConsent.id, pendingConsent.consent!.fields, granted)}
                  />
                </div>
              )}
              {escalationOffered && !escalated && (
                <button
                  type="button"
                  onClick={onEscalate}
                  className="w-full rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground"
                >
                  Hand over to a human
                </button>
              )}
            </div>
          )}
          {!debug && messages.map((msg) => (
            <div
              key={msg.id}
              className={
                msg.role === "user"
                  ? "ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-sm border border-border bg-background px-4 py-2.5 text-sm text-foreground"
                  : "mr-auto w-fit max-w-[85%] rounded-2xl rounded-bl-sm bg-chat-assistant px-4 py-2.5 text-sm text-foreground"
              }
            >
              {/* whitespace-pre-line keeps the line breaks the backend puts before follow-up questions. */}
              <p className="whitespace-pre-line">{msg.text}</p>
              {msg.consent && (
                <ConsentCard
                  fields={msg.consent.fields}
                  choice={msg.consent.choice}
                  disabled={waiting}
                  onAnswer={(granted) => onConsent(msg.id, msg.consent!.fields, granted)}
                />
              )}
              {msg.answer && <AnswerCard answer={msg.answer} escalated={escalated} onEscalate={onEscalate} />}
              {msg.handoff && (
                <details className="mt-2 text-xs text-muted-foreground">
                  <summary className="cursor-pointer">What was shared with the agent</summary>
                  <pre className="mt-1 whitespace-pre-wrap break-words">{JSON.stringify(msg.handoff, null, 2)}</pre>
                </details>
              )}
            </div>
          ))}
          {waiting && (
            <div className="mr-auto flex w-fit items-center gap-2 rounded-2xl rounded-bl-sm bg-chat-assistant px-4 py-2.5 text-sm text-muted-foreground">
              <LoaderCircle className="h-4 w-4 animate-spin" />
              Thinking...
            </div>
          )}
          {error && (
            <p role="alert" className="rounded-lg border border-destructive/40 bg-background px-3 py-2 text-xs text-destructive">
              {error}
            </p>
          )}
          <div ref={bottomRef} />
        </div>

        <form onSubmit={onSend} className="sticky bottom-0 bg-content p-3">
          <div className="flex items-center gap-2 rounded-full border border-border bg-background py-1.5 pl-2 pr-1.5">
            {/* Attachments are not supported in this prototype (the assistant reads text only). */}
            <button
              type="button"
              disabled
              aria-label="Attachments are not supported in this prototype"
              title="Attachments are not supported in this prototype"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted-foreground opacity-40"
            >
              <Paperclip className="h-5 w-5" />
            </button>
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={consentOpen}
              maxLength={4000}
              placeholder={consentOpen ? "Please answer the question above" : "Type a message..."}
              aria-label="Type a message"
              className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            />
            <button
              type="submit"
              aria-label="Send"
              disabled={waiting || consentOpen || !draft.trim()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-primary disabled:opacity-40"
            >
              <SendHorizontal className="h-5 w-5" />
            </button>
          </div>
        </form>
      </main>

      <nav className="sticky bottom-0 grid shrink-0 grid-cols-5 border-t border-border bg-background pb-[env(safe-area-inset-bottom)]">
        {navItems.map(({ label, icon: Icon }) => (
          <button key={label} className="flex flex-col items-center gap-1 py-2 text-xs text-nav-foreground">
            <Icon className="h-6 w-6" strokeWidth={1.5} />
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}
