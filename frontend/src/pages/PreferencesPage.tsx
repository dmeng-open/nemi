import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { getPreferences, updatePreferences } from "@/api/preferences";
import { Button } from "@/components/ui/button";
import { CUISINES, DAYS, EVENT_CATEGORIES } from "@/features/preferences/options";
import { labelFor } from "@/lib/format";
import type { Preferences } from "@/types/api";

const schema = z
  .object({
    preferred_event_categories: z.array(z.string()),
    preferred_cuisines: z.array(z.string()),
    disliked_categories: z.array(z.string()),
    default_budget: z.number().min(0).max(10000).nullable(),
    max_travel_minutes: z.number().int().min(0).max(180).nullable(),
    preferred_days: z.array(z.string()),
    preferred_time_ranges: z.array(
      z.object({
        start: z.string(),
        end: z.string(),
        label: z.string().nullable(),
      }),
    ),
    home_city: z.string().max(80).nullable(),
    latitude: z.number().min(-90).max(90).nullable(),
    longitude: z.number().min(-180).max(180).nullable(),
    default_radius_km: z.number().min(1).max(50).nullable(),
    timezone: z.string().nullable(),
  })
  .superRefine((value, ctx) => {
    if ((value.latitude == null) !== (value.longitude == null)) {
      ctx.addIssue({
        code: "custom",
        message: "Enter both latitude and longitude, or leave both empty.",
        path: ["latitude"],
      });
    }
    if (value.timezone) {
      try {
        Intl.DateTimeFormat("en-US", { timeZone: value.timezone });
      } catch {
        ctx.addIssue({
          code: "custom",
          message: "Enter a valid IANA timezone, such as America/Chicago.",
          path: ["timezone"],
        });
      }
    }
  });

