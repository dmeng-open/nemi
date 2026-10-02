import { Check, LoaderCircle, X } from "lucide-react";

import type { TimelineItem } from "@/types/api";

export function AgentTimeline({
  items,
  working = false,
}: {
  items: TimelineItem[];
  working?: boolean;
}) {
  return (
    <ol className="space-y-3" aria-label="Agent activity">
      {items.map((item) => {
        const active = item.status === "started";
        const failed = item.status === "failed";
        return (
          <li key={item.id} className="flex items-start gap-3 text-sm">
            <span
              className={
                failed
                  ? "mt-0.5 text-danger"
                  : active
                    ? "mt-0.5 text-accent"
                    : "mt-0.5 text-sage"
              }
            >
              {active ? (
                <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
              ) : failed ? (
                <X className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Check className="h-4 w-4" aria-hidden="true" />
              )}
            </span>
            <span className={failed ? "text-danger" : "text-ink"}>{item.label}</span>
          </li>
        );
      })}
      {working ? (
        <li className="flex items-center gap-3 text-sm text-muted">
          <LoaderCircle className="h-4 w-4 animate-spin" aria-hidden="true" />
          Working on your plan
        </li>
      ) : null}
    </ol>
  );
}
