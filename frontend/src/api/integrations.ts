import { request } from "@/api/client";
import type { Integrations } from "@/types/api";

export function getIntegrations() {
  return request<Integrations>("/api/integrations");
}
