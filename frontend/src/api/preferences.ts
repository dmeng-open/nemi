import { request } from "@/api/client";
import type { Preferences } from "@/types/api";

export function getPreferences() {
  return request<Preferences>("/api/preferences");
}

export function updatePreferences(body: Preferences) {
  return request<Preferences>("/api/preferences", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
