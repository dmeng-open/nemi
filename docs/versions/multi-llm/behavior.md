# Model roles on this machine

This note describes the evening graph after the supervisor, restaurant research, event research, and critic gained a model call. It is not a numbered product version.

Two graphs remain.

- A single activity or meal uses `compile_planning_graph` in `backend/app/agents/graph.py`. HTTP approve calls `schedule_approved_plan` and does not resume that graph.
- A multi-part evening uses `compile_itinerary_graph` in `backend/app/agents/itinerary/graph.py`. `is_itinerary_request` is the only switch. Approve resumes that thread with `Command(resume={"action": "approve", ...})`.

## What calls a model

The itinerary deps own `StructuredOutputPort` (`app.agents.itinerary.structured_output`). Tests pass a fake. A configured `OPENAI_API_KEY` uses `AsyncOpenAI`, `responses.parse`, `store=False`, and `max_retries=0`, with `settings.model_for(role)` on each call. `SUPERVISOR_MODEL`, `RESEARCH_MODEL`, and `CRITIC_MODEL` override `OPENAI_MODEL` for that role. `PLANNER_MODEL` is not read.

| Role | Node | System text | Schema |
| --- | --- | --- | --- |
| `supervisor` | `decompose` | `SUPERVISOR_V1` | Known task ids only: `calendar`, `restaurant`, `events`, `itinerary` |
| `research` | `restaurant_research` | `RESTAURANT_RESEARCH_V1` plus the selection sentence | `selected_id` |
| `research` | `event_research` | `EVENT_RESEARCH_V1` plus the selection sentence | `selected_id` |
| `critic` | `critique` | `CRITIC_V1` | `PASS` or `REVISE`, with an issue |

The selection sentence is code, not a new prompt version: the only legal field is `selected_id`, and the ids in the user message are the only legal values. Titles and descriptions stay in the user message.

A real call stores the resolved model name, the prompt version of the constant that was sent (`supervisor_v1`, `restaurant_research_v1`, `event_research_v1`, or `critic_v1`), token counts from SDK usage when present, duration, and `retry_count` (attempts minus one). `gpt-4o-mini` stores `estimate_cost_usd`. Any other model stores cost 0 and `safe_metadata.cost_unpriced`. Missing SDK usage stores zero tokens and `tokens_unreported`. Parse retries count toward `max_total_llm_calls`. They do not increment `supervisor_steps` and they are not tool calls.

## What stays in code

`ITINERARY_PLANNER_V1` and `VERIFIER_V1` stay in `prompts.py` and are not sent. `verify_semantics` still calls `review_semantics`. `HeuristicRanker` still supplies the scores. `build_itineraries` still sorts by that ranker and `_diverse`; it does not accept a model-authored itinerary. Meal length, travel estimates, and the two calendar writes stay in the engine and the executor.

The supervisor schema has no date, budget, or home-by field. Code overwrites `status`, `input`, `result`, `error`, `retryable`, and `retry_count`. An unknown task id, an agent/type mismatch, a missing required task, or a dependency outside the known set is rejected and retried. After three invalid attempts the step fails closed.

Research runs the existing filter and ranker first. Code accepts `selected_id` only when that id is still in the filtered list. Membership, dietary flags, scores, excluded candidates, and provider failures stay on the artifact. The model does not emit a new ranking. When the existing placement rules can build that dinner and/or activity, that card is first. The other cards stay in the ranker order produced by `_diverse`. If that candidate cannot be placed, `selected_id` is left as it was. An id that was over budget, diet-excluded, past the hard end, or already rejected is a validation error. After three failures that branch fails closed and does not insert the id.

The critic runs `validate_itinerary` and deterministic `critique()` first. A hard validation failure or a code `REVISE` is stored as `REVISE`. When code already says `REVISE`, its target wins. The model's target is used only when code had `PASS` and the model says `REVISE`, and only `restaurant` or `events` is kept. `calendar` is dropped. No itinerary means the critic model is not called. `CRITIC_REJECT` stays a local injection and does not call the model.

Research agents are not on `google_calendar.create_event` or `calendar.delete_event`. A write still happens only after `human_approval` resumes with `action=approve`.

## No key

An empty `OPENAI_API_KEY` does not construct a client. The four sites call `decompose_tasks`, the first ranked id, and `critique()` through the same port. That first ranked id uses the same placement rule as a model `selected_id`. Spans use `model=deterministic`, the existing policy version, and zero tokens. They do not record a sent prompt version, `tokens_unreported`, or `cost_unpriced`. Deterministic calls do not increment `max_total_llm_calls`.

## Finish earlier

The phrase is matched before the catch-all revision. Code subtracts 60 minutes from `time_end`, floored at `time_start` plus 90 minutes. It does not reject candidate ids, clear calendar, or reopen calendar. Surviving candidates are re-ranked, then `build_itineraries` runs.

If that build is non-empty, the on-screen itineraries are replaced, `replan_count` increments once, and the graph returns to approval without `Send`. If the window cannot shrink, nothing changes and `replan_count` does not increment. A branch is reopened only when the build is empty and that branch has no usable candidate: an event whose end still meets the hard end, or a restaurant that can hold a 90-minute dinner in the new window. If that rerun still yields nothing valid, the previous constraints and the previous itinerary list are restored, then approval.

## Limits and the previous itinerary

`after_replan` uses `>=` on `max_supervisor_steps`, same as `after_critic`. Each real HTTP attempt reserves one `max_total_llm_calls` slot before the attempt starts. The two research branches share that counter. The lock is released before the network wait. Crossing `max_total_llm_calls` or `max_supervisor_steps` with an itinerary on screen goes to `prepare_approval` and interrupts. `finalize` does not publish `awaiting_approval` on that path. A refused call records zero tokens and does not set `tokens_unreported`. A provider API error other than a timeout or a connection error becomes a local `model_request_failed` error. The adapter log line contains the role and that code, not the provider text, the system prompt, or the user message. A `tool_limit` on the first discovery still fails that branch. A `tool_limit` while an itinerary is already on screen does not clear it.

An empty or fully invalid replan puts the previous itinerary list back into state before save. `_replace_itineraries` does not delete saved rows when the new list is empty.

Execution retry, already in `compensation.py`, calls `schedule_block` only for restaurant or event items on the selected itinerary that already have an execution action and whose create key is not `completed`. There is no rank-0 fallback. Zero execution actions raises and does not write.

## Untrusted text

System text is only the prompt constant and, for research, the selection sentence. Titles, descriptions, tool results, and revision text stay in the user message or in state. They do not change `TOOLS`, skip `interrupt`, or set `approved`.
