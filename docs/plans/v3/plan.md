# Goal

On this machine, the evening itinerary graph calls a model for supervisor decomposition, restaurant choice, event choice, and critic review. Dates, overlaps, budget, the hard home-by time, diet, and calendar writes stay in code. A person can still finish a date night from the mock catalog with no Ticketmaster and no Google account.

This file is the implementation handoff. It is not a numbered Nemi version. Do not add a V3 row to `docs/versions/`, the roadmap, or `docs/architecture.md`. After implementation, behavior notes go in `docs/versions/multi-llm/`.

# User / Business Outcome

A person on this computer asks for dinner and something afterwards. Nemi still shows specialist progress, then whole-evening plans, and writes the calendar only after an explicit yes. The roles that judge the evening use a versioned, rate-limited, evaluable model call. Approving twice still creates one restaurant event and one activity event.

# Current System

Two graphs already exist.

- Single activity or one meal: `compile_planning_graph` in `backend/app/agents/graph.py`. Nodes are `parse_request`, `load_user_preferences`, `get_calendar_availability`, `determine_plan_type`, `search_events`, `search_restaurants`, `normalize_candidates`, `rank_candidates`, `verify_candidates`, `generate_recommendations`, `wait_for_user_selection`, `wait_for_user_approval`, `create_calendar_plan`. `PlanningOrchestrator._discover_single` compiles that graph with its own `MemorySaver`. HTTP approve calls `schedule_approved_plan` and does not send `Command(resume=...)`.
- Multi-part evening: `compile_itinerary_graph` in `backend/app/agents/itinerary/graph.py`. Entry is `is_itinerary_request` in `routing.py`. Nodes, in graph order: `understand`, `load_preferences`, `decompose`, `calendar_analysis`, `restaurant_research`, `event_research`, `aggregate`, `plan`, `constraint_engine`, `verify_semantics`, `critique`, `apply_replan`, `prepare_approval`, `human_approval`, `execute`, `finalize`. `prepare_approval` leads to `human_approval`, which calls `interrupt`. Approve resumes that thread with `Command(resume={"action": "approve", "itinerary_id": ...})`.

`docs/plans/v2/plan.md` calls both graphs the "V2 graph". The code names are the ones above. Follow the code.

Every itinerary node is deterministic today. Nothing in `backend/app/agents/itinerary/` imports `app.agents.llm`. `prompts.py` defines `SUPERVISOR_V1`, `RESTAURANT_RESEARCH_V1`, `EVENT_RESEARCH_V1`, `ITINERARY_PLANNER_V1`, `VERIFIER_V1`, and `CRITIC_V1`. No other module imports those strings. Spans always pass `model="deterministic"` and zero tokens. Supervisor spans store `supervisor_policy_v1`, while `SUPERVISOR_PROMPT_VERSION` is `supervisor_v1`.

`Settings.model_for` exists and is unused. `llm.py` always parses with `settings.openai_model`. `max_total_llm_calls` (default 12) is unread. `max_supervisor_steps` (20), `max_tool_calls_per_agent` (10), `max_replan_attempts` (3), and `specialist_timeout_seconds` (25) are already used by the itinerary graph.

# Facts

