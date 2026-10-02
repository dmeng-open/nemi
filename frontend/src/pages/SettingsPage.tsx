import { useQuery } from "@tanstack/react-query";

import { getIntegrations } from "@/api/integrations";
import { useTheme, type ThemeChoice } from "@/hooks/useTheme";

const CHOICES: ThemeChoice[] = ["light", "dark", "system"];

export function SettingsPage() {
  const { theme, setTheme } = useTheme();
  const integrations = useQuery({ queryKey: ["integrations"], queryFn: getIntegrations });

  return (
    <div className="mx-auto max-w-2xl">
      <h1 className="font-serif text-4xl">Settings</h1>
      <section className="mt-8">
        <h2 className="text-sm font-medium">Appearance</h2>
        <div className="mt-3 flex gap-2" role="group" aria-label="Theme">
          {CHOICES.map((choice) => (
            <button
              key={choice}
              type="button"
              aria-pressed={theme === choice}
              className={
                theme === choice
                  ? "rounded-full bg-accent px-4 py-2 text-sm text-accent-ink"
                  : "rounded-full border border-line px-4 py-2 text-sm"
              }
              onClick={() => setTheme(choice)}
            >
              {choice}
            </button>
          ))}
        </div>
      </section>
      <section className="mt-8">
        <h2 className="text-sm font-medium">Timezone</h2>
        <p className="mt-2 text-sm text-muted">
          “Saturday” and “after work” are read in {integrations.data?.timezone ?? "the configured timezone"}. Change
          APP_TIMEZONE to match where you are.
        </p>
      </section>
    </div>
  );
}
