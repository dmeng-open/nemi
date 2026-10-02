import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listPlans } from "@/api/plans";

const STATUS_LABEL: Record<string, string> = {
  processing: "Working",
  awaiting_clarification: "Needs a detail",
  awaiting_selection: "Ready to choose",
  awaiting_approval: "Waiting for approval",
  scheduled: "Scheduled",
  failed: "Failed",
  no_matches: "No match",
  cancelled: "Cancelled",
};

export function RecentPlansPage() {
  const query = useQuery({ queryKey: ["plans"], queryFn: listPlans });
  const plans = query.data ?? [];

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-serif text-4xl">Recent plans</h1>
      <p className="mt-3 text-sm text-muted">These stay here after you refresh.</p>
      {query.isLoading ? <p className="mt-8 text-sm text-muted">Loading plans…</p> : null}
      {query.isError ? (
        <p className="mt-8 text-sm text-danger" role="alert">
          Could not load your plans.
        </p>
      ) : null}
      {!query.isLoading && plans.length === 0 ? (
        <div className="mt-8 rounded-3xl border border-dashed border-line p-8">
          <p className="font-serif text-2xl">No plans yet</p>
          <p className="mt-2 text-sm text-muted">Start with a Saturday afternoon or a Friday dinner.</p>
          <Link className="mt-4 inline-flex text-sm text-accent" to="/">
            New plan
          </Link>
        </div>
      ) : null}
      <ul className="mt-6 space-y-3">
        {plans.map((plan) => (
          <li key={plan.plan_id}>
            <Link
              to={`/plans/${plan.plan_id}`}
              className="block rounded-3xl border border-line bg-surface px-5 py-4 hover:border-accent"
            >
              <p className="text-xs text-muted">{STATUS_LABEL[plan.status] ?? plan.status}</p>
              <p className="mt-1 line-clamp-2">{plan.request}</p>
              {plan.selected_title ? <p className="mt-2 text-sm text-sage">{plan.selected_title}</p> : null}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
