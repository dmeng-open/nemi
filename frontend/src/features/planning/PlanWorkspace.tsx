import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { AgentTimeline } from "@/features/planning/AgentTimeline";
import { CandidateCard } from "@/features/planning/CandidateCard";
import { Confirmation, SuccessState } from "@/features/planning/Confirmation";
import { formatDay, formatRange } from "@/lib/format";
import type { Candidate, Plan } from "@/types/api";

export function PlanWorkspace({
  plan,
  timeZone,
  busy = false,
  demoMode = false,
  onClarify,
  onChoose,
  onReject,
  onCancel,
  onApprove,
  onContinue,
  onConnect,
  onRetry,
  onAnother,
}: {
  plan: Plan;
  timeZone: string;
  busy?: boolean;
  demoMode?: boolean;
  onClarify: (message: string) => void;
  onChoose: (candidate: Candidate) => void;
  onReject?: (candidate: Candidate) => void;
  onCancel: () => void;
  onApprove: () => void;
  onContinue?: () => void;
  onConnect?: () => void;
  onRetry: () => void;
  onAnother: () => void;
}) {
  const [clarification, setClarification] = useState("");
  const selected =
    plan.recommendations.find((item) => item.id === plan.selected_candidate_id) ?? null;
  const reduceMotion = useReducedMotion();
  const working = plan.status === "processing";
  const disconnected =
    plan.status === "awaiting_approval" && plan.error?.code === "calendar_not_connected";
  const showCards =
    plan.status === "awaiting_selection" ||
    (plan.status === "no_matches" && plan.recommendations.length > 0) ||
    disconnected;
  const icsHref =
    plan.calendar?.ics_available && plan.status === "awaiting_approval"
      ? `/api/plans/${plan.plan_id}/ics`
      : null;

  return (
    <div className="grid gap-8 lg:grid-cols-[280px_1fr]">
      <div>
        <p className="text-sm text-muted">Your request</p>
        <p className="mt-2 text-sm leading-6">{plan.request}</p>
        {plan.summary ? <p className="mt-3 text-sm text-muted">{plan.summary}</p> : null}
        <div className="mt-6">
          <AgentTimeline items={plan.timeline} working={working} />
        </div>
      </div>
      <motion.div
        className="space-y-4"
        initial={reduceMotion ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: reduceMotion ? 0 : 0.25 }}
      >
        {plan.status === "awaiting_clarification" ? (
          <form
            className="rounded-3xl border border-line bg-surface p-6"
            onSubmit={(event) => {
              event.preventDefault();
              if (clarification.trim()) onClarify(clarification.trim());
            }}
          >
            <h2 className="font-serif text-3xl">One detail</h2>
            <p className="mt-3 text-sm leading-6">{plan.clarification_question}</p>
            <label className="mt-4 block">
              <span className="sr-only">Clarification</span>
              <input
                value={clarification}
                onChange={(event) => setClarification(event.target.value)}
                className="w-full rounded-2xl border border-line bg-bg px-4 py-3"
              />
            </label>
            <Button className="mt-4" type="submit" disabled={busy || !clarification.trim()}>
              Continue
            </Button>
          </form>
        ) : null}

        {plan.status === "awaiting_location" ? (
          <section className="rounded-3xl border border-line bg-surface p-6" aria-labelledby="location-needed">
            <h2 id="location-needed" className="font-serif text-3xl">
              Location needed
            </h2>
            <p className="mt-3 text-sm leading-6">
              {plan.error?.message ?? "Save a location in Preferences, then continue this plan."}
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <Link
                className="inline-flex h-11 items-center rounded-full border border-line px-5 text-sm"
                to="/preferences"
              >
                Preferences
              </Link>
              <Button type="button" onClick={onContinue} disabled={busy || !onContinue}>
                Continue this plan
              </Button>
            </div>
          </section>
        ) : null}

        {plan.status === "awaiting_approval" && selected ? (
          <Confirmation
            candidate={selected}
            timeZone={timeZone}
            error={plan.error?.message}
            pending={busy}
            icsHref={icsHref}
            onCancel={onCancel}
            onApprove={onApprove}
            onConnect={disconnected ? onConnect : undefined}
          />
        ) : null}

        {plan.status === "scheduled" && plan.execution ? (
          <SuccessState
            title={plan.execution.title}
            when={formatDay(plan.execution.start, timeZone)}
            hours={formatRange(plan.execution.start, plan.execution.end, timeZone)}
            downloadHref={`/api/plans/${plan.plan_id}/ics`}
            onAnother={onAnother}
          />
        ) : null}

        {plan.status === "failed" || plan.status === "no_matches" ? (
          <div className="rounded-3xl border border-line bg-surface p-6" role="alert">
            <h2 className="font-serif text-3xl">Nothing to schedule yet</h2>
            <p className="mt-3 text-sm leading-6 text-muted">
              {plan.error?.message ?? "The planning request failed."}
            </p>
            <Button className="mt-4" type="button" variant="quiet" onClick={onRetry}>
              Try again
            </Button>
          </div>
        ) : null}

        {demoMode && showCards ? (
          <p className="text-sm text-muted">Showing demo recommendations.</p>
        ) : null}

        {showCards ? (
          <div id="recommendation-list" tabIndex={-1} className="grid gap-4 outline-none">
            {plan.recommendations.map((candidate) => (
              <CandidateCard
                key={candidate.id}
                candidate={candidate}
                timeZone={timeZone}
                pending={busy}
                onChoose={onChoose}
                onReject={plan.status === "awaiting_selection" ? onReject : undefined}
              />
            ))}
          </div>
        ) : null}

        {plan.status === "cancelled" ? (
          <div className="rounded-3xl border border-line bg-surface p-6">
            <h2 className="font-serif text-3xl">Plan cancelled</h2>
            <p className="mt-3 text-sm text-muted">Nothing was added to your calendar.</p>
            <Button className="mt-4" type="button" variant="quiet" onClick={onAnother}>
              Start another plan
            </Button>
          </div>
        ) : null}
      </motion.div>
    </div>
  );
}
