# V2 plan — hierarchical planning

## Goal

Nemi can turn a multi-part request into a small set of complete itineraries, check them with deterministic rules, revise only the broken part, wait for an explicit yes, and then write the approved blocks to the calendar.

## User outcome

A person can say they want dinner and something afterwards, with a budget, a dietary limit, and a time they need to be home. Nemi shows which specialists ran, then offers whole-evening plans. Nothing is written until they approve one plan. Approving twice does not create a second copy.

## Non-goals

- Retrieval, embeddings, pgvector, or a memory agent
- Learned ranking, PyTorch, LightGBM, or XGBoost
- Kafka, Spark, AWS, Kubernetes, or a feature store
- Ticket purchase or restaurant reservation
- Automatic deletion of calendar events

Single-activity requests (“find a workshop Saturday afternoon”, “find a Japanese restaurant Friday”) stay on the existing V2 graph: one ranked shortlist, selection, then one calendar event. That path is the regression contract.

## Facts

- V2 is one LangGraph in `backend/app/agents/graph.py`. Nodes parse, load preferences, read the calendar, search either events or restaurants, rank, verify, recommend, then interrupt for selection and approval.
- Production approval does not resume that graph. `PlanningOrchestrator.approve` writes the calendar after the plan row is `awaiting_approval`.
- `compile_planning_graph` is what `test_full_graph_waits_for_selection_and_approval` drives. It must keep the same node names and interrupt behavior.
- Providers already normalize Ticketmaster, Google Places, and Google Calendar into `Candidate` and `CalendarEvent`. Google OAuth and idempotent create already exist.
- The client polls `GET /api/plans/{id}` while status is `processing`. Workflow events are committed as they are written.
- Tests use SQLite. Postgres checkpointing cannot be the thing those tests depend on.
- The mock Saturday catalog is mostly afternoon. An evening jazz listing was added so a “free after 5 PM, home by 11” request can pair dinner with a real catalog event. Prices and times come from that catalog, not from a scripted dollar amount.

## Assumptions

- One local user remains the tenant. Itinerary rows use the same `user_id` as planning sessions.
- “Reasonable travel” with no number means the saved travel limit, or 30 minutes, with a hard cap 15 minutes above that.
- Travel minutes between two stops are a labeled estimate: the average of the two catalog travel times. This is not a routing API.
- The default OpenAI model is enough for every agent. Per-agent model settings exist so that can change without a rewrite.
- Coordination rules that are known (which specialist to call, whether two times overlap, whether a total exceeds the budget) stay in code. The model is not asked those questions.

## Decisions

1. **Two graphs.** Multi-part text runs the V2 root graph. Everything else runs the single-activity graph unchanged. Type 1 for the public planning contract. Replacing that graph in place would change selection and approval semantics that the current API and tests depend on.
2. **Typed artifacts, not chat.** Specialists return pydantic models. No agent reads another agent’s prose.
3. **Parallel research.** Calendar, restaurant, and event tasks with no dependencies fan out with LangGraph `Send` and join before the planner. The supervisor does not search or write.
4. **Deterministic constraint engine.** Overlaps, windows, budget, order, duration, and the hard end time are code. The verifier and critic run after that and may send the plan back.
5. **Targeted replan.** A restaurant rejection marks the restaurant task pending and leaves a completed calendar task alone. The same cap covers critic replans and user revisions (`MAX_REPLAN_ATTEMPTS`, default 3).
6. **Interrupt before write.** The V2 graph pauses on `interrupt` after itineraries exist. Approve resumes that thread. Cancel resumes it with a cancel decision. Restart survival uses the same checkpointer: Postgres when the API is on Postgres and `LANGGRAPH_CHECKPOINTING` is true, otherwise in-memory for tests and SQLite.
7. **Calendar shape.** Approval creates one event per restaurant and one per event. Travel and buffer blocks are not written. Each write has its own idempotency key. A partial write is `partial_success` and is not described as fully scheduled.
8. **Deletes.** Nemi does not delete those events unless the person confirms `cancel_created`. The delete tool is `WRITE_SENSITIVE` and only the execution path may call it.
9. **No new ranker.** Restaurant and event research still use `HeuristicRanker` for ordering. The planner ranks complete itineraries with the constraint checks.

