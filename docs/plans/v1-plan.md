# Nemi V1 plan

Status: **approved** on 2026-10-02. The five Type 1 choices in Human Approval Requirements are accepted, including the recommended default that Connected omits the Google account email. Do not add `openid` or `email` scopes. Implement this plan. Do not redesign it.

This file is the implementation contract and the progress tracker. It was produced from repository exploration and specialist review. Recommendations are not approved decisions.

## Progress

| Step | Status |
| --- | --- |
| 1. Config and integration status | Done |
| 2. Ticketmaster provider | Done |
| 3. Google Places provider | Done |
| 4. Location and timezone | Done |
| 5. Google Calendar OAuth | Done |
| 6. Calendar read | Done |
| 7. Calendar write and idempotency | Done |
| 8. Graph wiring | Done |
| 9. Interaction events | Done |
| 10. Frontend | Done |
| 11. Tests | Done |
| 12. Docs | Done |

Baseline before this plan: backend pytest 27 passed, frontend Vitest 5 passed. Those runs did not cover the real provider stubs or the HTTP API.

## Goal

Replace the mocked Ticketmaster, Google Places, and Google Calendar providers with real HTTP implementations behind the existing provider seam, keep mock and local mode runnable with no credentials, and persist trustworthy interaction rows for a future ranker.

## User / Business Outcome

A person running Nemi locally can point events, restaurants, and calendar at Ticketmaster, Google Places, and Google Calendar, see real options for one saved home location, and approve one event onto that calendar. With the default `mock` / `local` settings, the current planning journey still runs with no API keys. Every shown, selected, explicitly rejected, and scheduled option leaves a stable row a later ranker can join. V1 does not buy tickets, book tables, or rank with a model.

## Current System

**Fact.** Nemi V0 is one FastAPI process, one Vite React app, and PostgreSQL. Discovery runs in LangGraph until recommendations exist. Selection and approval are HTTP transitions on the `planning_sessions` row. `PlanningOrchestrator.approve` calls `schedule_approved_plan`. The graph is not resumed on that HTTP path.

**Fact.** Providers are duck-typed. `backend/app/providers/factory.py` selects `MockEventProvider`, `TicketmasterEventProvider`, `MockRestaurantProvider`, `GooglePlacesProvider`, `LocalCalendarProvider`, or `GoogleCalendarProvider`. The three real classes raise `ProviderNotConfigured`. `httpx` is installed and unused. There is no Google client library.

**Fact.** `schedule_approved_plan` in `backend/app/services/calendar/scheduling.py` is typed to `LocalCalendarProvider`. Idempotency is the SHA-256 hex of `plan_id:candidate_id:create_event` (`backend/app/services/calendar/idempotency.py`). A schedule conflict is raised before the local insert, so the key is not consumed.

**Fact.** `EventCandidate.to_candidate()` and `RestaurantCandidate.to_candidate()` hardcode `source` to `mock_events` and `mock_restaurants`. Search queries have no city, latitude, longitude, or radius. `UserPreferences` has no home location or timezone. Planning uses `Settings.app_timezone`.

**Fact.** `interaction_events` exists. `_interact` writes `properties={}`. Topics already produced: `recommendation.shown`, `recommendation.selected`, `plan.cancelled`, `plan.approved`, `plan.scheduled`, `user.preference.updated`. `recommendation_candidates.rejected` is never set. `_persist` deletes and reinserts recommendation and candidate rows for the session.

**Fact.** `HeuristicRanker.rank(candidates, context)` is the only ranker. There is no `CandidateRanker` protocol in code. `docs/architecture.md` describes that protocol; the code does not. Weights are 0.35 / 0.25 / 0.15 / 0.10 / 0.15. Distance uses `estimated_travel_minutes`. Quality is `rating / 5`, or `0.5` when rating is missing. Verify drops `schedule_compatible is False` as `outside_window`, and `schedule == 0` as `conflict`.

**Fact.** One Alembic revision, `ad1a206d0e8d`. `GET /api/integrations` marks Ticketmaster, Google Places, and Google Calendar unavailable even when those settings are selected. The frontend has one planning journey, no OAuth, no location fields, and no provider label on cards. Routes are `/`, `/plans`, `/plans/:planId`, `/preferences`, `/integrations`, `/settings`.

**Fact.** `docs/plans/v0-plan.md` exists. `docs/v0-plan.md` does not. `.env.example` already names `TICKETMASTER_API_KEY`, `GOOGLE_PLACES_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REDIRECT_URI`. It has no `APP_BASE_URL`.

## Facts

- Work class: large, architecture-sensitive, UI, agent, and security-sensitive. Human plan approval is required before implementation. A security review is required before any release, because this change adds OAuth, stored refresh tokens, and external URLs.
- The local user remains `LOCAL_USER_ID` (`00000000-0000-4000-8000-000000000001`). There is no account system.
- Mock event distances are derived from the Chicago constants in `backend/app/integrations/events/mock.py` (`41.9214`, `-87.648`).
- `GET /api/plans/{id}/ics` currently requires `status == scheduled` and a `local_calendar_events` row.
- `ProviderNotConfigured` currently uses the code `provider_unavailable`.
- Approve writes both `plan_approved` and `plan_scheduled` on a successful, non-replayed write. Existing tests do not assert those topic names.
- `call_with_retries` retries a `ProviderError` up to 3 times only when `retryable` is true. It does not sleep.
- Places field mask is a Places API (New) requirement. Legacy Places does not use `X-Goog-FieldMask`.

## Assumptions

