import { ShieldAlert } from "lucide-react";
import type { AnswerCard as Answer, RiskLevel } from "@/lib/chatService";

/** Badge colour per risk level (green = nothing to do, red = act now). */
const riskStyle: Record<RiskLevel, string> = {
  none: "bg-green-600",
  low: "bg-green-600",
  medium: "bg-yellow-500",
  high: "bg-orange-500",
  critical: "bg-red-600",
};

const urgencyText: Record<Answer["urgency"], string> = {
  none: "No action needed",
  routine: "When convenient",
  today: "Act today",
  immediate: "Act now",
};

/** Names of the data sources the assistant may have used, in plain language. */
const sourceLabel: Record<string, string> = {
  artifact: "the message or call you shared",
  link_check: "a link safety check",
  call_warning: "the network's call warning",
  user_call_notes: "your notes about the call",
  "subscription.products": "your subscriptions",
  "subscription.recent_events": "recent SIM/order events",
  "subscription.network_status": "network service status",
  "device.summary": "this device's basics",
  "device.recent_app_installs": "recently installed apps",
  "device.security_findings": "security app findings",
  "operator_account.recent_logins": "recent account logins",
  credential_exposure: "a breach check",
  "business.profile": "your company profile",
  "business.staff_accounts": "your company's user list",
};

/**
 * The structured part of a final answer: how serious it is, what to do, where the advice comes from,
 * and (only when the backend asks for it) a button to bring in a human.
 */
export function AnswerCard({
  answer,
  escalated,
  onEscalate,
}: {
  answer: Answer;
  escalated: boolean;
  onEscalate: () => void;
}) {
  return (
    <div className="mt-2 space-y-3 border-t border-border pt-2 text-xs text-muted-foreground">
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2 py-0.5 font-semibold text-white ${riskStyle[answer.riskLevel]}`}>
          Risk: {answer.riskLevel}
        </span>
        <span>{urgencyText[answer.urgency]}</span>
      </div>

      {answer.steps.length > 0 && (
        <ol className="list-decimal space-y-1 pl-4 text-foreground">
          {answer.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      )}

      {answer.escalationRequired && !escalated && (
        <button
          type="button"
          onClick={onEscalate}
          className="flex w-full items-center justify-center gap-2 rounded-full bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground"
        >
          <ShieldAlert className="h-4 w-4" />
          Hand over to a human
        </button>
      )}

      {/* Transparency: where the advice comes from and which data it used. */}
      {answer.citations.length > 0 && <p>Sources: {answer.citations.map((c) => c.title).join(" · ")}</p>}
      <p>Based on: {answer.signalsUsed.map((s) => sourceLabel[s] ?? s).join(", ") || "what you told me"}.</p>
      <p className="italic">{answer.disclaimer}</p>
    </div>
  );
}