## Alternatives considered

- **Fold V2 into the root graph immediately.** One orchestration story, and a high chance of changing the three-card selection flow. Rejected for this version.
- **Supervisor as a free-form tool loop.** Harder to test, and it would put search tools on the coordinator. Rejected.
- **One calendar event for the whole evening.** Simpler writes, worse calendar conflict checks for the individual blocks. Rejected.
- **Server-sent events.** The poll already observes committed spans. A second stream is not required for the specialist checklist.

## Data flow

```text
POST /api/plans
  → if the text is multi-part, V2 graph
       understand → preferences → supervisor decompose
       → parallel calendar / restaurant / event
       → planner → constraint engine → verifier → critic
       → replan or interrupt
  → else V2 graph (unchanged)
GET /api/plans/{id} polls spans and, for V2, itineraries
POST /api/plans/{id}/approve resumes the V2 thread when plan_type is itinerary
POST /api/plans/{id}/revise resumes with a revision and invalidates one branch
POST /api/plans/{id}/execution retries, keeps, or cancels created events
```

## API

Existing plan routes stay. Additions:

- `ApproveRequest.itinerary_id` optional. Required in practice when several itineraries exist; the client sends the card the person approved.
- `POST /api/plans/{id}/revise` with `{ "message" }`.
- `POST /api/plans/{id}/execution` with `{ "action": "retry" | "keep" | "cancel_created", "confirm": bool }`. `cancel_created` requires `confirm: true`.

`PlanResponse` gains `itineraries`, `agents`, `execution_status`, `execution_actions`, and `limiting_constraint`. Omitted or empty on V2 plans.

## Persistence

New tables: `agent_threads`, `agent_tasks`, `agent_artifacts`, `agent_spans`, `itineraries`, `itinerary_items`, `execution_actions`.

LangGraph owns checkpoint rows when the Postgres saver is enabled. Nemi does not duplicate those rows in an application table.

`agent_runs` and `agent_run_events` stay the timeline source. Spans add agent name, model, prompt or policy version, token counts, tool names, and retry count. Prompts and chain-of-thought are not stored.

## UI

V2 screens stay. Multi-part plans show a specialist checklist, itinerary cards with constraint checks, revision prompts, and a collapsed developer trace (tokens and cost). Partial calendar writes offer retry, keep, and cancel.

## Security

- Google client secret stays on the server. The browser only receives the authorization URL.
- Tool use is an allow-list: research agents cannot create events. Only execution can call `google_calendar.create_event`. Only a confirmed execution command can call `calendar.delete_event`.
- Failure injection is ignored when `ENVIRONMENT=production`.
- User text is data for the parser and the revision interpreter. It does not grant tools.
- Spans store tool names and counts, not OAuth tokens or raw provider payloads.

## Tests

- Existing backend and frontend suites must pass.
- Reducer, routing, constraint, permission, fan-out, replan, and resume tests.
- `backend/evals/multi_agent/` covers the twelve scenarios in the V2 brief.
- Parallel speedup is measured in a test with delayed branches. It is not claimed from the diagram alone.

## Rollout

Local only. Set `CALENDAR_PROVIDER=google` and the OAuth variables when a real calendar should be read and written. Mock providers remain the default. See [Google Calendar](../../versions/v2/google-calendar.md).

## Risks

- Postgres checkpoint setup fails open to an in-memory saver if the checkpoint package or database is unavailable. A process restart then loses the paused thread. The plan row and itineraries still exist; approve would not resume. The API log line is `checkpoint_unavailable`.
- Mock catalog hours limit which real-world evenings can be demonstrated without Ticketmaster.
- Revision language is a small interpreter. Unrecognized text replans both research branches once, still under the replan cap.

## Ordered steps

The implementation follows the specialist modules under `backend/app/agents/v3/`, then persistence, the orchestrator branch, the React checklist and itinerary cards, then the evals.