- V1 runs as one local process. An in-process cache is lost on restart and is not shared across processes. That matches the current single-process deployment.
- One Google connection per local user is enough. `oauth_connections.user_id` is unique.
- Ticketmaster Discovery API `events.json` and Places API (New) `places:searchText` are the upstream calls. No other Ticketmaster or Places products are in scope.
- One Places page (`pageSize` at most 20) is enough, because the UI shows three options.
- Google Calendar event ids accept the 64-character hex idempotency key. Hex `0-9a-f` is inside Google’s event-id alphabet, and 64 is inside the allowed length.
- Upstream ids fit `recommendation_candidates.candidate_id` (`String(160)`). A longer id is skipped and counted in the search log, not hashed.
- `calendar.events` does not return the Google account email. The recommended UI shows “Connected” without an email until the open question below is decided.
- Default urban speed `30` km/h is only a ranking input. It is not a claim about traffic.

## Constraints

- No PyTorch, Kafka, Redis, Kubernetes, AWS, ticket purchase, reservations, or a second ranker.
- No Google client library. Use `httpx.AsyncClient` for Ticketmaster, Places, and Google.
- Do not edit Alembic revision `ad1a206d0e8d`. Add a new revision only.
- Do not invent coordinates from a city name.
- Do not substitute mock results when a real provider is selected.
- Do not union local sample events into Google busy results.
- Do not log or return refresh tokens, access tokens, authorization codes, or raw upstream bodies.
- Places field mask is an explicit list, never `*`.
- `rank()` keeps the signature `(candidates, context) -> ranked`.
- No new routes in the React app. No visual redesign.
- The HTTP approval path stays `PlanningOrchestrator.approve`. It keeps calling `schedule_approved_plan`. It does not resume the graph.

## Invariants

- Mock event provider, mock restaurant provider, and local calendar still run when the corresponding secrets are empty.
- A conflict check that finds an overlap does not write a `calendar_actions` row and does not consume the idempotency key.
- Replaying a completed create returns the existing event with `replayed=True` and does not write a second interaction row.
- Calendar read failure during discovery does not fail the plan and does not look like an empty free calendar.
- Approve reads the calendar again before create. Disconnected, expired, or failed Google create leaves the plan `awaiting_approval` and creates no provider event.
- Interaction properties do not contain scores or score components.
- `recommendation.shown` for a candidate row is written once. Re-running discovery appends a new recommendation generation and leaves the previous rows in place.
- Rejecting one card sets `rejected=true` on that row only.
- OAuth `state` is single-use. The browser return target is a relative path on the allowlist.

## Proposed Design

### Type 1 recommendations (pending human approval)

These are not approved decisions.

#### 1. Location pause: `awaiting_location`

**Recommendation, Type 1 (plan lifecycle and public status).** Missing location does not fail the plan and does not call the provider.

| Provider mode | Missing input | `error_code` | Provider call |
| --- | --- | --- | --- |
| `event_provider=ticketmaster` | `home_city` blank | `city_required` | none |
| `place_provider=google` | `latitude` or `longitude` null | `location_required` | none |
| `event_provider=mock` or `place_provider=mock` | either | no gate | mock search runs |

Ticketmaster with a city and without coordinates still searches. Coordinates are sent only when both are saved. Places without coordinates does not search. The city string is never geocoded.

The same `planning_sessions.id` stays. `POST /api/plans/{id}/continue` is the resume. It is accepted only from `awaiting_location`. It clears the error, sets `processing`, and starts `run_discovery` on that id. It does not take a message and does not create a plan. `POST /clarify` stays the clarification path.

ADR outline, status `proposed`:

- Context: the UI needs the same plan to resume after Preferences is saved. A `failed` plan is a terminal error in the current client.
- Decision recommended: add `awaiting_location`.
- Alternative: `failed` plus `location_required`, which forces “Try again” and a new plan.
- Consequence: clients must understand one new status. Existing failed-plan behavior stays for provider and parse failures.
- Security: no new trust boundary. The continue call only re-runs discovery for the local user’s plan.
- Migration: status is a string column. No backfill.

#### 2. OAuth return path

**Recommendation, Type 1 (open-redirect control).** The callback redirects to a server-stored relative path, default `/integrations`. Allowed paths are only `/integrations` and `/plans/{uuid}` where that plan exists for the local user. Reject absolute URLs, scheme-relative URLs, backslashes, query strings, and fragments. The browser never chooses the redirect host. The host is `APP_BASE_URL`.

ADR outline, status `proposed`:

- Context: Connect started on a plan must return to that plan. An unchecked `return_to` is an open redirect.
- Decision recommended: store the path in `oauth_states` at connect time and allowlist it.
- Alternative: always redirect to `/integrations`.
- Security: state nonce is single-use and expires in 10 minutes. Tokens and the authorization code stay on the API response path and are not copied into the redirect URL.

#### 3. Refresh token storage

**Recommendation, Type 1 (secrets at rest).** New `oauth_connections` table behind `OAuthConnectionRepository`. Local V1 stores the refresh token in Postgres as plaintext. The repository is the only read path. Responses, logs, and interaction properties never include it. This is not production encryption. The port is the seam a later encrypting implementation can replace. Security review is required before release, not before this plan.

ADR outline, status `proposed`:

- Context: Google create and read need a refresh token after restart. The app is one local Postgres database and one local user.
- Decision recommended: plaintext column behind a repository.
- Alternative: OS keychain or application-level encryption now. That is a second secret-management design and is out of V1’s scope.
- Operational impact: anyone with database access can use the token. The API stays bound to localhost, as in V0.
- Migration: new table only.