- `is_itinerary_request` is true for "date night", "after dinner", "after lunch", "afternoon and evening", or both a meal word and an outing word. Missing date sets `needs_clarification` and `understand` ends at `END` with `awaiting_clarification` before `decompose`.
- `decompose_tasks` always emits calendar, then restaurant and/or events when the regex constraints asked for them, then an itinerary task that depends on that research. `AgentTask` fields are `task_id`, `task_type`, `status`, `dependencies`, `assigned_agent`, `input`, `result`, `error`, `retryable`, `retry_count`.
- Research searches, filters, then `HeuristicRanker.rank`. `build_itineraries` drops `dietary == "exclude"` and rejected ids. Meal length is `DINNER_MINUTES = 90`. Travel between dinner and the activity is the average of the two catalog travel estimates, default 15, minimum 5. `execute` writes only `restaurant` and `event` items.
- `validate_itinerary` fails closed on overlap, bad duration, calendar overlap when the read succeeded, hard end, budget, and hard travel. Its `_checks` call does not pass `dietary`, so the dietary argument stays the default `"ok"`. Diet is enforced by research filtering, by `build_itineraries`, and by the deterministic `critique()`.
- `authorize` is an allow-list by agent name. `google_calendar.create_event` and `calendar.delete_event` are granted only to `execution`. Research agents are not on those tools.
- `interpret_revision` matches cheaper, restaurant, quieter/activity, then later. Any other sentence, including the chip text `Finish earlier`, hits the `else` branch: both research tasks reopen, both current candidate ids are rejected, and both research artifacts are cleared. Calendar is not reopened.
- `_plan` omits the `itineraries` key when a new build is empty and an older list exists. `constraint_engine` then replaces `itineraries` with the valid subset, which can be `[]`. `_replace_itineraries` deletes saved rows and inserts whatever list it is given, including an empty list.
- `human_approval` does not substitute `ids[0]` for a non-empty unknown id. It sets `awaiting_approval`, `invalid_selection`, and `after_human` returns to `prepare_approval`. An omitted id selects the only card when exactly one itinerary exists.
- At the revision cap, `interpret_revision` returns `ASK_USER` and `awaiting_approval` without clearing itineraries. `test_revision_limit_stays_approvable` covers that, and also approves `"not-a-real-itinerary"` and expects zero calendar rows.
- `resume_itinerary` refuses approve unless status is `awaiting_approval`. `run_itinerary_discovery` on an unexpected exception calls `mark_failed` and does not `_save`. `mark_failed` sets `failed` and does not delete itinerary rows from an earlier save. `apply_execution_command` retry accepts `partial_success` or `failed`, and if no row is `selected` it falls through to the lowest rank. It calls `schedule_block` for every restaurant and event item. Completed keys are replayed inside `schedule_block`.
- `after_critic` uses `>=` on `max_supervisor_steps` and routes to `prepare_approval` when itineraries exist. `after_replan` uses `>`. `finalize` can set `awaiting_approval` and then the edge is `END`. `execute` also goes to `END`.
- `OpenAIConstraintParser` retries validation three times (`range(3)`), appends `The previous output was invalid: {error}`, and raises `LLMValidationError`. Timeouts retry inside those three attempts and raise on the last one. `OpenAIGateway.parse` uses `responses.parse`, `store=False`, and `max_retries=0`. It returns the parsed model only. It does not return token usage.
- `AgentSpan.input_tokens` and `output_tokens` are non-null integers defaulting to 0. `estimate_cost_usd` is the gpt-4o-mini formula. `LANGGRAPH_CHECKPOINTING` defaults true. `main._open_checkpointer` uses `AsyncPostgresSaver` only when that flag is true and `database_url` starts with `postgresql`. Failure logs `checkpoint_unavailable` and uses `MemorySaver`. Tests use SQLite. No test starts Postgres checkpointing.
- The date-night example is the "Saturday date night" chip. `AgentBoard` shows specialist label, detail, and status for `plan_type == "itinerary"`. The developer trace prints `agent.model`. There is no separate date-night route.
- `README.md` Architecture says the graph is one state machine and does not spawn other agents. `docs/architecture.md` opens with the second LangGraph, then under `## LangGraph workflow` says there is no second agent. V4 means leaving this machine. V5 means splitting services. `backend/app/integrations/calendar/google.py` calls `https://www.googleapis.com/calendar/v3/calendars/primary/events`. That path is Google's.
- `backend/pyproject.toml` `testpaths` includes `tests` and `evals`. `backend/evals/multi_agent/test_scenarios.py` is deterministic and must stay off the network. `backend/tests/conftest.py` sets an empty OpenAI key.

# Assumptions

