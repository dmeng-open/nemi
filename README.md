# Nemi

Nemi is a personal planning agent. You describe an afternoon or a meal. Nemi turns that into constraints, checks a local calendar, searches activities or restaurants, ranks the options, and waits for an explicit yes before it writes anything down.

V0 is a local product. OpenAI does the language work. Events, restaurants, and the calendar are local providers, so the loop runs without Ticketmaster, Google Places, or Google Calendar credentials.

## Product vision

Nemi is not a general chatbot. The loop is fixed:

understand the request, load preferences, check the schedule, search, rank, verify, recommend, ask, then write one calendar event.

Two kinds of plan are supported:

- **Events.** “Find me something interesting to do Saturday afternoon. I like tech, food and live music. Keep it under $50 and within 20 minutes.”
- **Restaurants.** “Find me a Japanese restaurant Friday after work. Budget around $50. Nothing too far away.”

Restaurant booking and ticket purchase are out of scope. After you approve, Nemi adds the plan to a local calendar and gives you an `.ics` file you can import into Google Calendar, Apple Calendar, or Outlook.

## Screenshots

The interface is a calm workspace: a composer, an activity timeline driven by stored workflow events, three recommendation cards, and an approval step before anything is written.

Capture these locally after `npm run dev` and the API are running:

1. The new-plan composer at `http://127.0.0.1:5173`
2. The recommendation workspace after a Saturday request
3. The approval panel
4. The scheduled state with **Add to calendar**

## Architecture

Details, diagrams, and the decisions that should stay put live in [docs/architecture.md](docs/architecture.md). The phase checklist is [docs/plans/v0-plan.md](docs/plans/v0-plan.md).

```text
React (Vite)  →  FastAPI  →  LangGraph
                    │            ├─ OpenAI, for parsing and explanations
                    │            ├─ EventProvider / RestaurantProvider
                    │            ├─ CalendarProvider
                    │            └─ CandidateRanker
                    └─ PostgreSQL
```

The graph is one state machine. It does not spawn other agents. Calendar conflict checks, prices, distances, dates, and sort order are ordinary code. The model classifies the request and writes the short “why this” lines. It does not reorder the ranked list.

Human waits are rows in Postgres (`awaiting_selection`, then `awaiting_approval`). A calendar write requires `approved=true`. Doing it twice uses an idempotency key and creates one event.

## Technology

| Area | Choice |
| --- | --- |
| Frontend | React, TypeScript, Vite, React Router, Tailwind, TanStack Query, React Hook Form, Zod |
| Backend | Python 3.12+, FastAPI, Pydantic v2, LangGraph, SQLAlchemy 2, Alembic |
| Data | PostgreSQL |
| Language model | OpenAI structured output |
| World data | `MockEventProvider`, `MockRestaurantProvider`, `LocalCalendarProvider` |

Kafka, Kubernetes, PyTorch, and cloud infrastructure are not part of V0. The provider and ranker interfaces are the seams for them later.

## Local setup

Requirements: Docker, Node.js, and Python 3.12 or newer. This repo was exercised on Python 3.14.

From the repository root:

```powershell
Copy-Item .env.example .env
# Put your key in .env:
# OPENAI_API_KEY=sk-...

docker compose up -d
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`. API docs are at `http://127.0.0.1:8000/docs`.

| Service | URL |
| --- | --- |
| React | http://127.0.0.1:5173 |
| FastAPI | http://127.0.0.1:8000 |
| PostgreSQL | localhost:5432, database `nemi`, user and password `postgres` |

The Vite dev server proxies `/api` and `/health` to FastAPI.

On a machine with `make`, `make db-up`, `make migrate`, `make backend`, and `make frontend` do the same jobs. Windows without `make` can use the PowerShell commands above.

### OpenAI

`OPENAI_API_KEY` is the only secret V0 needs. The default model is `gpt-4o-mini`. Parsing uses structured output and retries a bad response up to three times. If the day or the plan type is still missing, Nemi asks one question instead of inventing it.

Explanations use the model when a key is present, and fall back to a factual template if that call fails. The ranking order does not change.

### PostgreSQL

`docker compose up -d` starts Postgres 16 and keeps the data in a named volume. `GET /health` checks the process. `GET /health/db` checks the database.

### Migrations

```powershell
cd backend
.\.venv\Scripts\python -m alembic upgrade head
```

### Tests

```powershell
cd backend
.\.venv\Scripts\python -m pytest

cd frontend
npm test
```

Backend tests cover date resolution, budget phrasing, calendar conflicts, ranking weights, the discovery workflow against the mock catalogs, the approval gate, idempotent calendar writes, empty results, provider failure, `.ics` contents, and the full LangGraph interrupt path. They use a fixed parser so they do not call OpenAI. Frontend tests cover the composer, the timeline, candidate cards, approval, and the scheduled state.

### Demo mode

The defaults are:

```env
EVENT_PROVIDER=mock
PLACE_PROVIDER=mock
CALENDAR_PROVIDER=local
```

OpenAI, the graph, the API, the database, and the UI are real. The catalogs are deterministic seed data around a demo neighborhood, not live city data. Travel times are estimates from that neighborhood, not from your GPS.

`Integrations` can add a sample Saturday gym session and dinner so conflict removal is visible. V0 has one local user and no login. Do not expose port 8000 beyond your machine.

## Provider architecture

`EVENT_PROVIDER`, `PLACE_PROVIDER`, and `CALENDAR_PROVIDER` choose the implementation. `mock` and `local` are implemented. `ticketmaster`, `google` (places), and `google` (calendar) are registered and fail with a clear unavailable error. They do not call those APIs.

`CandidateRanker` is implemented by `HeuristicRanker`. A later model ranker can replace it without changing the graph. Weights default to preference 0.35, schedule 0.25, distance 0.15, price 0.10, quality 0.15, and must sum to 1.

## Current limitations

- No accounts. Every row belongs to the seeded local user.
- No live events, places, or Google Calendar. Export is an `.ics` file.
- No ticket purchase and no restaurant reservation.
- “Around $50” becomes a ceiling of 1.2× that amount. “Under $50” stays at 50.
- Dates are interpreted in `APP_TIMEZONE` (default `America/Chicago`).
- The discovery run is in-process. Poll `GET /api/plans/{id}` while it works.
- Chain-of-thought is not stored or shown. The timeline is operational events only.

## Future roadmap

Documented only. Not built.

**V1.** Ticketmaster, Google Places, and Google Calendar OAuth behind the existing provider interfaces.

**V2.** Train on `recommendation_candidates` and `interaction_events`. Keep the heuristic as the baseline and add another `CandidateRanker`. Measure Recall@K and NDCG@K before treating a model as the ranker.

**V3.** Publish the interaction topics (`recommendation.shown`, `plan.scheduled`, and the rest) when a second consumer exists. The table is already shaped for that. Kafka is not justified before then.

**V4.** Managed Postgres, object storage, images, and secrets when the app leaves one machine.

**V5.** Separate services only when their scaling or release needs diverge.

## Engineering workflow

How this repository is changed is separate from the product. See [AGENTS.md](AGENTS.md).