#### 4. Explicit rejection

**Recommendation, pending approval (interaction contract).** A quiet “Not this” on a shown card, during `awaiting_selection`, sends `POST /api/plans/{id}/reject` with that card’s `candidate_id`. The handler sets `rejected=true` on that `recommendation_candidates` row and writes one `recommendation.rejected` event. It does not reject the other shown cards. A second call for the same row returns 200 and does not write another event. Rejecting the selected card clears the selection and returns the plan to `awaiting_selection`.

#### 5. Distance origin

**Recommendation, pending approval.** Mock providers keep their catalog distances and the Chicago demo origin. Real providers compute Haversine kilometers from saved `latitude` and `longitude` to the venue. A venue with no coordinates gets `distance_km = null` and `estimated_travel_minutes = null`. The ranker’s existing null distance score (`0.5`) applies. Real providers do not use `41.9214, -87.648`.

#### 6. Calendar scope

**Recommendation, Type 1 (OAuth scope).** Request only `https://www.googleapis.com/auth/calendar.events`. Do not add `calendar.readonly`, full `calendar`, or Gmail scopes. `prompt=consent`, `access_type=offline`, and `include_granted_scopes=false`.

### Type 2 choices (part of the same approval, not a second design pass)

**Choice.** OAuth paths:

- `POST /api/integrations/google/calendar/connect`
- `GET /api/integrations/google/calendar/callback`
- `DELETE /api/integrations/google/calendar/disconnect`

POST mints the nonce. GET is the browser callback. DELETE is idempotent and returns 204 when no row exists.

**Choice.** Add `CandidateRanker` as a `Protocol` whose only method is `async def rank(self, candidates: list[Candidate], context: RankingContext) -> list[RankedCandidate]`. `HeuristicRanker` is the only implementation. Put the protocol in `backend/app/domain/ranking.py`. Providers stay duck-typed.

**Choice.** Widen `schedule_approved_plan` to a `CalendarGateway` protocol in `backend/app/domain/calendar.py` with the current `get_events` and `create_event` signatures. `LocalCalendarProvider` and `GoogleCalendarProvider` already have those methods. This is one writer, used by the orchestrator and by the graph node.

**Choice.** Travel estimate constant in `backend/app/services/planning/geo.py`: `ASSUMED_URBAN_SPEED_KMH = 30`. Derived minutes are `max(1, round(distance_km / 30 * 60))`, and `travel_time_is_estimate=True`. Mock catalog minutes stay as given, with the flag false. No new ranker weight.

**Choice.** Google `priceLevel` maps to `price_min` for the existing price component. These are ranking bands, not menu prices:

| `priceLevel` | `price_level` | `price_min` |
| --- | --- | --- |
| `PRICE_LEVEL_FREE` | 0 | 0 |
| `PRICE_LEVEL_INEXPENSIVE` | 1 | 15 |
| `PRICE_LEVEL_MODERATE` | 2 | 35 |
| `PRICE_LEVEL_EXPENSIVE` | 3 | 70 |
| `PRICE_LEVEL_VERY_EXPENSIVE` | 4 | 120 |
| missing | `null` | `null` |

**Choice.** Quality prior, used only when both `rating` and `review_count` are present: prior mean `3.5`, prior count `20`.

`adjusted = (rating * review_count + 3.5 * 20) / (review_count + 20)`

`quality = clamp(adjusted / 5)`

When `review_count` is missing, keep today’s `rating / 5` or `0.5`. `rank()` is unchanged.

**Choice.** Neutral schedule when calendar read is not ok: schedule component `0.5`, `schedule_compatible=True`, so verify does not apply `outside_window` or `conflict`. `RankingContext.calendar_read` is `"ok"` or `"unavailable"`, default `"ok"`, so current ranking tests stay valid.

**Choice.** On a successful approve click, write `plan.scheduled` only. Do not also write `plan.approved` for that click. Leave historical rows already stored. `plan.cancelled` on decline stays.

**Choice.** Discovery cache TTL 600 seconds. Integrations health TTL 300 seconds. They are separate objects. Neither uses Redis.

### What to preserve

Leave the LangGraph node names and the “HTTP does not resume the graph” split. Leave `HeuristicRanker` weights. Leave `GET /api/calendar/events` as the local notebook. Leave `make_idempotency_key`’s hash input. Leave the initial Alembic revision. Leave mock catalogs and the Chicago demo origin for mock mode.

### Provider behavior

Shared HTTP rules in each provider, with an injected `httpx.AsyncClient` so tests pass `MockTransport`:

- Connect timeout 5 seconds, read timeout 10 seconds. No transport-level retries.
- `call_with_retries` stays at 3 attempts. Add an optional delay argument defaulting to `0` so existing tests stay fast. Production search and calendar call sites pass a 0.25 second base delay, doubling per attempt, capped at 2 seconds.
- Map responses into `ProviderError`. Log provider name, operation, and status code. Do not log the URL, because Ticketmaster puts the key in the query string.

| Upstream | `code` | HTTP status on synchronous calls | `retryable` | Plan effect during discovery |
| --- | --- | --- | --- | --- |
| Missing key, or OAuth not connected | `provider_not_configured` | 409 | no | `failed`, safe message names the provider |
| 401 / 403 auth (not quota) | `provider_not_configured` | 409 | no | `failed` |
| 400 invalid request | `provider_failed` | 502 | no | `failed` |
| 429, 500, 503, timeout | `provider_unavailable` | 503 | yes | `failed` after retries |
| Empty list | success | — | — | existing `no_events` / `no_restaurants` |