- One local user remains the tenant. Itinerary rows keep the same `user_id` as planning sessions.
- An empty `OPENAI_API_KEY` keeps the current deterministic policy for those four judgment points so existing pytest and the mock catalog still finish. Spans for that path keep `model="deterministic"` and do not record a prompt as sent.
- A configured key uses `model_for` on the real calls. Per-role env vars stay optional overrides of `OPENAI_MODEL`.
- "Finish earlier" tightens the evening by the same 60 minutes the existing "later" phrase adds. The floor is `time_start` plus 90 minutes.
- Candidate titles, blurbs, and tool snippets are data inside the user message. They are not copied into the system message.

# Constraints

Shipped behavior stays inside the decisions below. Do not add login, multi-user tenancy, token encryption, deployment, hosted CI, RAG, embeddings, a learned ranker, Kafka, Kubernetes, a service split, reservations, ticket purchase, model routing on the single-activity graph, or SSE. Do not write product docs under `learning/`. Do not commit, push, open a PR, or merge `main` unless the owner asks.

Google's `/calendar/v3/` path stays. Do not rename it to avoid the letters v3.

`ITINERARY_PLANNER_V1` and `VERIFIER_V1` stay in `prompts.py` and are not sent. Sending either string as an authoritative model call would let a model build the itinerary or judge coverage, which the approved decisions leave in `build_itineraries`, `validate_itinerary`, and the critic role. `PLANNER_MODEL` stays unused. `verify_semantics` stays on `review_semantics`. If an implementation cannot proceed without those two calls, stop. Do not add a planner or verifier model role to get past that stop.

# Invariants

- `is_itinerary_request` remains the only switch between the two graphs.
- Single-activity node names, selection, and approval stay. Production approve of that graph still calls `schedule_approved_plan` and does not resume it.
- Agents exchange Pydantic artifacts. No agent reads another agent's prose. No swarm and no `create_supervisor`.
- The model proposes a schema. Code runs tools. Research agents still have no `google_calendar.create_event` and no `calendar.delete_event`.
- A write happens only after `human_approval` resumes with `action=approve`. `approved=True` is set only there for a known itinerary id.
- `validate_itinerary` runs before the critic model. A hard failure from that function cannot be stored as PASS.
- Regex date, budget, and home-by time stay on `ItineraryConstraints`. The model has no field that replaces them. A missing date still asks the person and is not invented.
- `HeuristicRanker` still orders candidates. The model cannot reinsert a candidate the code already removed for budget, diet, hard home-by, or rejection.
- Meal length, travel estimates, and the two-event write stay in the engine and executor. Travel and buffer blocks are not written.
- `MAX_REPLAN_ATTEMPTS` stays 3 and is shared by user revisions and the critic. A completed calendar task is not reopened because a restaurant or event was rejected. No new rejectable id means stop.
- Unknown non-empty `itinerary_id` is not rewritten to the first card. A failed replan does not persist an empty itinerary list over a previous list. After the revision cap, the current itinerary stays approvable.
- `Finish earlier` does not reject both branches up front. It tightens the end time and re-ranks. A research branch reruns only when the candidates already in hand cannot fill the new window.
- Discovery that fails before approval does not write a calendar event merely because an itinerary row exists. Execution retry fills only items on this plan that already have an execution action and whose create idempotency key is not `completed`.
- Delete still requires `confirm: true` and only deletes this plan's completed `execution_actions`.
- Unit tests and the existing pytest suite do not call OpenAI. No span invents token counts for a step that did not call a model.
- A limit breach while an itinerary is on screen returns through `prepare_approval` into `interrupt`. Status `awaiting_approval` is not saved from a thread that has already taken `END`.

# Proposed Design

## Decisions

