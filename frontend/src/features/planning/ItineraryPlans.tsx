import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatClock } from "@/lib/format";
import type { AgentProgress, ExecutionAction, Itinerary } from "@/types/api";

export function ItineraryPlans({
  itineraries,
  agents,
  timeZone,
  busy = false,
  status,
  executionActions = [],
  resolution,
  parallelSpeedup,
  onApprove,
  onRevise,
  onRetry,
  onKeep,
  onCancelCreated,
}: {
  itineraries: Itinerary[];
  agents: AgentProgress[];
  timeZone: string;
  busy?: boolean;
  status: string;
  executionActions?: ExecutionAction[];
  resolution?: string | null;
  parallelSpeedup?: number | null;
  onApprove: (itineraryId: string) => void;
  onRevise: (message: string) => void;
  onRetry: () => void;
  onKeep: () => void;
  onCancelCreated: () => void;
}) {
  const [revision, setRevision] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const cost = agents.reduce((sum, agent) => sum + (agent.estimated_cost_usd || 0), 0);
  const waiting = status === "awaiting_approval";
  const partial = status === "partial_success" && resolution !== "kept";

  return (
    <div className="space-y-4">
      {itineraries.map((plan, index) => (
        <article key={plan.id} className="rounded-3xl border border-line bg-surface p-6 shadow-[var(--shadow)]">
          <p className="text-xs uppercase tracking-[0.14em] text-muted">Plan {String.fromCharCode(65 + index)}</p>
          <ol className="mt-4 space-y-3">
            {plan.items.map((item) => (
              <li key={`${item.item_type}-${item.start}-${item.title}`} className="grid grid-cols-[88px_1fr] gap-3 text-sm">
                <time className="text-muted" dateTime={item.start}>
                  {formatClock(item.start, timeZone)}
                </time>
                <span>
                  <span className="block font-medium">{item.title}</span>
                  {item.travel_time_is_estimate ? (
                    <span className="text-muted">Estimated travel, not a routed trip.</span>
                  ) : null}
                  {item.location ? <span className="block text-muted">{item.location}</span> : null}
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-4 text-sm">Estimated total ${Math.round(plan.estimated_total_cost)}</p>
          {plan.explanation ? <p className="mt-2 text-sm leading-6 text-muted">{plan.explanation}</p> : null}
          <ul className="mt-4 flex flex-wrap gap-2" aria-label="Constraint checks">
            {plan.checks.map((check) => (
              <li
                key={check.code}
                className={
                  check.status === "fail"
                    ? "rounded-full border border-danger/40 px-3 py-1 text-xs text-danger"
                    : check.status === "soft"
                      ? "rounded-full border border-line px-3 py-1 text-xs text-muted"
                      : "rounded-full border border-sage/40 px-3 py-1 text-xs text-sage"
                }
              >
                {check.label} {check.status === "pass" ? "✓" : check.status === "soft" ? "·" : "×"} {check.message}
              </li>
            ))}
          </ul>
          {waiting ? (
            <Button className="mt-5" type="button" disabled={busy} onClick={() => onApprove(plan.id)}>
              Approve & add to calendar
            </Button>
          ) : null}
        </article>
      ))}

      {waiting ? (
        <form
          className="rounded-3xl border border-line bg-surface p-6"
          onSubmit={(event) => {
            event.preventDefault();
            if (revision.trim()) onRevise(revision.trim());
          }}
        >
          <h2 className="font-serif text-2xl">Change this plan</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {["Make this cheaper", "Find a different restaurant", "Replace the activity", "Finish earlier"].map(
              (label) => (
                <button
                  key={label}
                  type="button"
                  className="rounded-full border border-line px-3 py-1 text-sm"
                  onClick={() => setRevision(label)}
                >
                  {label}
                </button>
              ),
            )}
          </div>
          <label className="mt-4 block">
            <span className="sr-only">Revision</span>
            <input
              value={revision}
              onChange={(event) => setRevision(event.target.value)}
              className="w-full rounded-2xl border border-line bg-bg px-4 py-3"
              placeholder="Make this cheaper"
            />
          </label>
          <Button className="mt-4" type="submit" variant="quiet" disabled={busy || !revision.trim()}>
            Update the plan
          </Button>
        </form>
      ) : null}

      {partial ? (
        <section className="rounded-3xl border border-line bg-surface p-6" aria-labelledby="partial-schedule">
          <h2 id="partial-schedule" className="font-serif text-2xl">
            Part of the schedule was saved
          </h2>
          <ul className="mt-3 space-y-2 text-sm">
            {executionActions.map((action) => (
              <li key={action.item_id}>
                {action.title}: {action.status === "completed" ? "added" : "not added"}
              </li>
            ))}
          </ul>
          <div className="mt-4 flex flex-wrap gap-3">
            <Button type="button" disabled={busy} onClick={onRetry}>
              Retry remaining
            </Button>
            <Button type="button" variant="quiet" disabled={busy} onClick={onKeep}>
              Keep partial schedule
            </Button>
            {confirmCancel ? (
              <Button type="button" variant="danger" disabled={busy} onClick={onCancelCreated}>
                Remove the events I added
              </Button>
            ) : (
              <Button type="button" variant="danger" disabled={busy} onClick={() => setConfirmCancel(true)}>
                Cancel created events
              </Button>
            )}
          </div>
        </section>
      ) : null}

      <details className="rounded-3xl border border-line bg-surface px-5 py-4 text-sm">
        <summary className="cursor-pointer">Developer trace</summary>
        <p className="mt-3 text-muted">
          Estimated model cost ${cost.toFixed(4)}
          {parallelSpeedup ? ` · parallel research speedup ${parallelSpeedup.toFixed(2)}×` : ""}
        </p>
        <ul className="mt-3 space-y-2">
          {agents.map((agent) => (
            <li key={agent.agent}>
              <span className="font-medium">{agent.label}</span>
              <span className="text-muted">
                {" "}
                {agent.status}
                {agent.duration_ms != null ? ` · ${agent.duration_ms} ms` : ""}
                {agent.model ? ` · ${agent.model}` : ""}
                {agent.tool_calls.length ? ` · ${agent.tool_calls.join(", ")}` : ""}
              </span>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
