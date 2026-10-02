# Nemi V0 plan

Local planning agent. OpenAI for language, mock providers for the world, PostgreSQL for memory, one LangGraph workflow, one React app.

- [x] Phase 1 — Repository scaffold
- [x] Phase 2 — React UI shell
- [x] Phase 3 — FastAPI, database, and domain layer
- [x] Phase 4 — Mock providers and local calendar
- [x] Phase 5 — Heuristic ranking
- [x] Phase 6 — OpenAI constraint parsing
- [x] Phase 7 — LangGraph discovery workflow
- [x] Phase 8 — Frontend and backend integration
- [x] Phase 9 — Selection and approval
- [x] Phase 10 — Calendar execution and idempotency
- [x] Phase 11 — `.ics` export
- [x] Phase 12 — Persistence and recent plans
- [x] Phase 13 — Backend and frontend tests
- [x] Phase 14 — UX polish, errors, dark mode, responsive layout
- [x] Phase 15 — README and finish documentation

## Notes

- Phase 1 is the runnable skeleton: Compose Postgres, FastAPI health, Vite React app, env example.
- The UI is the real product shell. Component tests render the composer, timeline, cards, approval, and success state with fixtures. The pages talk to the API.
- Discovery, ranking, conflict removal, the approval gate, and idempotent calendar writes are covered by pytest against SQLite and the mock catalogs. Those tests use a fixed parser so they do not call OpenAI.
- The OpenAI parser and explainer are wired for a configured `OPENAI_API_KEY`. A missing key stores `openai_unconfigured` instead of inventing a plan.
- `GET /health` and `GET /health/db` are the process and database checks. Alembic revision `ad1a206d0e8d` is the initial schema.
- Selection and approval are API transitions over Postgres. The same graph also contains the wait nodes and is resumed in the interrupt test.
- Calendar creation refuses to run unless the plan is approved. A second approve returns the original event.
