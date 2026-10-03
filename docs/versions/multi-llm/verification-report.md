# Verification

The evening model roles were checked with the backend suite and an empty OpenAI key. This is not a release and it is not a security review.

## Commands

Working directory `backend`, with `OPENAI_API_KEY` and `NEMI_RUN_MODEL_EVALS` empty for pytest:

- `.\.venv\Scripts\python -m pytest -q --tb=line` with `OPENAI_API_KEY` and `NEMI_RUN_MODEL_EVALS` empty — 138 passed, 4 skipped in 68.63s. This run includes the closed supervisor and research schemas.
- `.\.venv\Scripts\python -m ruff check app/agents/itinerary/engine.py app/agents/itinerary/graph.py app/agents/itinerary/routing.py app/agents/itinerary/judgments.py app/agents/itinerary/structured_output.py tests/test_itinerary_roles.py tests/test_structured_output_port.py evals/multi_llm` — all checks passed.

The 4 skips are the golden package. Its skip reason is unchanged: "Live multi-LLM golden eval was not run. It runs only when OPENAI_API_KEY is non-empty and NEMI_RUN_MODEL_EVALS=1. This skip is not a pass or fail score." A separate `evals/multi_llm` invocation was not run again after this suite.

`evals/multi_agent/test_scenarios.py` ran inside the full suite and passed. It was not edited.

## Live golden eval

Not run. No score was produced. The runner is pointed at `app.agents.itinerary.structured_output.StructuredOutputPort` and the schemas in `app.agents.itinerary.judgments`. It stays skipped unless the key is non-empty and `NEMI_RUN_MODEL_EVALS=1`.

## Postgres restart check

Not completed. Not a pass.

`127.0.0.1:5432` was already accepting connections. The app settings point at database `nemi`, and `select 1` succeeded. Postgres was not installed or started for this check.

`uvicorn app.main:app` on this Windows machine logged `checkpoint_unavailable` and fell open to `MemorySaver`. Psycopg cannot use the Proactor event loop. Starting the same app with a selector event loop did not log `checkpoint_unavailable`.

A date-night `POST /api/plans` then returned 202 for plan `11e90409-2b19-4cc6-a893-4a2d94556865`. Discovery did not reach approval. The log reported `relation "agent_spans" does not exist`, and a following GET reported `relation "itineraries" does not exist`. The process was stopped. Approve, the second approve, and the calendar counts were not run.

The provider overrides for that attempt were mock events, mock places, and the local calendar, so the attempt would not write to Google Calendar. `OPENAI_API_KEY` was blank for the process, so the call was not a live model run. The machine's saved `.env` still selects Google Calendar and Ticketmaster; those values were not changed.

## Browser

Not run. The specialist board and the displayed model string were not changed. With no key, stored spans stay `model=deterministic`. With a key, a real call stores the resolved model name on the existing span field.

## What the suite covers

The tests inject a fake port. They fail if an invented supervisor agent is kept, if an illegal research id is inserted, if a code `REVISE` is cleared, if Finish earlier reopens both branches when only one is short, if a placeable non-first `selected_id` is not the first itinerary, if a failed Finish-earlier rerun drops the previous constraints or itinerary rows, if a limit breach with an itinerary on screen ends instead of interrupting, or if a poisoned title or revision sets `approved` before `Command(resume={"action": "approve"})`. `test_revision_limit_stays_approvable` passed in the full suite.

Ordinary pytest did not call OpenAI and did not construct a live client. `backend/tests/conftest.py` still sets an empty key on the test `Settings` object.
