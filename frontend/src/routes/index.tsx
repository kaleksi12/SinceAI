import { createFileRoute } from "@tanstack/react-router";
import { ArrowLeft, House, LayoutGrid, FileText, Ticket, Ellipsis, SendHorizontal, Paperclip, ShieldAlert, LoaderCircle } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";
import { sendMessageToBot, type ChatState } from "@/lib/chatService";

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

const navItems = [
  { label: "Home", icon: House },
  { label: "Services", icon: LayoutGrid },
  { label: "Bills", icon: FileText },
  { label: "Benefits", icon: Ticket },
  { label: "More", icon: Ellipsis },
];

type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  text: string;
};

const initialMessages: ChatMessage[] = [
  { id: 1, role: "assistant", text: "Hi! I'm your Security Assistant. How can I help you today?" },
  { id: 2, role: "user", text: "I got a suspicious email, what should I do?" },
  { id: 3, role: "assistant", text: "Good question! Don't click any links or download attachments. Can you tell me more about the email — for example, who it claims to be from?" },
];

function Index() {
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [draft, setDraft] = useState("");
  const [chatState, setChatState] = useState<ChatState>({ highRisk: false, escalated: false });
  const [waiting, setWaiting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sendMessage = async (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || waiting) return;
    setMessages((prev) => [...prev, { id: Date.now(), role: "user", text }]);
    setDraft("");
    setWaiting(true);
    try {
      const reply = await sendMessageToBot(text, chatState);
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: "assistant", text: reply.text }]);
      if (reply.highRisk) {
        setChatState((prev) => ({ ...prev, highRisk: true, escalated: false }));
      }
    } finally {
      setWaiting(false);
    }
  };

  const escalate = () => {
    setChatState((prev) => ({ ...prev, escalated: true }));
    setMessages((prev) => [
      ...prev,
      { id: Date.now(), role: "assistant", text: "Your case has been escalated to a human specialist. We will contact you soon." },
    ]);
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col bg-background">
      <header className="sticky top-0 z-10 flex h-14 items-center gap-6 bg-primary px-4 text-primary-foreground">
        <button aria-label="Back" onClick={() => history.back()} className="p-1">
          <ArrowLeft className="h-6 w-6" />
        </button>
        <h1 className="font-display text-xl font-bold">Security Assistant</h1>
      </header>

      <main className="flex min-h-0 flex-1 flex-col bg-content">
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={
                msg.role === "user"
                  ? "ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-sm border border-border bg-background px-4 py-2.5 text-sm text-foreground"
                  : "mr-auto w-fit max-w-[80%] rounded-2xl rounded-bl-sm bg-chat-assistant px-4 py-2.5 text-sm text-foreground"
              }
            >
              {msg.text}
            </div>
          ))}
          {waiting && (
            <div className="mr-auto flex w-fit items-center gap-2 rounded-2xl rounded-bl-sm bg-chat-assistant px-4 py-2.5 text-sm text-muted-foreground">
              <LoaderCircle className="h-4 w-4 animate-spin" />
              Typing...
            </div>
          )}
        </div>

        {chatState.highRisk && !chatState.escalated && (
          <div className="px-3 pb-2">
            <button
              onClick={escalate}
              className="flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground"
            >
              <ShieldAlert className="h-5 w-5" />
              Escalate to Human Agent
            </button>
          </div>
        )}

        <form onSubmit={sendMessage} className="sticky bottom-0 bg-content p-3">
          <div className="flex items-center gap-2 rounded-full border border-border bg-background py-1.5 pl-2 pr-1.5">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              aria-hidden="true"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) {
                  setMessages((prev) => [
                    ...prev,
                    { id: Date.now(), role: "user", text: `📎 Attachment: ${file.name}` },
                  ]);
                }
                e.target.value = "";
              }}
            />
            <button
              type="button"
              aria-label="Add attachment"
              onClick={() => fileInputRef.current?.click()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted-foreground"
            >
              <Paperclip className="h-5 w-5" />
            </button>
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Type a message..."
              aria-label="Type a message"
              className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
            />
            <button
              type="submit"
              aria-label="Send"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-primary"
            >
              <SendHorizontal className="h-5 w-5" />
            </button>
          </div>
        </form>
      </main>

      <nav className="sticky bottom-0 grid grid-cols-5 border-t border-border bg-background pb-[env(safe-area-inset-bottom)]">
        {navItems.map(({ label, icon: Icon }) => (
          <button
            key={label}
            className="flex flex-col items-center gap-1 py-2 text-xs text-nav-foreground"
          >
            <Icon className="h-6 w-6" strokeWidth={1.5} />
            {label}
          </button>
        ))}
      </nav>
    </div>
  );
}
