import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { getPreferences, updatePreferences } from "@/api/preferences";
import { Button } from "@/components/ui/button";
import { CUISINES, DAYS, EVENT_CATEGORIES } from "@/features/preferences/options";
import { labelFor } from "@/lib/format";
import type { Preferences } from "@/types/api";

const schema = z.object({
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
    },
  });

  useEffect(() => {
    if (query.data) form.reset(query.data);
  }, [form, query.data]);

  const mutation = useMutation({
    mutationFn: updatePreferences,
    onSuccess: async (data) => {
      form.reset(data);
      await queryClient.invalidateQueries({ queryKey: ["preferences"] });
    },
  });

  const draft = form.watch();
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
