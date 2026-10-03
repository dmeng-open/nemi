export type PlanStatus =
  | "processing"
  | "awaiting_clarification"
  | "awaiting_location"
  | "awaiting_selection"
  | "awaiting_approval"
  | "scheduled"
  | "partial_success"
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
  calendar_checked: boolean;
  travel_time_is_estimate: boolean;
  listed_time_missing?: boolean;
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
  plan_type: "event" | "restaurant" | "itinerary" | null;
  summary: string | null;
  clarification_question: string | null;
  recommendations: Candidate[];
  selected_candidate_id: string | null;
  execution: Execution | null;
  error: PlanError | null;
  calendar: { ics_available: boolean };
  timeline: TimelineItem[];
  itineraries?: Itinerary[];
  agents?: AgentProgress[];
  execution_status?: string | null;
  execution_actions?: ExecutionAction[];
  limiting_constraint?: string | null;
  parallel_speedup?: number | null;
  execution_resolution?: string | null;
  created_at: string;
  updated_at: string;
};

export type ItineraryItem = {
  item_type: "restaurant" | "event" | "travel" | "buffer" | string;
  title: string;
  start: string;
  end: string;
  location: string | null;
  estimated_cost: number | null;
  travel_time_is_estimate: boolean;
};

export type ConstraintCheck = {
  code: string;
  label: string;
  status: "pass" | "fail" | "soft" | string;
  message: string;
};

export type Itinerary = {
  id: string;
  items: ItineraryItem[];
  estimated_total_cost: number;
  start: string;
  end: string;
  explanation: string | null;
  checks: ConstraintCheck[];
  valid: boolean;
};

export type AgentProgress = {
  agent: string;
  label: string;
  status: string;
  detail: string | null;
  duration_ms: number | null;
  model: string | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  tool_calls: string[];
  retry_count: number;
  error_code: string | null;
};

export type ExecutionAction = {
  item_id: string;
  title: string;
  status: string;
  calendar_event_id: string | null;
  error_code: string | null;
};

export type PlanSummary = {
  plan_id: string;
  status: PlanStatus;
  request: string;
  plan_type: "event" | "restaurant" | "itinerary" | null;
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
  home_city: string | null;
  latitude: number | null;
  longitude: number | null;
  default_radius_km: number | null;
  timezone: string | null;
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

export type ProviderConnection =
  | "mock"
  | "local"
  | "not_configured"
  | "configured"
  | "oauth_required"
  | "connected"
  | "unhealthy";

export type ProviderStatus = {
  key: string;
  label: string;
  mode: string;
  status: "ready" | "unavailable";
  connection: ProviderConnection;
  detail: string;
  account_email: string | null;
};

export type Integrations = {
  event_provider: ProviderStatus;
  place_provider: ProviderStatus;
  calendar_provider: ProviderStatus;
  openai_configured: boolean;
  timezone: string;
  demo_mode: boolean;
};
