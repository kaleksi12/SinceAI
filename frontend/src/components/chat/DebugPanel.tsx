import { useState } from "react";
import type { Exchange } from "@/lib/chatService";

/** Pretty-printed JSON, long enough values scroll instead of stretching the page. */
function Json({ value }: { value: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words rounded bg-muted p-2 text-[11px] leading-snug text-foreground">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

/**
 * Debug view: shows the raw JSON of every request and response exchanged with the backend, newest last,
 * instead of the chat bubbles. The response also carries a "debug" object (what the LLM extracted, which rules
 * fired, consent state), which the backend only includes because the client asks for it.
 */
export function DebugPanel({ exchanges }: { exchanges: Exchange[] }) {
  const [copied, setCopied] = useState(false);

  const copyAll = async () => {
    await navigator.clipboard.writeText(JSON.stringify(exchanges, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (exchanges.length === 0) {
    return <p className="text-xs text-muted-foreground">No backend exchanges yet. Send a message to see the JSON objects here.</p>;
  }

  return (
    <div className="space-y-3 text-xs">
      <button type="button" onClick={copyAll} className="rounded-full border border-border bg-background px-3 py-1 font-semibold text-foreground">
        {copied ? "Copied" : "Copy all as JSON"}
      </button>
      {exchanges.map((e, i) => (
        <section key={e.id} className="rounded-lg border border-border bg-background p-2">
          <h2 className="font-semibold text-foreground">
            #{i + 1} {e.method} {e.url}{" "}
            <span className={e.status === 200 ? "text-green-700" : "text-destructive"}>{e.status || "no connection"}</span>{" "}
            <span className="font-normal text-muted-foreground">
              {e.time} · {(e.ms / 1000).toFixed(1)} s
            </span>
          </h2>
          {e.request !== null && (
            <details className="mt-1">
              <summary className="cursor-pointer text-muted-foreground">Request</summary>
              <Json value={e.request} />
            </details>
          )}
          <details open className="mt-1">
            <summary className="cursor-pointer text-muted-foreground">Response</summary>
            <Json value={e.response} />
          </details>
        </section>
      ))}
    </div>
  );
}