function toggle(list: string[], value: string) {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

export function PreferencesPage() {
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: ["preferences"], queryFn: getPreferences });
  const form = useForm<Preferences>({
    resolver: zodResolver(schema),
    defaultValues: {
      preferred_event_categories: [],
      preferred_cuisines: [],
      disliked_categories: [],
      default_budget: 50,
      max_travel_minutes: 30,
      preferred_days: [],
      preferred_time_ranges: [{ start: "12:00:00", end: "18:00:00", label: "afternoon" }],
      home_city: null,
      latitude: null,
      longitude: null,
      default_radius_km: null,
      timezone: null,
    },
  });

  useEffect(() => {
    if (!query.data) return;
    form.reset(query.data);
    setLatitudeText(query.data.latitude == null ? "" : String(query.data.latitude));
    setLongitudeText(query.data.longitude == null ? "" : String(query.data.longitude));
    setRadiusText(query.data.default_radius_km == null ? "" : String(query.data.default_radius_km));
  }, [form, query.data]);

  const mutation = useMutation({
    mutationFn: updatePreferences,
    onSuccess: async (data) => {
      form.reset(data);
      await queryClient.invalidateQueries({ queryKey: ["preferences"] });
    },
  });

  const [latitudeText, setLatitudeText] = useState("");
  const [longitudeText, setLongitudeText] = useState("");
  const [radiusText, setRadiusText] = useState("");
  const draft = form.watch();

  function setOptionalNumber(
    name: "latitude" | "longitude" | "default_radius_km",
    text: string,
    setText: (value: string) => void,
  ) {
    setText(text);
    const trimmed = text.trim();
    if (trimmed === "") {
      form.setValue(name, null, { shouldDirty: true, shouldValidate: true });
      return;
    }
    if (!/^-?\d+(\.\d+)?$/.test(trimmed)) return;
    form.setValue(name, Number(trimmed), { shouldDirty: true, shouldValidate: true });
  }
  const range = draft.preferred_time_ranges[0] ?? {
    start: "12:00:00",
    end: "18:00:00",
    label: "afternoon",
  };

  if (query.isLoading && !query.data) {
    return <p className="text-sm text-muted">Loading preferences…</p>;
  }
  if (query.isError) {
    return <p className="text-sm text-danger">Could not load preferences.</p>;
  }

  return (
    <form className="mx-auto max-w-2xl" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
      <h1 className="font-serif text-4xl">Preferences</h1>
      <p className="mt-3 text-sm leading-6 text-muted">
        Nemi uses these when your request leaves a budget, a distance, or a time of day open.
      </p>

      <ChipGroup
        title="Activities you like"
        options={EVENT_CATEGORIES}
        selected={draft.preferred_event_categories}
        onToggle={(value) =>
          form.setValue(
            "preferred_event_categories",
            toggle(draft.preferred_event_categories, value),
            { shouldDirty: true },
          )
        }
      />
      <ChipGroup
        title="Food you like"
        options={CUISINES}
        selected={draft.preferred_cuisines}
        onToggle={(value) =>
          form.setValue("preferred_cuisines", toggle(draft.preferred_cuisines, value), { shouldDirty: true })
        }
      />
      <ChipGroup
        title="Skip these"
        options={[...EVENT_CATEGORIES, ...CUISINES]}
        selected={draft.disliked_categories}
        onToggle={(value) =>
          form.setValue("disliked_categories", toggle(draft.disliked_categories, value), { shouldDirty: true })
        }
      />
      <ChipGroup
        title="Days you usually have free"
        options={DAYS}
        selected={draft.preferred_days}
        onToggle={(value) =>
          form.setValue("preferred_days", toggle(draft.preferred_days, value), { shouldDirty: true })
        }
      />

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <label className="text-sm">
          Default budget
          <input
            className="mt-2 w-full rounded-2xl border border-line bg-surface px-3 py-2"
            type="number"
            min={0}
            value={draft.default_budget ?? ""}
            onChange={(event) =>
              form.setValue("default_budget", event.target.value === "" ? null : Number(event.target.value), {
                shouldDirty: true,
              })
            }
          />
        </label>
        <label className="text-sm">
          Max travel minutes
          <input
            className="mt-2 w-full rounded-2xl border border-line bg-surface px-3 py-2"
            type="number"
            min={0}
            value={draft.max_travel_minutes ?? ""}
            onChange={(event) =>
              form.setValue(
                "max_travel_minutes",
                event.target.value === "" ? null : Number(event.target.value),
                { shouldDirty: true },
              )
            }
          />
        </label>
        <label className="text-sm">
          Usual start
          <input
            className="mt-2 w-full rounded-2xl border border-line bg-surface px-3 py-2"
            type="time"
            value={range.start.slice(0, 5)}
            onChange={(event) =>
              form.setValue(
                "preferred_time_ranges",
                [{ ...range, start: `${event.target.value}:00` }],
                { shouldDirty: true },
              )
            }
          />
        </label>
        <label className="text-sm">
          Usual end
          <input
            className="mt-2 w-full rounded-2xl border border-line bg-surface px-3 py-2"
            type="time"
            value={range.end.slice(0, 5)}
            onChange={(event) =>
              form.setValue("preferred_time_ranges", [{ ...range, end: `${event.target.value}:00` }], {
                shouldDirty: true,
              })
            }
          />
        </label>
      </div>

      <fieldset className="mt-8">
        <legend className="text-sm font-medium">Home location</legend>
        <p className="mt-2 text-sm leading-6 text-muted">
          Coordinates are required for restaurant search. A city is enough for event search.
        </p>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <label className="text-sm">
            Home city
            <input
              className="mt-2 w-full rounded-2xl border border-line bg-surface px-3 py-2"
              maxLength={80}
              value={draft.home_city ?? ""}
              onChange={(event) =>
                form.setValue("home_city", event.target.value.trim() ? event.target.value : null, {
                  shouldDirty: true,
                  shouldValidate: true,
                })
              }
            />
          </label>
          <label className="text-sm">
            Timezone
            <input
              className="mt-2 w-full rounded-2xl border border-line bg-surface px-3 py-2"
              placeholder="America/Chicago"
              value={draft.timezone ?? ""}
              onChange={(event) =>
                form.setValue("timezone", event.target.value.trim() ? event.target.value.trim() : null, {
                  shouldDirty: true,
                  shouldValidate: true,
                })
              }
            />
            {form.formState.errors.timezone ? (
              <span className="mt-1 block text-danger" role="alert">
                {form.formState.errors.timezone.message}
              </span>
            ) : null}
          </label>
          <label className="text-sm">
            Latitude
            <input
              className="mt-2 w-full rounded-2xl border border-line bg-surface px-3 py-2"
              inputMode="decimal"
              value={latitudeText}
              onChange={(event) =>
                setOptionalNumber("latitude", event.target.value, setLatitudeText)
              }
            />
            {form.formState.errors.latitude ? (
              <span className="mt-1 block text-danger" role="alert">
                {String(form.formState.errors.latitude.message)}
              </span>
            ) : null}
          </label>
          <label className="text-sm">
            Longitude
            <input
              className="mt-2 w-full rounded-2xl border border-line bg-surface px-3 py-2"
              inputMode="decimal"
              value={longitudeText}
              onChange={(event) =>
                setOptionalNumber("longitude", event.target.value, setLongitudeText)
              }
            />
          </label>
          <label className="text-sm">
            Default radius (km)
            <input
              className="mt-2 w-full rounded-2xl border border-line bg-surface px-3 py-2"
              inputMode="decimal"
              value={radiusText}
              onChange={(event) =>
                setOptionalNumber("default_radius_km", event.target.value, setRadiusText)
              }
            />
          </label>
        </div>
      </fieldset>

      <div className="mt-8 flex items-center gap-3">
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Saving…" : "Save preferences"}
        </Button>
        {mutation.isSuccess ? <p className="text-sm text-sage">Saved</p> : null}
        {mutation.isError || form.formState.errors.default_budget ? (
          <p className="text-sm text-danger" role="alert">
            Could not save those preferences.
          </p>
        ) : null}
      </div>
    </form>
  );
}

function ChipGroup({
  title,
  options,
  selected,
  onToggle,
}: {
  title: string;
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <fieldset className="mt-8">
      <legend className="text-sm font-medium">{title}</legend>
      <div className="mt-3 flex flex-wrap gap-2">
        {options.map((option) => {
          const on = selected.includes(option);
          return (
            <button
              key={option}
              type="button"
              aria-pressed={on}
              className={
                on
                  ? "rounded-full bg-accent px-3 py-1.5 text-sm text-accent-ink"
                  : "rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-muted"
              }
              onClick={() => onToggle(option)}
            >
              {labelFor(option)}
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
