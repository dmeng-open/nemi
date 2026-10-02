import { request } from "@/api/client";
import type { Integrations } from "@/types/api";

export function getIntegrations() {
  return request<Integrations>("/api/integrations");
}

export function connectGoogleCalendar(returnPath: string) {
  return request<{ authorization_url: string }>("/api/integrations/google/calendar/connect", {
    method: "POST",
    body: JSON.stringify({ return_path: returnPath }),
  });
}

export function disconnectGoogleCalendar() {
  return request<void>("/api/integrations/google/calendar/disconnect", { method: "DELETE" });
}
