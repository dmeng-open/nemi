import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { connectGoogleCalendar, getIntegrations } from "@/api/integrations";
import {
  approvePlan,
  clarifyPlan,
  clearSelection,
  commandExecution,
  continuePlan,
  createPlan,
  getPlan,
  rejectCandidate,
  revisePlan,
  selectCandidate,
} from "@/api/plans";
import { getPreferences } from "@/api/preferences";
import { PlanWorkspace } from "@/features/planning/PlanWorkspace";
import type { Candidate } from "@/types/api";

export function PlanPage() {
  const { planId = "" } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const queryClient = useQueryClient();
  const focusList = useRef(false);
  const planQuery = useQuery({
    queryKey: ["plan", planId],
    queryFn: () => getPlan(planId),
    enabled: Boolean(planId),
    refetchInterval: (query) => (query.state.data?.status === "processing" ? 1000 : false),
  });
  const integrations = useQuery({
    queryKey: ["integrations"],
    queryFn: getIntegrations,
  });
  const preferences = useQuery({
    queryKey: ["preferences"],
    queryFn: getPreferences,
  });
  const timeZone = preferences.data?.timezone || integrations.data?.timezone || "America/Chicago";

  function refresh() {
    return queryClient.invalidateQueries({ queryKey: ["plan", planId] });
  }

  const action = useMutation({
    mutationFn: async (work: () => Promise<unknown>) => work(),
    onSuccess: () => refresh(),
  });
  const plan = planQuery.data;

  useEffect(() => {
    if (!plan || !focusList.current || plan.status !== "awaiting_selection") return;
    focusList.current = false;
    document.getElementById("recommendation-list")?.focus();
  }, [plan]);

  if (planQuery.isLoading) {
    return <p className="text-sm text-muted">Opening your plan…</p>;
  }
  if (planQuery.isError || !plan) {
    const message =
      planQuery.error instanceof ApiError ? planQuery.error.message : "That plan could not be found.";
    return (
      <p className="text-sm text-danger" role="alert">
        {message}
      </p>
    );
  }

  return (
    <div>
      {params.get("calendar") === "connect_failed" ? (
        <p className="mb-4 text-sm text-danger" role="alert">
          Google Calendar was not connected.
        </p>
      ) : null}
      {action.isError ? (
        <p className="mb-4 text-sm text-danger" role="alert">
          {action.error instanceof ApiError ? action.error.message : "That action failed."}
        </p>
      ) : null}
      <PlanWorkspace
        plan={plan}
        timeZone={timeZone}
        busy={action.isPending}
        demoMode={integrations.data?.demo_mode === true}
        onClarify={(message) => action.mutate(() => clarifyPlan(plan.plan_id, message))}
        onChoose={(candidate: Candidate) => action.mutate(() => selectCandidate(plan.plan_id, candidate.id))}
        onReject={(candidate: Candidate) => {
          focusList.current = true;
          return action.mutate(() => rejectCandidate(plan.plan_id, candidate.id));
        }}
        onCancel={() => action.mutate(() => clearSelection(plan.plan_id))}
        onApprove={() => action.mutate(() => approvePlan(plan.plan_id, true))}
        onApproveItinerary={(itineraryId) =>
          action.mutate(() => approvePlan(plan.plan_id, true, itineraryId))
        }
        onRevise={(message) => action.mutate(() => revisePlan(plan.plan_id, message))}
        onRetryExecution={() => action.mutate(() => commandExecution(plan.plan_id, "retry"))}
        onKeepPartial={() => action.mutate(() => commandExecution(plan.plan_id, "keep"))}
        onCancelCreated={() => action.mutate(() => commandExecution(plan.plan_id, "cancel_created", true))}
        onContinue={() => action.mutate(() => continuePlan(plan.plan_id))}
        onConnect={() =>
          action.mutate(async () => {
            const started = await connectGoogleCalendar(`/plans/${plan.plan_id}`);
            window.location.assign(started.authorization_url);
          })
        }
        onRetry={() =>
          action.mutate(async () => {
            const created = await createPlan(plan.request);
            navigate(`/plans/${created.plan_id}`);
          })
        }
        onAnother={() => navigate("/")}
      />
    </div>
  );
}
