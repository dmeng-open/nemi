# Execution safety

Writes happen in the execution node after `human_approval` resumes with `action=approve`. Research nodes cannot call the create tool. `authorize` raises if they do.

## What gets written

For the approved itinerary, Nemi creates:

- one calendar event for the restaurant block
- one calendar event for the activity block

Travel and buffer items stay on the itinerary card. They are estimates, and they are not separate calendar events.

Each item uses `make_idempotency_key(plan_id, item_id, "create_event")`. The item id is stable for that itinerary and candidate. A second approve sees plan status `scheduled` and returns. If a create races, the provider returns the original action. Local and Google providers both replay a completed key.

Before a new key is inserted, execution reads the calendar again and refuses the item when it overlaps. A conflict does not mark the key completed, so a later retry can succeed after the overlap is gone.

## Partial failure

Items are written one at a time. If the activity write fails after dinner succeeded:

- status is `partial_success`
- the response lists each item as completed or failed
- the UI does not say the evening was fully scheduled

`POST /api/plans/{id}/execution` with `action=retry` runs only items that do not already have a completed action. Completed keys replay.

`action=keep` records that the person accepted the partial schedule. Status stays `partial_success`.

## Compensation

Nemi does not delete calendar events on its own.

`action=cancel_created` requires `confirm: true`. The execution path may then call `calendar.delete_event`, which is `WRITE_SENSITIVE`. It deletes only events created for this plan. A missing confirm is rejected and nothing is deleted.

Google delete uses the Calendar API `DELETE` for the event id stored on the action (the same id used as the Google event id at insert). Local delete removes the `local_calendar_events` row. Neither path deletes unrelated personal events.

Future tools such as `ticket.purchase` and `restaurant.reserve` are specified as `WRITE_SENSITIVE` and are not implemented.

## Approval and restart

The graph interrupts before execution. The checkpointer is the process `MemorySaver` in tests and on SQLite. With Postgres and `LANGGRAPH_CHECKPOINTING=true`, the API uses LangGraph’s Postgres saver and calls `setup()` at startup so the paused thread survives a restart. Approve sends `Command(resume={"action": "approve", "itinerary_id": ...})` on thread id = plan id. Research nodes do not run again for that resume.

If the Postgres saver cannot start, the API logs `checkpoint_unavailable` and uses memory. Itinerary rows are still in the application database, but a restart would not resume the thread.

## Human gate

Decline resumes the thread with `action=cancel` and writes nothing. Closing the confirmation on a single-activity plan is unchanged and still does not resume a graph.