Safe sentences:

- Ticketmaster not configured: “Ticketmaster is selected but no API key is configured. Demo results were not substituted.”
- Ticketmaster failed: “Ticketmaster could not be reached. Demo results were not substituted.”
- Places not configured: “Google Places is selected but no API key is configured. Demo results were not substituted.”
- Places failed: “Google Places could not be reached. Demo results were not substituted.”

Approve does not use 409/503 for a missing Google connection or a failed Google create. See Calendar write.

#### Ticketmaster

`GET https://app.ticketmaster.com/discovery/v2/events.json`

Send `apikey`, `startDateTime`, `endDateTime` as UTC `Z`, `size` from `query.limit` (keep 40), and `classificationName` only when the first normalized category is in this map: `live_music→Music`, `arts→Arts`, `comedy→Comedy`, `film→Film`. Unmapped categories omit the classification filter. City-only search sends `city`. Coordinate search sends `latlong`, `radius`, and `unit=km`, and omits `city`. Radius is `default_radius_km` or `10`.

Normalize each event: id, name, url, dates as timezone-aware datetimes, venue name and address, venue lat/lng when present, price min when `priceRanges` exists, otherwise `null`. Image is the widest image URL or `null`. `source="ticketmaster"`, `provider="ticketmaster"`, `external_id` is the Ticketmaster id, `retrieved_at` is the clock’s UTC now. Categories pass through `normalize_token`. A missing price stays null. A missing coordinate pair stays null. Do not drop the event for either gap.

#### Google Places

`POST https://places.googleapis.com/v1/places:searchText`

Header `X-Goog-FieldMask` is exactly:

`places.id,places.displayName,places.formattedAddress,places.location,places.rating,places.userRatingCount,places.priceLevel,places.googleMapsUri,places.businessStatus,places.primaryType,places.types`

Body: `textQuery` from the cuisine labels or `"restaurant"`, `pageSize` at most 20, `includedType=restaurant`, `strictTypeFiltering=true`, and `locationBias.circle` from saved coordinates and radius in meters.

Drop `CLOSED_PERMANENTLY` and `CLOSED_TEMPORARILY`. Keep a place when `openNow` is false, so a daytime search can still return a dinner. Missing rating stays null. `source="google_places"`.

`EventCandidate` and `RestaurantCandidate` must allow null price, rating, latitude, and longitude. Mock constructors still fill them. `to_candidate()` copies `source` from the integration model.

#### Discovery cache

`backend/app/providers/cache.py`: a `DiscoveryCache` protocol with `get` and `set`, plus `InMemoryDiscoveryCache`. The factory injects it. Tests can inject a null cache. Cache successful lists, including empty lists. Do not cache errors.

Key material, canonical JSON then SHA-256: provider, operation, city, latitude and longitude rounded to 3 decimals, radius, date start, date end, sorted categories, timezone. The health cache is a different object in `backend/app/providers/health.py` and is updated only after a real call.

#### Integrations status

`GET /api/integrations` does not call upstream. `status` stays `ready` or `unavailable`. Add `connection`:

| Situation | `connection` | `status` |
| --- | --- | --- |
| Mock events or mock places | `mock` | `ready` |
| Local calendar | `local` | `ready` |
| Real provider, secret missing | `not_configured` | `unavailable` |
| Ticketmaster or Places key present, no recent failure | `configured` | `ready` |
| Google client configured, no connection row | `oauth_required` | `unavailable` |
| Google connection `connected` and refresh token present, no recent failure | `connected` | `ready` |
| Last real call failed within 5 minutes | `unhealthy` | `unavailable` |

`demo_mode` is true only when events are mock, places are mock, and calendar is local. `account_email` is included on the calendar provider object and is null when unknown.

#### Calendar read

`get_calendar_availability` catches provider failures, including not connected. It sets `calendar_read` to `unavailable`, `calendar_events` to an empty list, and `free_windows` to an empty list, then continues. Ranking must look at `calendar_read` before the empty lists. An empty busy list with `calendar_read=ok` still means a free calendar. That is the local provider’s real result.

For restaurants, when the read is unavailable, build the display slot from the constraint’s own `time_start` / `time_end` on `date_start` (default 08:00–22:00, duration 90 minutes inside that window). Set `calendar_checked=false` on those candidates. The template must not say the slot is free.

`GET /api/calendar/window?start=&end=` reads the configured provider for the local user. Google results are only Google events. Local results are only local rows. Auth failure is 409 `provider_not_configured`. Temporary failure is 503 `provider_unavailable`. Naive datetimes are 422, matching `POST /api/calendar/events`.

#### Calendar write

Approve always re-reads the configured calendar before create.

| Outcome | HTTP | Plan status | Event created | `calendar.ics_available` |
| --- | --- | --- | --- | --- |
| Overlap | 409 `schedule_conflict` | `awaiting_approval` | no | false |
| Google disconnected, revoked, or refresh `invalid_grant` | 200 | `awaiting_approval` | no | false |
| Read failed, so overlap cannot be checked | 200 | `awaiting_approval` | no | true |
| Create timeout or 5xx, and GET-by-id did not find it | 200 | `awaiting_approval` | no | true |
| Create succeeded, or GET-by-id found the prior create | 200 | `scheduled` | yes | true |

Google event id is the 64-character idempotency key. On timeout, `GET /calendars/primary/events/{id}` before another insert. A completed `calendar_actions` row, or a Google 409 on that id, returns `replayed=True`.

