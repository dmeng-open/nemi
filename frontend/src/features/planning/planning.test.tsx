import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AgentTimeline } from "@/features/planning/AgentTimeline";
import { CandidateCard } from "@/features/planning/CandidateCard";
import { Composer } from "@/features/planning/Composer";
import { Confirmation, SuccessState } from "@/features/planning/Confirmation";
import { PlanWorkspace } from "@/features/planning/PlanWorkspace";
import type { Candidate, Plan, TimelineItem } from "@/types/api";

const candidate: Candidate = {
  id: "evt_ai",
  candidate_type: "event",
  title: "AI Builders Workshop",
  description: "A hands-on afternoon.",
  categories: ["technology", "workshops"],
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
  explanation: "You said you enjoy technology. It fits your open time.",
  calendar_checked: true,
  travel_time_is_estimate: false,
};

describe("planning interface", () => {
  it("submits a new plan from the composer", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Composer onSubmit={onSubmit} />);
    await user.click(screen.getByRole("button", { name: "Saturday afternoon nearby" }));
    await user.click(screen.getByRole("button", { name: "Plan this" }));
    expect(onSubmit).toHaveBeenCalledWith(expect.stringContaining("Saturday afternoon"));
  });

  it("renders the agent timeline from stored events", () => {
    const items: TimelineItem[] = [
      {
        id: "1",
        event_type: "constraints_parsed",
        label: "Understood your request",
        status: "completed",
        timestamp: "2026-10-02T20:00:00Z",
      },
      {
        id: "2",
        event_type: "search_completed",
        label: "Found 12 possible events",
        status: "completed",
        timestamp: "2026-10-02T20:00:01Z",
      },
    ];
    render(<AgentTimeline items={items} working />);
    expect(screen.getByText("Understood your request")).toBeInTheDocument();
    expect(screen.getByText("Found 12 possible events")).toBeInTheDocument();
    expect(screen.getByText("Working on your plan")).toBeInTheDocument();
  });

  it("renders a candidate and chooses it", async () => {
    const user = userEvent.setup();
    const onChoose = vi.fn();
    render(
      <CandidateCard candidate={candidate} timeZone="America/Chicago" onChoose={onChoose} />,
    );
    expect(screen.getByRole("heading", { name: "AI Builders Workshop" })).toBeInTheDocument();
    expect(screen.getByText(/Why Nemi picked this/)).toBeInTheDocument();
    expect(screen.getByText("Match 91%")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Choose this" }));
    expect(onChoose).toHaveBeenCalledWith(candidate);
  });

  it("shows a ticket price and keeps place prices as a band", () => {
    const ticket = render(
      <CandidateCard
        candidate={{
          ...candidate,
          price_min: 42,
          price_level: null,
          travel_time_is_estimate: true,
          travel_minutes: 8,
        }}
        timeZone="America/Chicago"
        onChoose={vi.fn()}
      />,
    );
    expect(ticket.getByText(/\$42/)).toBeInTheDocument();
    expect(ticket.queryByText(/Price varies/)).not.toBeInTheDocument();
    ticket.unmount();

    const place = render(
      <CandidateCard
        candidate={{
          ...candidate,
          candidate_type: "restaurant",
          title: "Noodle Bar",
          price_min: 35,
          price_level: 2,
          travel_time_is_estimate: true,
        }}
        timeZone="America/Chicago"
        onChoose={vi.fn()}
      />,
    );
    expect(place.getByRole("heading", { name: "Noodle Bar" })).toBeInTheDocument();
    expect(place.getByText(/\$\$ · about/)).toBeInTheDocument();
    expect(place.queryByText(/\$35/)).not.toBeInTheDocument();
    place.unmount();

    const menu = render(
      <CandidateCard
        candidate={{
          ...candidate,
          title: "Menu Place",
          price_min: 48,
          price_level: 2,
          travel_time_is_estimate: false,
        }}
        timeZone="America/Chicago"
        onChoose={vi.fn()}
      />,
    );
    expect(menu.getByText(/\$\$ · about \$48/)).toBeInTheDocument();
  });

  it("asks for approval before scheduling", async () => {
    const user = userEvent.setup();
    const onApprove = vi.fn();
    const onCancel = vi.fn();
    render(
      <Confirmation
        candidate={candidate}
        timeZone="America/Chicago"
        onApprove={onApprove}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByText("Ready to schedule")).toBeInTheDocument();
    expect(screen.getByText("No conflicts detected.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Add to schedule" }));
    expect(onApprove).toHaveBeenCalledOnce();
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("shows the scheduled success state", () => {
    render(
      <SuccessState
        title="AI Builders Workshop"
        when="Saturday, Oct 3"
        hours="2:00 PM – 4:00 PM"
        downloadHref="/api/plans/1/ics"
        onAnother={() => undefined}
      />,
    );
    expect(screen.getByText("Scheduled")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add to calendar" })).toHaveAttribute(
      "href",
      "/api/plans/1/ics",
    );
    expect(screen.getByRole("button", { name: "Start another plan" })).toBeInTheDocument();
  });
});

