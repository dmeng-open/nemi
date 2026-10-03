import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { createSampleEvents, deleteCalendarEvent, listCalendarEvents } from "@/api/calendar";
import { connectGoogleCalendar, disconnectGoogleCalendar, getIntegrations } from "@/api/integrations";
import { Button } from "@/components/ui/button";
import { formatDay, formatRange } from "@/lib/format";
import type { ProviderStatus } from "@/types/api";

const CONNECTION_LABEL: Record<string, string> = {
  mock: "Mock",
  local: "Local",
  not_configured: "Not configured",
  configured: "Configured",
  oauth_required: "Not connected",
  connected: "Connected",
  unhealthy: "Unavailable",
};

export function IntegrationsPage() {
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
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
  const connect = useMutation({
    mutationFn: () => connectGoogleCalendar("/integrations"),
    onSuccess: (data) => {
      window.location.assign(data.authorization_url);
    },
  });
  const disconnect = useMutation({
    mutationFn: disconnectGoogleCalendar,
    onSuccess: async () => {
      setConfirmDisconnect(false);
      await queryClient.invalidateQueries({ queryKey: ["integrations"] });
    },
  });

  const providers = integrations.data
    ? [integrations.data.event_provider, integrations.data.place_provider, integrations.data.calendar_provider]
    : [];

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-serif text-4xl">Integrations</h1>
      <p className="mt-3 text-sm leading-6 text-muted">
        Mock events, mock restaurants, and the local calendar run with no API keys. Real providers turn on from the
        server environment, and Google Calendar also needs Connect.
      </p>
      {params.get("calendar") === "connect_failed" ? (
        <p className="mt-4 text-sm text-danger" role="alert">
          Google Calendar was not connected.
        </p>
      ) : null}
      <ul className="mt-6 space-y-3">
        {providers.map((provider) => (
          <li key={provider.mode + provider.label} className="rounded-3xl border border-line bg-surface px-5 py-4">
            <div className="flex items-center justify-between gap-3">
              <p className="font-medium">{provider.label}</p>
              <p className="text-xs text-sage">{CONNECTION_LABEL[provider.connection] ?? provider.connection}</p>
            </div>
            <p className="mt-2 text-sm text-muted">{provider.detail}</p>
            <ProviderActions
              provider={provider}
              confirmDisconnect={confirmDisconnect}
              connectPending={connect.isPending}
              disconnectPending={disconnect.isPending}
              onConnect={() => connect.mutate()}
              onAskDisconnect={() => setConfirmDisconnect(true)}
              onDisconnect={() => disconnect.mutate()}
              onKeep={() => setConfirmDisconnect(false)}
            />
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
          {integrations.data?.calendar_provider.mode === "google"
            ? "These rows are the local notebook. They are not Google busy time."
            : "Travel times use a demo neighborhood. Sample Saturday plans help Nemi show a real conflict."}
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

function ProviderActions({
  provider,
  confirmDisconnect,
  connectPending,
  disconnectPending,
  onConnect,
  onAskDisconnect,
  onDisconnect,
  onKeep,
}: {
  provider: ProviderStatus;
  confirmDisconnect: boolean;
  connectPending: boolean;
  disconnectPending: boolean;
  onConnect: () => void;
  onAskDisconnect: () => void;
  onDisconnect: () => void;
  onKeep: () => void;
}) {
  if (provider.connection === "oauth_required") {
    return (
      <Button className="mt-4" type="button" onClick={onConnect} disabled={connectPending}>
        {connectPending ? "Connecting…" : "Connect"}
      </Button>
    );
  }
  if (provider.connection !== "connected") return null;
  if (!confirmDisconnect) {
    return (
      <Button className="mt-4" type="button" variant="quiet" onClick={onAskDisconnect}>
        Disconnect
      </Button>
    );
  }
  return (
    <div className="mt-4" role="group" aria-label="Disconnect Google Calendar">
      <p className="text-sm">Disconnect Google Calendar? Nemi will stop reading and writing that calendar.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" onClick={onDisconnect} disabled={disconnectPending}>
          {disconnectPending ? "Disconnecting…" : "Disconnect"}
        </Button>
        <Button type="button" variant="quiet" onClick={onKeep}>
          Keep connected
        </Button>
      </div>
    </div>
  );
}
