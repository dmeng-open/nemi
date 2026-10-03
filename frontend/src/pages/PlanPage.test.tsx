import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Integrations, Plan, Preferences } from "@/types/api";

vi.mock("@/api/plans", () => ({
  getPlan: vi.fn(),
  approvePlan: vi.fn(),
  clarifyPlan: vi.fn(),
  clearSelection: vi.fn(),
  continuePlan: vi.fn(),
  createPlan: vi.fn(),
  rejectCandidate: vi.fn(),
  selectCandidate: vi.fn(),
}));

vi.mock("@/api/integrations", () => ({
  getIntegrations: vi.fn(),
  connectGoogleCalendar: vi.fn(),
}));

vi.mock("@/api/preferences", () => ({
  getPreferences: vi.fn(),
}));

import { getIntegrations } from "@/api/integrations";
import { getPlan } from "@/api/plans";
import { getPreferences } from "@/api/preferences";
import { PlanPage } from "@/pages/PlanPage";

const planId = "11111111-1111-4111-8111-111111111111";

const preferences: Preferences = {
  preferred_event_categories: [],
  preferred_cuisines: [],
  disliked_categories: [],
  default_budget: null,
  max_travel_minutes: null,
  preferred_days: [],
  preferred_time_ranges: [],
  home_city: null,
  latitude: null,
  longitude: null,
  default_radius_km: null,
  timezone: "America/Chicago",
};

const integrations: Integrations = {
  event_provider: {
    key: "events",
    label: "Events",
    mode: "mock",
    status: "ready",
    connection: "mock",
    detail: "",
    account_email: null,
  },
  place_provider: {
    key: "places",
    label: "Places",
    mode: "mock",
    status: "ready",
    connection: "mock",
    detail: "",
    account_email: null,
  },
  calendar_provider: {
    key: "calendar",
    label: "Calendar",
    mode: "local",
    status: "ready",
    connection: "local",
    detail: "",
    account_email: null,
  },
  openai_configured: false,
  timezone: "America/Chicago",
  demo_mode: true,
};

const plan: Plan = {
  plan_id: planId,
  status: "awaiting_selection",
  request: "Saturday afternoon",
  plan_type: "event",
  summary: "Saturday afternoon",
  clarification_question: null,
  recommendations: [
    {
      id: "evt_ai",
      candidate_type: "event",
      title: "AI Builders Workshop",
      description: "A hands-on afternoon.",
      categories: ["technology"],
      start: "2026-10-03T19:00:00Z",
      end: "2026-10-03T21:00:00Z",
      venue: "Catalyst Hall",
      address: "1840 N Halsted St",
      distance_km: 2.4,
      travel_minutes: 12,
      price_min: 20,
      price_max: 20,
      price_level: null,
      rating: 4.8,
      source_url: "https://example.com/events/ai",
      image_url: null,
      score: 0.91,
      components: { preference: 0.9, schedule: 1, distance: 0.8, price: 0.9, quality: 0.9 },
      schedule_compatible: true,
      explanation: "You said you enjoy technology.",
      calendar_checked: true,
      travel_time_is_estimate: false,
    },
  ],
  selected_candidate_id: null,
  execution: null,
  error: null,
  calendar: { ics_available: false },
  timeline: [],
  created_at: "2026-10-02T20:00:00Z",
  updated_at: "2026-10-02T20:00:00Z",
};

describe("PlanPage", () => {
  beforeEach(() => {
    vi.mocked(getIntegrations).mockResolvedValue(integrations);
    vi.mocked(getPreferences).mockResolvedValue(preferences);
  });

  it("renders through a loading plan query and then the workspace", async () => {
    let resolvePlan: (value: Plan) => void = () => undefined;
    const pending = new Promise<Plan>((resolve) => {
      resolvePlan = resolve;
    });
    vi.mocked(getPlan).mockReturnValue(pending);

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[`/plans/${planId}`]}>
          <Routes>
            <Route path="plans/:planId" element={<PlanPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Opening your plan…")).toBeInTheDocument();
    resolvePlan(plan);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "AI Builders Workshop" })).toBeInTheDocument();
    });
    expect(screen.queryByText("Opening your plan…")).not.toBeInTheDocument();
  });
});
