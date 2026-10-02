import { request } from "@/api/client";
import type { CalendarEvent } from "@/types/api";

export function listCalendarEvents() {
  return request<CalendarEvent[]>("/api/calendar/events");
}

export function createCalendarEvent(body: {
  title: string;
  start: string;
  end: string;
  location?: string;
  description?: string;
}) {
  return request<CalendarEvent>("/api/calendar/events", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function createSampleEvents() {
  return request<CalendarEvent[]>("/api/calendar/sample", { method: "POST" });
}

export function deleteCalendarEvent(id: string) {
  return request<void>(`/api/calendar/events/${id}`, { method: "DELETE" });
}