Add nullable `calendar_actions.external_event_id` (`String(128)`). Google success stores the hex id there and leaves `local_calendar_event_id` null. Local success stays as it is today.

`GET /api/plans/{id}/ics` succeeds when the plan is `scheduled` (local row, or the stored candidate when the event is only on Google) and when a failed Google create left `ics_available` true. The failed-create file is built from the stored candidate. The plan is not marked `scheduled` in that case.

Disconnected approve copy tells the user to connect Google Calendar. The three stored recommendations stay on the plan response. The workspace shows those cards and a Connect action. It does not say Scheduled.

#### Interaction rows

`_persist` inserts a new `recommendations` generation and its candidate rows. It does not delete earlier generations for that session. Shown events are written only while inserting a new shown row.

`_interact` properties, and no score fields:

```json
{
  "recommendation_candidate_id": "<recommendation_candidates.id UUID>",
  "provider": "ticketmaster",
  "external_id": "<upstream id>",
  "candidate_type": "event"
}
```

`candidate_id` on the interaction row remains the provider candidate id string. The required join key is `properties.recommendation_candidate_id`.

`GET /api/interactions?limit=50&cursor=` returns only `interaction_events` for the local user. `limit` default 50, max 100. Cursor is `(created_at, id)`. This list does not include `agent_run_events`.

#### Preferences

Add to the existing preferences document and `user_preferences` row, all nullable: `home_city` (max 80), `latitude` (−90..90), `longitude` (−180..180), `default_radius_km` (1..50), `timezone` (IANA). PUT remains a full replace. Omitted new fields store null so older payloads still validate. Latitude and longitude must both be present or both be absent. Invalid timezone is 422.

Planning uses `preferences.timezone` when set, otherwise `Settings.app_timezone`. Datetimes stored on candidates and sent to Google are timezone-aware. Naive datetimes are rejected at the calendar boundary.

#### Explanation fact-check

Extend `merge_explanations` in `backend/app/services/recommendations/explanations.py`. The model payload gains venue, address, start, and end. It does not gain the dollar price band. It gains `calendar_checked`.

Reject model text when:

- a number in the text is not one of the allowed payload numbers (travel minutes, rating to one decimal, clock hours and minutes in the plan timezone), or
- `calendar_checked` is false and the text claims a free slot, open time, or no conflict.

On rejection, store `template_explanation`. The template itself omits “fits your open time” when `calendar_read != ok`. It may say “about N minutes away” only when travel minutes are present. It may say “fits your budget” from the band comparison without quoting the band as a menu price.

#### Frontend

No new routes.

- Preferences: city, latitude, longitude, radius, timezone. Timezone uses the same IANA validation the API returns.
- Plan workspace, status `awaiting_location`: a panel for `city_required` or `location_required`, a link to Preferences, and “Continue this plan” calling `POST /continue`. This panel is not the clarification text box.
- When `demo_mode` is true and cards are visible: “Showing demo recommendations.”
- Provider `failed` copy is the API message, which names Ticketmaster or Google and says demo results were not substituted.
- `awaiting_approval` after a disconnected calendar: keep the three cards and show Connect. Connect POSTs `return_path` of `/plans/{planId}`.
- Google write failure: offer “Download .ics” and do not show the Scheduled state.
- Integrations: connection label, mock detail, Connected plus Disconnect, Connect when `oauth_required`. Local calendar list stays, with one line that those rows are the local notebook and are not Google busy time when `CALENDAR_PROVIDER=google`.
- Settings timezone sentence becomes a link to `/preferences`.
- “Not this” is a quiet text button on each shown card in `awaiting_selection`.
- Cards still have no provider badge. “View details” remains the source link.
- When `calendar_checked` is false, the card says “Schedule was not checked.” Confirmation does not say “No conflicts detected.”

## Alternatives Considered

| Choice | Recommended | Alternative | Why the alternative loses |
| --- | --- | --- | --- |
| Missing location | `awaiting_location` and `POST /continue` on the same id | `failed` / `location_required` | The UI would start a new plan or misuse the clarification box |
| OAuth return | Allowlisted relative path | Always `/integrations` | Connect from a plan would drop the user off that plan |
| Rejection | Explicit “Not this” | Infer rejection from the cards not chosen | That labels unselected cards as rejected and double-counts later training |
| Distance | Saved coordinates for real providers | Chicago constant for every provider | Real results would be scored from the wrong origin |
| OAuth routes | POST connect, GET callback, DELETE disconnect | GET auth and POST disconnect | POST is the nonce mint; DELETE is idempotent |
| Token storage | Plaintext behind a repository | Encrypt now | Encryption is a second secret design; the port keeps that replacement possible |
| Ranker | One protocol, heuristic only | A model ranker in V1 | Out of scope, and it would change ordering behavior |
| Cache | In-process, replaceable | Redis | A new datastore with no load requirement |
| Google create failure | HTTP 200, stay `awaiting_approval`, offer `.ics` | 503 and mark the plan failed | The user would lose the three cards and the fallback file |
| Account email | Omit until the open question is answered | Add `openid` and `email` now | Those are extra scopes the API recommendation excluded |

## Data Flow

