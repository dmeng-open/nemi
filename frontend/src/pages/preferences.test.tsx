import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PreferencesPage } from "@/pages/PreferencesPage";
import type { Preferences } from "@/types/api";

vi.mock("@/api/preferences", () => ({
  getPreferences: vi.fn(),
  updatePreferences: vi.fn(),
}));

import { getPreferences, updatePreferences } from "@/api/preferences";

const saved: Preferences = {
  preferred_event_categories: ["technology"],
  preferred_cuisines: ["japanese"],
  disliked_categories: [],
  default_budget: 50,
  max_travel_minutes: 30,
  preferred_days: ["saturday"],
  preferred_time_ranges: [{ start: "12:00:00", end: "18:00:00", label: "afternoon" }],
  home_city: null,
  latitude: null,
  longitude: null,
  default_radius_km: null,
  timezone: null,
};

describe("preferences location fields", () => {
  beforeEach(() => {
    vi.mocked(getPreferences).mockResolvedValue(saved);
    vi.mocked(updatePreferences).mockImplementation(async (body) => body);
  });

  it("includes location fields and submits them", async () => {
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PreferencesPage />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("textbox", { name: "Home city" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Latitude" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Longitude" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Default radius (km)" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Timezone" })).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: "Home city" }), "Chicago");
    await user.type(screen.getByRole("textbox", { name: "Latitude" }), "41.88");
    await user.type(screen.getByRole("textbox", { name: "Longitude" }), "-87.63");
    await user.type(screen.getByRole("textbox", { name: "Default radius (km)" }), "10");
    await user.type(screen.getByRole("textbox", { name: "Timezone" }), "America/Chicago");
    await user.click(screen.getByRole("button", { name: "Save preferences" }));

    const submitted = vi.mocked(updatePreferences).mock.calls[0]?.[0];
    expect(submitted).toEqual(
      expect.objectContaining({
        home_city: "Chicago",
        latitude: 41.88,
        longitude: -87.63,
        default_radius_km: 10,
        timezone: "America/Chicago",
      }),
    );
  });
});