1. **Two graphs stay.** Type 1, already approved. Implement inside the existing itinerary node functions. Do not add nodes, a third graph, or `app.agents.v3`.
2. **Four call sites.** `decompose` calls `model_for("supervisor")` with `SUPERVISOR_V1`. `restaurant_research` and `event_research`, after filter and `HeuristicRanker`, call `model_for("research")` with `RESTAURANT_RESEARCH_V1` or `EVENT_RESEARCH_V1`. `critique`, after `constraint_engine`, calls `model_for("critic")` with `CRITIC_V1`. Empty role strings already fall back to `OPENAI_MODEL` inside `model_for`. Both research nodes share `RESEARCH_MODEL`.
3. **Replaceable structured-output port.** Add a small interface the itinerary deps own: role, system text, user text, schema, in; parsed object and usage, out. Tests pass a fake. The OpenAI adapter uses the existing `AsyncOpenAI` client, `responses.parse`, `text_format`, `store=False`, and `max_retries=0`. Pass `model=settings.model_for(role)` per call. Leave `OpenAIGateway.parse` and `OpenAIConstraintParser` on their current single-activity behavior.
4. **Supervisor output.** The schema is a list the existing `AgentTask` model can validate. The model may set `task_id`, `task_type`, `dependencies`, and `assigned_agent` using only the ids and agents `decompose_tasks` already uses: `calendar`/`calendar_analysis`, `restaurant`/`restaurant_research`, `events`/`event_research`, `itinerary`/`itinerary_planner`. Code overwrites `status`, `input`, `result`, `error`, `retryable`, and `retry_count`. Code rejects an unknown id, an agent/type mismatch, a missing calendar or itinerary task, a missing restaurant or events task when the regex constraints asked for one, and any dependency outside that set. Date, budget, and home-by are not in the schema.
5. **Research output.** The system message is the `prompts.py` constant plus one stable sentence, written in code, that the only legal field is `selected_id` and that the ids in the user message are the only legal values. The user message lists the post-filter candidates. Titles and blurbs stay in that user message. The schema is one `selected_id`. Code accepts it only when that id is still in the filtered list. Code keeps membership, dietary flags, scores, excluded candidates, and provider failures. `build_itineraries` still sorts by the ranker. The model does not emit candidate objects, scores, travel minutes, or an itinerary. Span `prompt_version` is `restaurant_research_v1` or `event_research_v1`, the constant that was included.
6. **Critic output.** Code runs `validate_itinerary` and the existing `critique()` first. The model may set `PASS` or `REVISE` and issue `target_task` of `restaurant` or `events`, plus the existing issue type, severity, and message. Store `REVISE` when the model says `REVISE`, when `validate_itinerary` is invalid, or when deterministic `critique()` already says `REVISE`. A hard-failure target comes from the existing `_violation_target` map. Any other `target_task`, including `calendar`, is dropped. When the deterministic critic already says `REVISE`, its target wins. The model's target is used only when code had `PASS` and the model says `REVISE`. `apply_critic_replan` stays the reopen path. No itinerary means do not call the critic. `CRITIC_REJECT` stays a local injection and does not call the model.
7. **Retries.** Match `OpenAIConstraintParser`: three attempts. On `LLMValidationError`, `ValidationError`, or `ValueError`, append the error to the user message and retry. On timeout, retry inside the same three attempts and raise on the last one. Then fail that step closed. Each HTTP attempt counts as one LLM call. Span `retry_count` is attempts minus one. Parse retries do not increment `supervisor_steps` and are not tool calls.
8. **Budgets.** `max_total_llm_calls` increments only on a real structured invocation, including failed attempts. `max_supervisor_steps` stays the checkpoint counter already incremented in `decompose`, branch retry, `apply_replan`, and revise. `max_tool_calls_per_agent` stays inside `note_tool_call`, after `authorize` and before the side effect. A `tool_forbidden` call does not count. A model choice is not a tool call. Tool and model counters live on the deps object for that invoke. A new HTTP resume gets a fresh tool budget. `max_replan_attempts` is what bounds research across resumes.
9. **Limit breach.** Use `>=` on `after_replan` as well as `after_critic`. If itineraries are non-empty, the next node is `prepare_approval`, then `human_approval` interrupts. The thread stays interrupted. If no itinerary is on screen, go to `finalize` and `END`, and do not set `awaiting_approval` there. A `tool_limit` on the first discovery, with no itinerary yet, still fails that branch and lets the others join. A `tool_limit` or a refused model call while an itinerary is already on screen does not clear it. Do not add a model call just to exercise the counter. `specialist_timeout_seconds` stays a branch failure. `recursion_limit` stays 80.
10. **No key.** If the key is empty, the four sites call the current functions (`decompose_tasks`, first ranked id, `critique()`) through the same port. Spans use `model="deterministic"`, the existing policy version, and zero tokens. They do not store an OpenAI model name.
11. **Finish earlier.** Match that phrase before the current `else` branch. Subtract 60 minutes from `constraints.time_end`, floored at `time_start` plus 90 minutes. Do not append rejected ids. Do not clear calendar or research artifacts. Do not reopen calendar. Re-rank surviving candidates and run `build_itineraries`. If that build validates to a non-empty list, replace the on-screen itineraries, increment `replan_count` once, and return to `prepare_approval` without `Send`. If the window cannot shrink, change nothing, do not increment `replan_count`, and return to `prepare_approval`. A branch is insufficient only when the build is empty and that branch has no non-rejected candidate the existing placement rules can use: an event whose end still meets the hard end, or a restaurant that can hold a 90-minute dinner in the new window. Reopen and clear only those branches, once. Reopening both is allowed only when both fail that test. If that rerun still yields nothing valid, restore the previous constraints and the previous itinerary list, then `prepare_approval`.
12. **Preserve the previous itinerary.** On an empty or fully invalid replan result, put the previous itinerary list back into state before `_save`. Do not let `_replace_itineraries` delete the saved rows in favor of an empty list.
13. **Execution retry.** Call `schedule_block` only when an `ExecutionAction` row already exists for this plan, the itinerary row is `selected=True` with no rank-0 fallback, the item is `restaurant` or `event` on that itinerary, and `make_idempotency_key(plan_id, item_id, "create_event")` is not already `completed`. Skip completed items. Do not call `schedule_block` for them. A `schedule_conflict` leaves the key incomplete, so a later retry may try again. Zero execution actions means discovery failed or approval never happened: raise, and do not write.
14. **Untrusted content.** System text is only the `prompts.py` constant and the stable schema sentence from decision 5. User text, revision text, titles, blurbs, and tool results do not enter the system message, do not change `TOOLS`, and do not set `approved`.