1. `POST /api/plans` inserts the session and returns 202. Discovery runs in the background.
2. The graph parses constraints, loads preferences, then reads the calendar. A calendar failure is recorded as `calendar_read=unavailable` and discovery continues.
3. After plan type is known, the location gate either stops at `awaiting_location` or searches. Search checks the discovery cache, then calls the selected provider. Results are normalized, including Haversine and the travel estimate for real providers.
4. `HeuristicRanker` scores the list. Verify excludes conflicts, travel, budget, and outside-window only when the calendar read was ok.
5. Explanations are fact-checked. `_persist` appends one recommendation generation and writes `recommendation.shown` for each shown row.
6. The client polls `GET /api/plans/{id}`. Select writes `recommendation.selected`. “Not this” writes `recommendation.rejected`.
7. Approve re-reads the calendar, conflict-checks, then `schedule_approved_plan` creates the local row or the Google event. Success writes `plan.scheduled` once and sets `scheduled`. Failure leaves `awaiting_approval`.
8. `POST /continue` from `awaiting_location` starts step 2 again on the same id after preferences are saved.

## API Changes

All routes stay under `/api`. Error JSON stays `{ "error": { "code", "message" } }`.

`GET /api/integrations` adds `connection` and `account_email` on each provider. `status`, `demo_mode`, and `timezone` stay. `timezone` in this payload remains the settings fallback. The user’s timezone is on preferences.

`POST /api/integrations/google/calendar/connect` body `{ "return_path": "/plans/{uuid}" }` optional. Response `{ "authorization_url": "https://accounts.google.com/..." }`. Invalid `return_path` is 422. Missing client id or secret is 409 `provider_not_configured`.

`GET /api/integrations/google/calendar/callback` exchanges the code, stores the connection, and redirects to `APP_BASE_URL` plus the stored path. Failure redirects to the stored path with `?calendar=connect_failed` and no code, token, or state in that URL.

`DELETE /api/integrations/google/calendar/disconnect` returns 204 and deletes the local user’s connection row.

`GET /api/calendar/window?start=&end=` returns the same event shape as `GET /api/calendar/events`, from the active calendar provider.

`GET /api/calendar/events`, `POST /api/calendar/events`, `POST /api/calendar/sample`, and `DELETE /api/calendar/events/{id}` stay the local notebook.

`PUT /api/preferences` accepts the five new fields on the same document.

`POST /api/plans/{id}/continue` returns the existing `PlanCreatedResponse` (`plan_id`, `status: processing`) with 202. Wrong status is 409 `plan_not_ready`.

`POST /api/plans/{id}/reject` body `{ "candidate_id": string }`. Response is `PlanResponse`. Unknown or not-shown id is 400 `invalid_selection`.

`PlanResponse` gains `calendar.ics_available`. Each recommendation gains `calendar_checked` and `travel_time_is_estimate`.

`GET /api/plans/{id}/ics` is allowed for `scheduled` and for `awaiting_approval` when `ics_available` is true.

`GET /api/interactions` is the paginated envelope of interaction events only.

Approve’s 409 conflict contract stays. Approve’s new soft failures return 200 with the plan.

## Persistence Changes

New Alembic revision. Do not edit `ad1a206d0e8d`.

`user_preferences` adds nullable `home_city` (`String(80)`), `latitude` (`Float`), `longitude` (`Float`), `default_radius_km` (`Float`), `timezone` (`String(64)`).

`calendar_actions` adds nullable `external_event_id` (`String(128)`).

`oauth_connections`: `id`, `user_id` unique, `provider`, `refresh_token`, nullable `access_token`, nullable `access_token_expires_at`, `scopes`, nullable `account_email`, `status` (`connected`, `expired`, `revoked`), `connected_at`, `updated_at`.

`oauth_states`: `id`, `user_id`, `state_hash` unique (SHA-256 of the nonce, not the raw nonce), `return_path`, `expires_at` (10 minutes), nullable `consumed_at`.

Candidate provenance stays in the existing `payload` JSON: `provider`, `external_id`, `source_url`, `retrieved_at`, `source`, `review_count`, `travel_time_is_estimate`, `calendar_checked`. No new candidate columns. `rejected` already exists.

## UI / UX Impact

The planning journey, sidebar, and visual system stay. New states use the existing surface, type, and buttons.

Preferences gains a location group: home city, latitude, longitude, default radius, timezone. Helper text says coordinates are required for restaurant search and that a city is enough for event search. Validation errors sit on the fields.

The plan page, when `awaiting_location`, explains which fact is missing and links to Preferences. After a successful save, “Continue this plan” resumes that id. The clarification input is only for `awaiting_clarification`.

Integrations replaces the “not available in V0” sentences with Configured, Not configured, Connected, and Disconnect. Connect starts OAuth and returns to the page that started it when that page is the plan or Integrations. The local calendar section remains for the notebook.

A failed real search does not say that demo results were used. A failed Google write offers the `.ics` download on the approval panel. Scheduled remains the success state with its existing download.

“Not this” sits beside “Choose this” and does not use a destructive color. Focus stays on the card list after the plan refreshes.

Settings no longer tells the person to edit `APP_TIMEZONE`. It links to Preferences.

The UI spec from the product designer is the interaction source for loading, error, disconnect confirmation, and focus behavior. Where this plan and that spec differ, this plan wins: no provider badge on cards, “Not this” is included, and Connected may omit email.

## AI / ML Impact

No model change, no new ranker, no weight change, no tool for the model. OpenAI remains the constraint parser and the optional explainer. The explainer’s output is checked against the payload and replaced with the template when the check fails. The template is deterministic.

Ranking changes are input changes only: normalized category aliases, the price band, the optional review prior, Haversine distance, and derived travel minutes. Null calendar reads use the neutral schedule component so candidates remain eligible.

Interaction rows are the future training surface. They live on `interaction_events` only. Scores stay on `recommendation_candidates` and are not copied into `properties`.

## Security

Trust boundary: Ticketmaster, Places, and Google responses are untrusted data. They become candidate fields after the normalizer. They do not choose tools, status codes, or redirect targets.

