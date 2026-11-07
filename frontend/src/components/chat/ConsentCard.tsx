import type { ConsentField } from "@/lib/chatService";

/**
 * Asks the user for permission before the assistant looks at optional, sensitive data.
 * "Allow" grants every listed field, "Not now" refuses them all (the assistant must then advise without them).
 * Once answered, the buttons are replaced by the user's choice so the history stays readable.
 */
export function ConsentCard({
  fields,
  choice,
  disabled,
  onAnswer,
}: {
  fields: ConsentField[];
  /** undefined while the question is open. */
  choice?: "granted" | "refused" | undefined;
  disabled: boolean;
  onAnswer: (granted: boolean) => void;
}) {
  return (
    <div className="mt-2 space-y-2 border-t border-border pt-2 text-xs">
      <ul className="list-disc space-y-0.5 pl-4 text-muted-foreground">
        {fields.map((f) => (
          <li key={f.path}>{f.label}</li>
        ))}
      </ul>
      {choice ? (
        <p className="font-semibold text-foreground">{choice === "granted" ? "You allowed this." : "You declined."}</p>
      ) : (
        <div className="flex gap-2">
          <button
            type="button"
            disabled={disabled}
            onClick={() => onAnswer(true)}
            className="flex-1 rounded-full bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground disabled:opacity-50"
          >
            Allow
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => onAnswer(false)}
            className="flex-1 rounded-full border border-border bg-background px-3 py-2 text-sm font-semibold text-foreground disabled:opacity-50"
          >
            Not now
          </button>
        </div>
      )}
    </div>
  );
}