## Recommendations

- Record cost with `estimate_cost_usd` only when the resolved model name is `gpt-4o-mini`. Any other model stores `estimated_cost_usd` as 0 and `safe_metadata` `cost_unpriced`. A call whose SDK usage is missing stores token counts 0 and `safe_metadata` `tokens_unreported`. A step with no call does not use those metadata flags.
- Keep the research prompt constants, and add the selection sentence in code, so a schema of `selected_id` can validate. Rewriting the constant into a new version is unnecessary if the span names the constant that was sent and the code sentence is covered by a unit test.
- Opt-in env for the live eval: `NEMI_RUN_MODEL_EVALS=1` together with a non-empty key. The name is local.

# Alternatives Considered

- **Send every string in `prompts.py`.** `ITINERARY_PLANNER_V1` tells the model to build dinner, travel, the activity, and the trip home. `VERIFIER_V1` has no approved model role. That moves pairing or pass/fail out of the engine. Rejected. Stop if a later change requires it.
- **Let research return a candidate list and drop unknown ids afterward.** The current prompt text matches that shape, and the model can omit the only legal id or spend the retry budget describing candidates. A single `selected_id`, checked against the filtered set, matches the approved "choose among" rule. The file constant is still sent.
- **Replace `HeuristicRanker` with the model order.** Rejected. The ranker still sorts. The model picks one surviving id.
- **Resume the single-activity graph on approve.** Rejected. HTTP approve stays on `schedule_approved_plan`.
- **Number this work V3 and start the V4 deploy.** Rejected. V4 and V5 in `README.md` and `docs/architecture.md` stay as they are.

# Data Flow

