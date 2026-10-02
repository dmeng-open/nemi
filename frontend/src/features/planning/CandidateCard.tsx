import { useState } from "react";

import { Button } from "@/components/ui/button";
import { formatDay, formatPrice, formatRange, formatTravel, labelFor, matchPercent } from "@/lib/format";
import type { Candidate } from "@/types/api";

export function CandidateCard({
  candidate,
  timeZone,
  onChoose,
  pending = false,
}: {
  candidate: Candidate;
  timeZone: string;
  onChoose: (candidate: Candidate) => void;
  pending?: boolean;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const place = candidate.venue || candidate.address;

  return (
    <article className="overflow-hidden rounded-3xl border border-line bg-surface shadow-[var(--shadow)]">
      <div className="relative h-44 bg-gradient-to-br from-accent/25 to-sage/20">
        {candidate.image_url && !imageFailed ? (
          <img
            src={candidate.image_url}
            alt=""
            className="h-full w-full object-cover"
            onError={() => setImageFailed(true)}
          />
        ) : null}
      </div>
      <div className="space-y-4 p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs tracking-wide text-muted uppercase">
              {candidate.categories.map(labelFor).join(" · ") || "Option"}
            </p>
            <h3 className="mt-1 font-serif text-2xl">{candidate.title}</h3>
          </div>
          <p className="rounded-full bg-bg px-3 py-1 text-sm">Match {matchPercent(candidate.score)}</p>
        </div>
        <p className="text-sm leading-6 text-muted">
          {formatDay(candidate.start, timeZone)}
          <br />
          {formatRange(candidate.start, candidate.end, timeZone)}
        </p>
        <p className="text-sm">
          {formatPrice(candidate.price_min, candidate.price_level)}
          {formatTravel(candidate.travel_minutes, candidate.distance_km)
            ? ` · ${formatTravel(candidate.travel_minutes, candidate.distance_km)}`
            : ""}
        </p>
        {place ? <p className="text-sm text-muted">{place}</p> : null}
        {candidate.rating != null && candidate.candidate_type === "restaurant" ? (
          <p className="text-sm text-muted">Rating {candidate.rating.toFixed(1)}</p>
        ) : null}
        <div>
          <p className="text-sm font-medium">Why Nemi picked this</p>
          <p className="mt-1 text-sm leading-6 text-muted">{candidate.explanation}</p>
        </div>
        <p className="text-sm text-sage">
          {candidate.schedule_compatible ? "Fits your open time" : "Check the schedule before adding it"}
        </p>
        <div className="flex flex-wrap gap-2">
          {candidate.source_url ? (
            <a
              className="inline-flex h-9 items-center rounded-full border border-line px-3 text-sm"
              href={candidate.source_url}
              target="_blank"
              rel="noreferrer"
            >
              View details
            </a>
          ) : null}
          <Button type="button" size="sm" disabled={pending} onClick={() => onChoose(candidate)}>
            Choose this
          </Button>
        </div>
      </div>
    </article>
  );
}
