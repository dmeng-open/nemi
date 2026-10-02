import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { getIntegrations } from "@/api/integrations";
import { approvePlan, clarifyPlan, clearSelection, createPlan, getPlan, selectCandidate } from "@/api/plans";
import { PlanWorkspace } from "@/features/planning/PlanWorkspace";
import type { Candidate } from "@/types/api";

export function PlanPage() {
  const { planId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
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
  const timeZone = integrations.data?.timezone ?? "America/Chicago";

  function refresh() {
    return queryClient.invalidateQueries({ queryKey: ["plan", planId] });
  }

  const action = useMutation({
    mutationFn: async (work: () => Promise<unknown>) => work(),
    onSuccess: () => refresh(),
  });

  if (planQuery.isLoading) {
    return <p className="text-sm text-muted">Opening your plan…</p>;
  }
  if (planQuery.isError || !planQuery.data) {
    const message =
      planQuery.error instanceof ApiError ? planQuery.error.message : "That plan could not be found.";
    return (
      <p className="text-sm text-danger" role="alert">
        {message}
      </p>
    );
  }

  const plan = planQuery.data;
  return (
    <div>
      {action.isError ? (
        <p className="mb-4 text-sm text-danger" role="alert">
          {action.error instanceof ApiError ? action.error.message : "That action failed."}
        </p>
      ) : null}
      <PlanWorkspace
        plan={plan}
        timeZone={timeZone}
        busy={action.isPending}
        onClarify={(message) => action.mutate(() => clarifyPlan(plan.plan_id, message))}
        onChoose={(candidate: Candidate) => action.mutate(() => selectCandidate(plan.plan_id, candidate.id))}
        onCancel={() => action.mutate(() => clearSelection(plan.plan_id))}
        onApprove={() => action.mutate(() => approvePlan(plan.plan_id, true))}
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