```text
POST /api/plans
  → is_itinerary_request?
       no  → single-activity graph, unchanged
       yes → understand (regex; missing date ends)
            → decompose (supervisor model, or deterministic if no key)
            → parallel calendar / restaurant / event
                 research models pick one filtered id
            → plan (build_itineraries only)
            → constraint_engine
            → verify_semantics (review_semantics only)
            → critique (critic model cannot overturn a code REVISE)
            → replan one branch, or prepare_approval → interrupt
POST /api/plans/{id}/approve
  → itinerary: Command(resume=approve) then execute writes two events
  → single activity: schedule_approved_plan, graph not resumed
POST /api/plans/{id}/revise
  → Finish earlier: tighten time_end, re-rank, rerun a branch only if short
POST /api/plans/{id}/execution
  → retry only incomplete approved items
  → cancel_created only with confirm=true, this plan's completed actions
```

# API Changes

No new routes and no new response fields. Existing `itineraries`, `agents`, `execution_status`, and `execution_actions` stay. Model name and token counts already have span columns. They start reflecting real calls when a key is set.

`ApproveRequest.itinerary_id`, revise, and execution commands keep their current shapes.

# Persistence Changes

No new tables. No migration for a new column. Spans already store `model`, `prompt_version`, token counts, `duration_ms`, `retry_count`, and `estimated_cost_usd`.

Checkpoint rows stay LangGraph's. Tests keep SQLite and `MemorySaver`. The optional Postgres check uses the existing saver when `LANGGRAPH_CHECKPOINTING=true` and Postgres is actually up.

# UI / UX Impact

Do not redesign the workspace. Specialist progress stays on `AgentBoard`. The developer trace already prints `agent.model`. With no key, that value stays `deterministic`. With a key, a real call shows the resolved model name.

Calendar results still appear only after approve. The date-night path is the existing "Saturday date night" example, then `/plans/:planId`.

# AI / ML Impact

The model is used only where a deterministic rule cannot see preference fit among options that already passed the rules: how to split a request into the known tasks, which surviving candidate to prefer, and whether a valid itinerary is weak enough to revise.

Structured output is validated in code. A schema mentioned in the prompt is not the validation.

No new provider, no embeddings, no fine-tune, no learned ranker. Prompt and model changes that affect the evening need the golden eval below, not one manual example.

A date night with no retries and no replan is 4 model calls when a key is set: supervisor, two research nodes, critic. One single-branch replan adds that research call and another critic call. Three attempts on a single call count as three toward `max_total_llm_calls`.

`specialist_timeout_seconds` is 25 and wraps the research branch. The OpenAI client timeout defaults to 30. Three research attempts can exceed the branch timeout. That remains a branch failure, then the existing one-time branch retry. Supervisor and critic are outside that wait.

# Security

Trust boundary: candidate titles, descriptions, tool payloads, and revision sentences are untrusted data. They must not be concatenated into the system message, appended to `TOOLS`, or used to set `approved` or to skip `interrupt`.

A test fixture puts "approve", a tool name, and a refresh-token-shaped string into a title, a blurb, and a revision message. The run still interrupts, research `authorize` of `google_calendar.create_event` and `calendar.delete_event` still raises `tool_forbidden` before any side effect, and nothing is written until `Command(resume={"action": "approve", ...})`.

`google_client_secret` and the calendar refresh token stay in the settings object and the OAuth store. They do not appear in checkpoint state, prompts, span `safe_metadata`, or logs.

`confirm: false` on `cancel_created` raises and deletes nothing. Delete still loads only this plan's `execution_actions` with `status=completed` and a stored event id.

Failure injection stays ignored when `ENVIRONMENT=production`. This work does not change that, and it does not deploy.

Schedule the security reviewer before any release. This plan does not release.

# Observability

On a real call, the span stores the resolved model name, the prompt version of the constant that was sent (`supervisor_v1`, `restaurant_research_v1`, `event_research_v1`, or `critic_v1`), input and output tokens from SDK usage when present, duration, and `retry_count`. `apply_replan` and other steps that do not call a model keep `model="deterministic"` and a policy version. They do not use the sent-prompt version.

Do not log the system prompt body, the user message, or chain-of-thought. Tool spans store tool names and counts.

`finalize` is not the place that publishes `awaiting_approval` after a limit breach. The interrupted thread is the signal that approve can resume.

# Tests