OAuth: backend-owned client secret, single-use state hash, 10-minute expiry, allowlisted return path, redirect host from `APP_BASE_URL`. Scope is `calendar.events` only, unless the open question below is explicitly approved.

Secrets: API keys and the client secret stay in `Settings` as `SecretStr`. Refresh and access tokens stay in `oauth_connections` and are read only through the repository. Logging omits credentials, raw bodies, and full request URLs.

Authorization: every new route uses the local user, the same way existing plan routes do. `continue`, `reject`, disconnect, and the calendar window do not accept a user id from the client.

`.ics` download is limited to the local user’s plan, and only after schedule success or a recorded Google write failure.

CSRF: the callback is a Google redirect with a single-use state. Connect is a POST. The app still has no session cookie. Keep `allow_credentials=False` on CORS.

Security review is required before release. It is not required to approve this plan.

## Observability

Log `provider`, `operation`, `status_code`, `plan_id`, and `error_code`. Log cache hit or miss and candidate counts. Do not log tokens, API keys, upstream bodies, or the OAuth code.

Existing agent-run events stay the timeline source. Add no timeline step that claims a provider succeeded when the call failed. Calendar read failure can emit `calendar_loaded` with `status=completed` and safe metadata `{ "calendar_read": "unavailable" }` so the timeline does not show a false failure of the whole plan and does not show a successful busy count of zero as if the calendar were empty.

Health for `GET /api/integrations` is the last real call within five minutes. No probe on that GET.

## Tests

Preserve the current 27 pytest and 5 vitest by keeping mock and local defaults, rank weights, and the `rank()` signature. Add tests. Do not treat the preserved suite as coverage of the new HTTP or providers.

Backend, `httpx.MockTransport` unless noted:

- `backend/tests/test_ticketmaster.py`: success, missing price, missing coordinates, empty list, 401, 429, 500, timeout. Assert the mapped error code, that retryable errors retry, and that the API key is not in any logged URL.
- `backend/tests/test_google_places.py`: normalization including category alias and price band, missing rating, closed place dropped, empty list, quota, timeout. Assert the field mask is the explicit list.
- `backend/tests/test_google_calendar.py`: state nonce single-use, expired state rejected, absolute `return_path` rejected, `/integrations` and an existing `/plans/{uuid}` allowed, read mapping, create uses the hex idempotency key, duplicate returns replayed, timeout then GET-before-insert, expired token refresh, `invalid_grant` creates nothing, overlap raises `ScheduleConflictError` and writes no `calendar_actions` row.
- One workflow test from a normalized real candidate through `HeuristicRanker`, select, approve, and one calendar create, using the local calendar gateway so the test does not need Google.
- Interaction test: one `recommendation.shown` per shown row, one `recommendation.selected`, one `recommendation.rejected` only after the reject call, one `plan.scheduled` and no second `plan.approved` on that click. Properties contain `recommendation_candidate_id` and no score fields. A second discovery run does not delete the first generation’s rows.
- Timezone tests: aware Ticketmaster and Google datetimes, preference timezone overrides `APP_TIMEZONE`, naive calendar input returns 422.
- Location gate: Ticketmaster without city does not call HTTP and yields `awaiting_location` / `city_required`. Places without coordinates yields `location_required`. Mock providers do not. `POST /continue` reuses the id.
- Calendar read failure: candidates remain, none are excluded solely as `outside_window`, and the template does not claim a free slot.
- Explanation fact-check: a model string with a dollar amount or venue not in the payload is replaced by the template.
- `GET /api/integrations` with a present key and no prior call returns `configured` and does not perform I/O.

Frontend vitest, added to the existing 5:

- Preferences form includes the location fields and submits them.
- `awaiting_location` renders the location panel and does not render the clarification input.
- Disconnected approval shows the cards and Connect, and does not show Scheduled.
- `ics_available` shows Download `.ics` while status is `awaiting_approval`.
- “Not this” calls reject for that card only.

Mock-provider mode is the existing suite plus an explicit test that `EVENT_PROVIDER=mock`, `PLACE_PROVIDER=mock`, and `CALENDAR_PROVIDER=local` never construct an `httpx` call.

## AI Evaluation

The ranker is deterministic. No baseline-versus-candidate model evaluation is required for V1.

The explainer is probabilistic. The fact-check and template fallback are the evaluation: the tests above are the gate. Do not add a second scoring model. Do not change the OpenAI model setting as part of this work.

Retrieval evaluation is not applicable. Discovery is a provider query plus a cache, not a vector index.

## Migration

Add one Alembic revision after `ad1a206d0e8d`. New columns are nullable. Existing preference, candidate, and calendar rows stay valid. No backfill. Mock mode needs no data change.

Deploy locally by running the new migration before starting the API with real provider flags. Default env values remain `EVENT_PROVIDER=mock`, `PLACE_PROVIDER=mock`, `CALENDAR_PROVIDER=local`.

There is no production database in this plan. Do not run this migration against a shared or production database as part of implementation.

## Rollout

Flags are the rollout. Real providers turn on only when the env vars are set and, for Google, after Connect. `GET /api/integrations` tells the operator which connection state they are in without calling the upstream APIs.

No percentage rollout, feature-flag service, or production deploy. If a real provider misbehaves, switch that one env var back to `mock` or `local` and restart. Cached discovery results expire within 10 minutes or on process restart.

