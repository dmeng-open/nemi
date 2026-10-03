import { Check, LoaderCircle, X } from "lucide-react";

import type { AgentProgress } from "@/types/api";

export function AgentBoard({ agents }: { agents: AgentProgress[] }) {
  return (
    <ol className="space-y-3" aria-label="Planning progress">
      {agents.map((agent) => {
        const waiting = agent.status === "waiting";
        const failed = agent.status === "failed";
        const active = agent.status === "running" || agent.status === "started";
        return (
          <li key={agent.agent} className="flex items-start gap-3 text-sm">
            <span
              className={
                failed ? "mt-0.5 text-danger" : waiting || active ? "mt-0.5 text-accent" : "mt-0.5 text-sage"
              }
            >
              {active || waiting ? (
                <LoaderCircle className={`h-4 w-4 ${active ? "animate-spin" : ""}`} aria-hidden="true" />
              ) : failed ? (
                <X className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Check className="h-4 w-4" aria-hidden="true" />
              )}
            </span>
            <span>
              <span className="block font-medium">{agent.label}</span>
              <span className={failed ? "text-danger" : "text-muted"}>{agent.detail ?? agent.status}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
