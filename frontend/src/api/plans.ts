import { request } from "@/api/client";
import type { Plan, PlanSummary } from "@/types/api";

export function listPlans() {
  return request<PlanSummary[]>("/api/plans");
}

export function getPlan(planId: string) {
  return request<Plan>(`/api/plans/${planId}`);
}

export function createPlan(message: string) {
  return request<{ plan_id: string; status: string }>("/api/plans", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function clarifyPlan(planId: string, message: string) {
  return request<{ plan_id: string; status: string }>(`/api/plans/${planId}/clarify`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function continuePlan(planId: string) {
  return request<{ plan_id: string; status: string }>(`/api/plans/${planId}/continue`, {
    method: "POST",
  });
}

export function rejectCandidate(planId: string, candidateId: string) {
  return request<Plan>(`/api/plans/${planId}/reject`, {
    method: "POST",
    body: JSON.stringify({ candidate_id: candidateId }),
  });
}

export function selectCandidate(planId: string, candidateId: string) {
  return request<Plan>(`/api/plans/${planId}/select`, {
    method: "POST",
    body: JSON.stringify({ candidate_id: candidateId }),
  });
}

export function clearSelection(planId: string) {
  return request<Plan>(`/api/plans/${planId}/selection`, { method: "DELETE" });
}

export function approvePlan(planId: string, approved: boolean) {
  return request<Plan>(`/api/plans/${planId}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved }),
  });
}