`.env.example` gains `APP_BASE_URL=http://localhost:5173`. `GOOGLE_REDIRECT_URI` stays the documented callback, `http://localhost:8000/api/integrations/google/calendar/callback`. Do not add `API_BASE_URL`. The redirect URI is already explicit.

After implementation, update `docs/architecture.md`, `README.md`, and `docs/plans/v0-plan.md` (point V1 at this file; do not create `docs/v0-plan.md`). Add `docs/integrations.md` with key setup and no secret values. Update the progress table in this file as steps land.

## Risks

- Plaintext refresh tokens in Postgres are usable by anyone who can read the database. Accepted for local V1 only if the Type 1 storage recommendation is approved. Security review before release must restate this.
- A neutral schedule score can surface an event that conflicts. Approve’s second read is the backstop. If that read fails, V1 refuses to create and offers `.ics`.
- The 30 km/h estimate can rank a far venue as close. The flag `travel_time_is_estimate` and the “about N minutes” copy are the mitigation. It is not a routing API.
- Price bands can mark a place inside budget when the menu is not. Explanations must not quote the band as a price.
- Stopping delete-and-reinsert leaves old generations in Postgres. Selection already uses the latest recommendation. The table can grow across clarifications. V1 does not add a cleanup job.
- Google allows overlapping events. Our overlap check is the product rule. A failed read must not skip that check and still create.
- `docs/architecture.md` says `CandidateRanker` already exists. The protocol is not in the code. Add it; do not assume it is present.
- Changing `ProviderNotConfigured` from `provider_unavailable` to `provider_not_configured` changes an error code. Existing tests do not assert it.

## Ordered Implementation Steps

Each step leaves mock/local mode runnable.

1. **Config and status.** Add `APP_BASE_URL`, health TTL, and discovery TTL to `Settings`. Split `provider_not_configured` (409) from `provider_unavailable` (503) on `ProviderError`. Teach `GET /api/integrations` the `connection` field from settings and the health cache, with no live probe. Update the integrations schema and frontend types. Default mock/local responses stay `ready`.
2. **Ticketmaster.** Replace the stub body. Inject `httpx.AsyncClient`. Normalize, map errors, and cache successful searches. Wire the factory. Empty key raises `provider_not_configured` on search, not at import.
3. **Places.** Same pattern: explicit field mask, closed-place filter, price band, rating and review count, cache. Do not call Places without coordinates. This step can require coordinates on the query model. The plan-status gate is step 4.
4. **Location and timezone.** Alembic revision for preference columns. Extend domain, schema, PUT, and the preference form. Apply the location gate in the search nodes and add graph edges to `END` on `awaiting_location`. Add `POST /continue`. Use the preference timezone when set. Haversine and the 30 km/h estimate run only for real providers.
5. **OAuth.** Add `oauth_connections` and `oauth_states` in the same or a following revision, the repository, connect, callback, and disconnect. Allowlist the return path. Do not log tokens.
6. **Calendar read.** Implement `get_events` for Google, including refresh. Discovery treats failure as `calendar_read=unavailable`. Add `GET /api/calendar/window`. Do not merge local sample events into Google results. Update verify and the template so an unknown calendar does not drop every candidate and does not claim a free slot.
7. **Calendar write and idempotency.** Widen `schedule_approved_plan` to `CalendarGateway`. Google create uses the hex id, GET-before-retry on timeout, and `external_event_id`. Conflict still skips the key. Soft failures return 200 and `ics_available`. Extend `.ics` for Google success and failed Google create. Keep the local success path.
8. **Graph wiring.** Pass location and timezone into the existing search queries. Set `source` from the provider. Append recommendation generations. Thread `calendar_checked` onto candidates. Keep `PlanningOrchestrator.approve` as the only HTTP writer.
9. **Interaction events.** Fill `recommendation_candidate_id` on shown, selected, rejected, and scheduled. Write `plan.scheduled` once per successful click. Add `POST /reject` and `GET /api/interactions`. Fact-check explanations.
10. **Frontend.** Location fields, location panel, continue, Connect and Disconnect, demo line, provider failure copy, “Not this”, `.ics` on write failure, and the Settings link. No new routes.
11. **Tests.** Add the mocked-HTTP, workflow, interaction, and timezone tests. Run the preserved pytest and vitest suites in mock/local mode.
12. **Docs.** Update the files listed under Rollout. `docs/integrations.md` explains which keys, the redirect URI, and `APP_BASE_URL`, with empty values only.

## Human Approval Requirements

Do not implement until this plan is approved.

Approval needs an explicit yes on:

1. `awaiting_location` plus `POST /api/plans/{id}/continue` on the same plan.
2. Allowlisted OAuth return path (`/integrations` or `/plans/{uuid}` only).
3. Plaintext refresh tokens in Postgres behind `OAuthConnectionRepository`.
4. OAuth scope limited to `https://www.googleapis.com/auth/calendar.events`, with no account email until the open question is approved.
5. Explicit “Not this” rejection, without inferring rejection from the cards that were not chosen.

Type 2 choices in this plan (paths, price bands, 30 km/h, neutral schedule score `0.5`, cache TTLs, `plan.scheduled` without a paired `plan.approved`) are part of the same approval.

Security review happens after implementation and before any release. This plan does not authorize production deploy, IAM changes, or a migration of any non-local database.

## Open questions

**Google account email.** The integrations UI asks for Connected plus an email. `calendar.events` does not provide one. Recommended default, so implementation is not blocked: show “Connected” and omit the email when `account_email` is null. If the product requires the address, approval must add the `openid` and `email` scopes and no calendar scope beyond `calendar.events`. Until that is explicitly approved, do not add those scopes.
