import { Button } from "@/components/ui/button";
import { formatDay, formatRange, formatTravel } from "@/lib/format";
import type { Candidate } from "@/types/api";

export function Confirmation({
  candidate,
  timeZone,
  error,
  pending = false,
  icsHref,
  onCancel,
  onApprove,
  onConnect,
}: {
  candidate: Candidate;
  timeZone: string;
  error?: string | null;
  pending?: boolean;
  icsHref?: string | null;
  onCancel: () => void;
  onApprove: () => void;
  onConnect?: () => void;
}) {
  return (
    <section className="rounded-3xl border border-line bg-surface p-6 shadow-[var(--shadow)]" aria-label="Ready to schedule">
      <p className="text-sm text-muted">Ready to schedule</p>
      <h2 className="mt-2 font-serif text-4xl">{candidate.title}</h2>
      <p className="mt-4 text-base leading-7">
        {formatDay(candidate.start, timeZone)}
        <br />
        {candidate.listed_time_missing
          ? "Start time was not listed. Adding it uses noon to 2:00 PM as a placeholder."
          : formatRange(candidate.start, candidate.end, timeZone)}
      </p>
      <p className="mt-4 text-sm text-muted">
        Travel estimate: {candidate.travel_minutes != null ? `${candidate.travel_minutes} minutes` : formatTravel(null, candidate.distance_km) || "not estimated"}
      </p>
      <p className="mt-2 text-sm text-sage">
        {candidate.listed_time_missing
          ? "Start time was not listed."
          : candidate.calendar_checked === false
            ? "Schedule was not checked."
            : candidate.schedule_compatible
              ? "No conflicts detected."
              : "This overlaps something on your calendar."}
      </p>
      {error ? (
        <p className="mt-4 text-sm text-danger" role="alert">
          {error}
        </p>
      ) : null}
      <div className="mt-6 flex flex-wrap gap-3">
        <Button type="button" variant="quiet" onClick={onCancel} disabled={pending}>
          Cancel
        </Button>
        <Button type="button" onClick={onApprove} disabled={pending}>
          {pending ? "Adding…" : "Add to schedule"}
        </Button>
        {onConnect ? (
          <Button type="button" variant="quiet" onClick={onConnect} disabled={pending}>
            Connect
          </Button>
        ) : null}
        {icsHref ? (
          <a
            className="inline-flex h-11 items-center rounded-full border border-line px-5 text-sm"
            href={icsHref}
          >
            Download .ics
          </a>
        ) : null}
      </div>
    </section>
  );
}

export function SuccessState({
  title,
  when,
  hours,
  downloadHref,
  onAnother,
}: {
  title: string;
  when: string;
  hours: string;
  downloadHref: string;
  onAnother: () => void;
}) {
  return (
    <section className="rounded-3xl border border-line bg-surface p-6 shadow-[var(--shadow)]" aria-label="Scheduled">
      <p className="text-sm text-sage">Scheduled</p>
      <h2 className="mt-2 font-serif text-4xl">{title}</h2>
      <p className="mt-4 leading-7">
        {when}
        <br />
        {hours}
      </p>
      <p className="mt-3 text-sm text-muted">
        The file opens in Google Calendar, Apple Calendar, or Outlook.
      </p>
      <div className="mt-6 flex flex-wrap gap-3">
        <a
          className="inline-flex h-11 items-center rounded-full bg-accent px-5 text-sm font-medium text-accent-ink"
          href={downloadHref}
        >
          Add to calendar
        </a>
        <Button type="button" variant="quiet" onClick={onAnother}>
          Start another plan
        </Button>
      </div>
    </section>
  );
}