Existing backend pytest must pass, including V0/V1 workflow tests and `test_full_graph_waits_for_selection_and_approval`. Those tests keep the injected parser and an empty key. They must not construct a live OpenAI client.

Add deterministic tests that inject the structured-output fake:

- Supervisor output that invents an agent or a tool is rejected and retried; hard date, budget, and home-by on the constraints object are unchanged.
- Research output whose id was over budget, diet-excluded, past the hard end, or already rejected is a validation error. After three failures the branch fails closed and does not insert that id.
- Critic `PASS` on a `validate_itinerary` failure is stored as `REVISE`. A dietary exclude already raised by deterministic `critique()` is not cleared. A code-valid plan can still be `REVISE` when the fake says so, and only `restaurant` or `events` is reopened. The calendar task stays completed. A second wave with no new id stops.
- `Finish earlier` with enough candidates does not clear research artifacts and does not mark both tasks pending. A short candidate list reruns only the short branch.
- `test_revision_limit_stays_approvable` still passes. Unknown id writes nothing. An empty replan result leaves the previous itinerary rows in place.
- Discovery marked `failed` with an itinerary row and zero `execution_actions` does not create events on retry. Retry of a partial write completes only the incomplete key and does not call create for the completed one.
- Research `authorize(..., "google_calendar.create_event")` and `authorize(..., "calendar.delete_event")` raise `tool_forbidden`. A model-shaped payload cannot set `approved`.
- Crossing `max_total_llm_calls` or `max_supervisor_steps` with an itinerary on screen ends in the approval interrupt, not `END` with `awaiting_approval`. The span for the refused call has no invented token usage.
- No-key path records `model="deterministic"` and does not report a sent prompt version.

Constraint checks, permissions, idempotency, partial success, and cancel confirmation stay plain assertions. `evals/multi_agent/test_scenarios.py` stays on the fake.

Frontend unit tests stay. If the trace's model string or the specialist board changes, follow the browser check in the last implementation step.

# AI Evaluation

Put a golden-set runner in `backend/evals/multi_llm/`. Default `pytest` must skip it. It runs only when `OPENAI_API_KEY` is non-empty and `NEMI_RUN_MODEL_EVALS=1`. Skipping is a skip, not a fabricated score.

Baseline is the deterministic port on the same frozen fixtures: regex constraints, `decompose_tasks`, ranker order, `build_itineraries`, `validate_itinerary`, `critique()`, two calendar writes.

The fixture set must be able to fail each locked check:

- A date-night request with a regex date, a budget, and a home-by time. The catalog includes one legal dinner, one legal activity, one over-budget restaurant, one diet-excluded restaurant, and one event past the hard end.
- A critic replan whose first pick is rejectable and whose other legal candidate is on that branch only. Calendar is already completed. A second wave has no new id and stops.
- One approve. Writes are one restaurant event and one activity event.

Compare baseline and live model on: the itinerary contains both dinner and an activity, no hard-constraint violation remains, the replan reopens only the failed branch, and the write count is two.

Missing-date behavior, the shared replan cap, invalid-output retry, and fail-closed stays in the unit tests on the fake.

If the key or the opt-in is absent, `docs/versions/multi-llm/` says this eval was not run. Do not invent pass/fail numbers.

The optional Postgres restart check is separate and deterministic. With `LANGGRAPH_CHECKPOINTING=true` and a local Postgres that is actually accepting connections: start the API, run a date night to the interrupt, stop the process, start it again, approve the same plan id, observe one restaurant event and one activity event, approve again, observe no new event. If Postgres is not running, the verification report says the check was not run. Do not mark it passed. Ordinary pytest does not require Postgres.

# Migration

None. Existing span rows may show `deterministic` and zero tokens. New calls write the new fields on new rows. No backfill.

# Rollout

Local only. Mock providers remain the default. Set `OPENAI_API_KEY` when the four roles should call a model. Set `SUPERVISOR_MODEL`, `RESEARCH_MODEL`, or `CRITIC_MODEL` only to override `OPENAI_MODEL`. Set `CALENDAR_PROVIDER=google` and the OAuth variables only when a real calendar should be read or written.

