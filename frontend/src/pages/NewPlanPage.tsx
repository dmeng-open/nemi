import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { createPlan } from "@/api/plans";
import { Composer } from "@/features/planning/Composer";

export function NewPlanPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: createPlan,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["plans"] });
      navigate(`/plans/${result.plan_id}`);
    },
  });

  return (
    <div className="pt-6 md:pt-16">
      <Composer pending={mutation.isPending} onSubmit={(message) => mutation.mutate(message)} />
      {mutation.isError ? (
        <p className="mx-auto mt-6 max-w-2xl text-sm text-danger" role="alert">
          {mutation.error instanceof ApiError
            ? mutation.error.message
            : "The planning request failed."}
        </p>
      ) : null}
    </div>
  );
}
