import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createSampleEvents, deleteCalendarEvent, listCalendarEvents } from "@/api/calendar";
import { getIntegrations } from "@/api/integrations";
import { Button } from "@/components/ui/button";
import { formatDay, formatRange } from "@/lib/format";

export function IntegrationsPage() {
  const queryClient = useQueryClient();
  const integrations = useQuery({ queryKey: ["integrations"], queryFn: getIntegrations });
  const events = useQuery({ queryKey: ["calendar"], queryFn: listCalendarEvents });
  const timeZone = integrations.data?.timezone ?? "America/Chicago";
  const sample = useMutation({
    mutationFn: createSampleEvents,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["calendar"] }),
  });
  const remove = useMutation({
    mutationFn: deleteCalendarEvent,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["calendar"] }),
  });

  const providers = integrations.data
    ? [integrations.data.event_provider, integrations.data.place_provider, integrations.data.calendar_provider]
    : [];

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-serif text-4xl">Integrations</h1>
      <p className="mt-3 text-sm leading-6 text-muted">
        V0 keeps the world local. Ticketmaster, Google Places, and Google Calendar can replace these providers later
        without changing the planner.
      </p>
      <ul className="mt-6 space-y-3">
        {providers.map((provider) => (
          <li key={provider.key + provider.label} className="rounded-3xl border border-line bg-surface px-5 py-4">
            <div className="flex items-center justify-between gap-3">
              <p className="font-medium">{provider.label}</p>
              <p className="text-xs text-sage">{provider.status === "ready" ? "Ready" : "Unavailable"}</p>
            </div>
            <p className="mt-2 text-sm text-muted">{provider.detail}</p>
          </li>
        ))}
        <li className="rounded-3xl border border-line bg-surface px-5 py-4">
          <p className="font-medium">OpenAI</p>
          <p className="mt-2 text-sm text-muted">
            {integrations.data?.openai_configured
              ? "A key is configured. Nemi will use it to understand requests."
              : "Add OPENAI_API_KEY before asking Nemi to plan."}
          </p>
        </li>
      </ul>

      <section className="mt-10">
        <h2 className="font-serif text-2xl">Local calendar</h2>
        <p className="mt-2 text-sm text-muted">
          Travel times use a demo neighborhood. Sample Saturday plans help Nemi show a real conflict.
        </p>
        <Button className="mt-4" type="button" variant="quiet" onClick={() => sample.mutate()} disabled={sample.isPending}>
          Add sample Saturday
        </Button>
        <ul className="mt-4 space-y-2">
          {(events.data ?? []).map((event) => (
            <li key={event.id} className="flex items-center justify-between gap-3 rounded-2xl border border-line px-4 py-3">
              <div>
                <p>{event.title}</p>
                <p className="text-sm text-muted">
                  {formatDay(event.start, timeZone)} · {formatRange(event.start, event.end, timeZone)}
                </p>
              </div>
              <button
                type="button"
                className="text-sm text-danger"
                onClick={() => remove.mutate(event.id)}
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
        {events.data && events.data.length === 0 ? (
          <p className="mt-4 text-sm text-muted">Your local calendar is empty.</p>
        ) : null}
      </section>
    </div>
  );
}