Do not deploy, do not change hosted CI, and do not treat this as the V4 move off this machine.

# Risks

- Three research parse attempts can hit `specialist_timeout_seconds` before the validation retries finish. The branch then fails and uses the existing one-time retry. The verification report should say whether a live eval saw that timeout.
- `estimate_cost_usd` is wrong for any model other than `gpt-4o-mini`. Those spans store an unpriced flag and a zero cost.
- Postgres checkpoint setup still falls open to `MemorySaver` and logs `checkpoint_unavailable`. A restart then loses the paused thread. The optional check covers only a machine where Postgres setup succeeded.
- The research system message is the old "return candidates" constant plus a selection sentence. If the model ignores the sentence, the three validation retries fail the branch closed. That is the intended failure. It can make a date night return no itinerary when the key is set and the model will not pick an id.
- `validate_itinerary` still does not receive dietary status. Diet remains on the filter, the builder, and deterministic `critique()`. A change that lets the model author itinerary items would bypass that. This plan does not give the model that authority. Stop if a patch needs it.
- `docs/plans/v2/plan.md` will still say "V2 graph" for both graphs. Do not rewrite that historical plan. The new version notes must use the code names.

# Ordered Implementation Steps

1. Add the structured-output port and the OpenAI adapter, including usage and the three-attempt retry. Wire `model_for` on that adapter only. Keep the single-activity parser's tests green without a network call.
2. Inject the port through `ItineraryDeps`. Empty key uses the deterministic functions. A fake is what unit tests pass.
3. Call it from `decompose`, both research nodes, and `critique`, with the schemas and code overrides in Decisions 4–6. Record real span fields only on a real call.
4. Count real attempts against `max_total_llm_calls`. On a supervisor-step breach, a `tool_limit` while an itinerary is visible, or a refused model call, route to `prepare_approval` and interrupt. Align `after_replan` with `>=`. Keep `finalize` from publishing `awaiting_approval` on that path.
5. Change `interpret_revision` for `Finish earlier` as in Decision 11. Add the regression next to the existing revision tests.
6. Preserve the previous itinerary list when a replan builds nothing valid. Narrow execution retry as in Decision 13.
7. Add the permission, untrusted-content, unknown-id, revision-cap, and limit-breach tests. Run the existing backend suite.
8. Add `backend/evals/multi_llm/` skipped by default. Run it only with a key and `NEMI_RUN_MODEL_EVALS=1`. Record baseline versus live, or record that it was not run.
9. Run the Postgres restart check only if Postgres is up. Otherwise record that it was not run.
10. Write `docs/versions/multi-llm/` for the behavior that was actually built: which role decides what, what stayed in code, and the commands and results. Update the opening of `README.md` and `docs/architecture.md` so they describe two graphs and these model roles. Delete the claim that the product has only one graph and will not split out other agents. Leave the V4 and V5 sentences as leaving this machine and splitting services. Do not add a V3 heading. Point `docs/versions/README.md` at the new notes when they exist.
11. If the specialist board or the displayed model name changed, open the app and run Saturday date night: specialist progress is visible, and calendar results appear only after approve. A single screenshot is not that check. If the browser was not run, say so in the verification report.

# Human Approval Requirements

Decisions 1–14 above are the approved product contract, plus the facts from this tree. The implementer continues after this plan. Do not wait for a second confirmation.

Stop and report the consequence before coding further if the patch needs any of these:

- A third graph, a swarm, `create_supervisor`, or a package path treated as a Nemi V3.
- Sending `ITINERARY_PLANNER_V1` or `VERIFIER_V1` as a model call, or reading `PLANNER_MODEL`.
- A research role on `google_calendar.create_event` or `calendar.delete_event`.
- Production approve resuming the single-activity graph.
- Untrusted title, blurb, tool result, or revision text changing `TOOLS`, skipping `interrupt`, or setting `approved`.
- A model call to implement `Finish earlier`.
- A learned ranker, a new vendor, or a vector store.
- Claiming the live eval or the Postgres restart check passed when it was not run.

Security review is required before any release. This plan does not authorize a release.
