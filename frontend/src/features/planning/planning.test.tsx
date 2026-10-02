import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AgentTimeline } from "@/features/planning/AgentTimeline";
import { CandidateCard } from "@/features/planning/CandidateCard";
import { Composer } from "@/features/planning/Composer";
import { Confirmation, SuccessState } from "@/features/planning/Confirmation";
import type { Candidate, TimelineItem } from "@/types/api";

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