function planFixture(overrides: Partial<Plan> = {}): Plan {
  return {
    plan_id: "11111111-1111-4111-8111-111111111111",
    status: "awaiting_selection",
    request: "Saturday afternoon",
    plan_type: "event",
    summary: "Saturday afternoon",
    clarification_question: "Which day?",
    recommendations: [candidate, { ...candidate, id: "evt_other", title: "Other Option" }],
    selected_candidate_id: null,
    execution: null,
    error: null,
    calendar: { ics_available: false },
    timeline: [],
    created_at: "2026-10-02T20:00:00Z",
    updated_at: "2026-10-02T20:00:00Z",
    ...overrides,
  };
}

function renderWorkspace(plan: Plan, handlers: Partial<Parameters<typeof PlanWorkspace>[0]> = {}) {
  return render(
    <MemoryRouter>
      <PlanWorkspace
        plan={plan}
        timeZone="America/Chicago"
        onClarify={vi.fn()}
        onChoose={vi.fn()}
        onReject={vi.fn()}
        onCancel={vi.fn()}
        onApprove={vi.fn()}
        onContinue={vi.fn()}
        onConnect={vi.fn()}
        onRetry={vi.fn()}
        onAnother={vi.fn()}
        {...handlers}
      />
    </MemoryRouter>,
  );
}

describe("v1 planning states", () => {
  it("shows the location panel without the clarification input", () => {
    renderWorkspace(
      planFixture({
        status: "awaiting_location",
        recommendations: [],
        error: { code: "city_required", message: "Add a home city in Preferences, then continue this plan." },
      }),
    );
    expect(screen.getByRole("heading", { name: "Location needed" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Preferences" })).toHaveAttribute("href", "/preferences");
    expect(screen.getByRole("button", { name: "Continue this plan" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Clarification" })).not.toBeInTheDocument();
  });

  it("shows cards and Connect when the calendar is disconnected", () => {
    const view = renderWorkspace(
      planFixture({
        status: "awaiting_approval",
        selected_candidate_id: "evt_ai",
        error: { code: "calendar_not_connected", message: "Connect Google Calendar to add this plan." },
      }),
    );
    expect(view.getAllByRole("heading", { name: "AI Builders Workshop" }).length).toBeGreaterThan(0);
    expect(view.getByRole("heading", { name: "Other Option" })).toBeInTheDocument();
    expect(view.getByRole("button", { name: "Connect" })).toBeInTheDocument();
    expect(view.queryByText("Scheduled")).not.toBeInTheDocument();
  });

  it("offers the calendar file while approval is still waiting", () => {
    const view = renderWorkspace(
      planFixture({
        status: "awaiting_approval",
        selected_candidate_id: "evt_ai",
        calendar: { ics_available: true },
        error: {
          code: "calendar_write_unconfirmed",
          message: "Nemi could not confirm the calendar event.",
        },
      }),
    );
    expect(view.getByRole("link", { name: "Download .ics" })).toHaveAttribute(
      "href",
      "/api/plans/11111111-1111-4111-8111-111111111111/ics",
    );
    expect(view.queryByText("Scheduled")).not.toBeInTheDocument();
  });

  it("rejects only the card that was declined", async () => {
    const user = userEvent.setup();
    const onReject = vi.fn();
    renderWorkspace(planFixture(), { onReject });
    await user.click(screen.getByRole("button", { name: "Not this, Other Option" }));
    expect(onReject).toHaveBeenCalledTimes(1);
    expect(onReject).toHaveBeenCalledWith(expect.objectContaining({ id: "evt_other" }));
  });
});
