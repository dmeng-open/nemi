# Nemi

Nemi is a personal planning agent. You describe an afternoon, a meal, or an evening that needs both. A single activity or meal becomes constraints, a calendar check, a search, a ranked shortlist, and a wait for an explicit yes before anything is written. A multi-part evening is planned as an itinerary: calendar, restaurants, and activities are researched in parallel, then checked against your budget, diet, and the time you need to be home.

The default local product uses OpenAI for language and mock providers for events, restaurants, and the calendar, so the loop runs without Ticketmaster, Google Places, or Google Calendar credentials. Those providers can be turned on with environment variables. Setup is in [docs/versions/v1/integrations.md](docs/versions/v1/integrations.md). Google Calendar setup is in [docs/versions/v2/google-calendar.md](docs/versions/v2/google-calendar.md). Plans written before implementation are in [docs/plans](docs/plans/README.md). What each version does after it shipped is in [docs/versions](docs/versions/README.md).

## Product vision

Nemi is not a general chatbot. A single activity or meal still follows one loop:

understand the request, load preferences, check the schedule, search, rank, verify, recommend, ask, then write one calendar event.

A multi-part evening uses a supervisor and specialist agents. The person sees the plan being built, then approves a whole itinerary before calendar events are created.

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

Details, diagrams, and the decisions that should stay put live in [docs/architecture.md](docs/architecture.md). Plans are in [docs/plans](docs/plans/README.md). Shipped behavior is in [docs/versions](docs/versions/README.md).

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

`EVENT_PROVIDER`, `PLACE_PROVIDER`, and `CALENDAR_PROVIDER` choose the implementation. `mock` and `local` do not need API keys. `ticketmaster`, `google` places, and `google` calendar call those services when selected. A missing key or a disconnected Google Calendar does not fall back to demo results.

`CandidateRanker` is the protocol. `HeuristicRanker` is the only implementation. Weights default to preference 0.35, schedule 0.25, distance 0.15, price 0.10, quality 0.15, and must sum to 1.

## Current limitations

- No accounts. Every row belongs to the seeded local user.
- Live events, places, and Google Calendar are optional. The defaults stay mock and local. Export is still an `.ics` file.
- Google refresh tokens are stored in Postgres as plaintext behind `OAuthConnectionRepository`. That is a local V1 choice, not production encryption.
- No ticket purchase and no restaurant reservation.
- “Around $50” becomes a ceiling of 1.2× that amount. “Under $50” stays at 50.
- Dates use the preference timezone when one is saved, otherwise `APP_TIMEZONE` (default `America/Chicago`).
- The discovery run is in-process. Poll `GET /api/plans/{id}` while it works.
- Chain-of-thought is not stored or shown. The timeline is operational events only.

## Roadmap

**V0.** Local demo loop. See [docs/plans/v0/plan.md](docs/plans/v0/plan.md).

**V1.** Ticketmaster, Google Places, and Google Calendar behind the existing provider interfaces. See [docs/plans/v1/plan.md](docs/plans/v1/plan.md) and [docs/versions/v1/integrations.md](docs/versions/v1/integrations.md).

**V2.** Hierarchical planning for multi-part evenings: parallel research, itinerary cards, a deterministic constraint check, targeted replans, and calendar writes only after the graph resumes. The plan is [docs/plans/v2/plan.md](docs/plans/v2/plan.md). The shipped design is [docs/versions/v2/multi-agent-architecture.md](docs/versions/v2/multi-agent-architecture.md). Interaction topics stay in Postgres until a second consumer exists. Kafka is not part of this version.

**V3.** Train on `recommendation_candidates` and `interaction_events`. Keep the heuristic as the baseline and add another `CandidateRanker`. Measure Recall@K and NDCG@K before treating a model as the ranker. Not built. See [docs/plans/v3/README.md](docs/plans/v3/README.md).

**V4.** Managed Postgres, object storage, images, and secrets when the app leaves one machine.

**V5.** Separate services only when their scaling or release needs diverge.

## Engineering workflow

How this repository is changed is separate from the product. See [AGENTS.md](AGENTS.md).
