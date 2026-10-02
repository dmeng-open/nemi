export type PlanStatus =
  | "processing"
  | "awaiting_clarification"
  | "awaiting_selection"
  | "awaiting_approval"
  | "scheduled"
  | "failed"
  | "no_matches"
  | "cancelled";

export type ScoreComponents = {
  preference: number;
  schedule: number;
  distance: number;
  price: number;
  quality: number;
};

export type Candidate = {
  id: string;
  candidate_type: "event" | "restaurant";
  title: string;
  description: string | null;
  categories: string[];
  start: string | null;
  end: string | null;
  venue: string | null;
  address: string | null;
  distance_km: number | null;
  travel_minutes: number | null;
  price_min: number | null;
  price_max: number | null;
  price_level: number | null;
  rating: number | null;
  source_url: string | null;
  image_url: string | null;
  score: number;
  components: ScoreComponents;
  schedule_compatible: boolean;
  explanation: string;
};

export type TimelineItem = {
  id: string;
  event_type: string;
  label: string;
  status: "started" | "completed" | "failed";
  timestamp: string;
};

export type Execution = {
  calendar_event_id: string;
  title: string;
  start: string;
  end: string;
  location: string | null;
};

export type PlanError = {
  code: string;
  message: string;
};

export type Plan = {
  plan_id: string;
  status: PlanStatus;
  request: string;
  plan_type: "event" | "restaurant" | null;
  summary: string | null;
  clarification_question: string | null;
  recommendations: Candidate[];
  selected_candidate_id: string | null;
  execution: Execution | null;
  error: PlanError | null;
  timeline: TimelineItem[];
  created_at: string;
  updated_at: string;
};

export type PlanSummary = {
  plan_id: string;
  status: PlanStatus;
  request: string;
  plan_type: "event" | "restaurant" | null;
  summary: string | null;
  created_at: string;
  selected_title: string | null;
};

export type TimeRange = {
  start: string;
  end: string;
  label: string | null;
};

export type Preferences = {
  preferred_event_categories: string[];
  preferred_cuisines: string[];
  disliked_categories: string[];
  default_budget: number | null;
  max_travel_minutes: number | null;
  preferred_days: string[];
  preferred_time_ranges: TimeRange[];
};

export type CalendarEvent = {
  id: string;
  title: string;
  start: string;
  end: string;
  location: string | null;
  description: string | null;
  source_url: string | null;
};

export type ProviderStatus = {
  key: string;
  label: string;
  mode: string;
  status: "ready" | "unavailable";
  detail: string;
};

export type Integrations = {
  event_provider: ProviderStatus;
  place_provider: ProviderStatus;
  calendar_provider: ProviderStatus;
  openai_configured: boolean;
  timezone: string;
  demo_mode: boolean;
};
