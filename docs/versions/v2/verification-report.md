# Requirement

V2 hierarchical planning: a multi-part evening becomes one or more itineraries, research that does not depend on other research runs together, a rejected plan reruns only the failed part, and calendar writes happen only after the graph is resumed from approval. Approving twice does not create a second copy. A single activity or meal still uses the existing one-candidate graph.

# Expected Behavior

- A Saturday date-night request ends in `awaiting_approval` with at least one dinner-plus-activity itinerary and no calendar rows yet.
- Approving that itinerary creates two calendar events. Approving again does not add more.
- A Saturday-afternoon activity request stays `plan_type=event` and `awaiting_selection`.
- After the revision cap, the same itinerary can still be approved and written.
- An itinerary id that is not one of the offered plans writes nothing.
- Event-provider timeout still returns a dinner-only plan. A partial calendar write can be retried to two events. Cancel without confirmation does not delete.

# Verification Environment

Windows, Python from `backend/.venv`, SQLite test database, Vitest 5. Branch `feature/nemi-v2`. No browser, no live Google account, no Postgres process.

# Commands Executed

Working directory `backend`:

- `python -m pytest -q --tb=line` — 95 passed in 41.16s (after the approval-resume fix).
- `python -m pytest tests/test_itinerary_smoke.py evals/multi_agent/test_scenarios.py -q --tb=short` — 16 passed in 20.05s.
- `python -m ruff check app/agents/itinerary app/services/planning app/api/routes/plans.py app/models/multi_agent.py tests/test_itinerary_smoke.py tests/test_itinerary_units.py evals` — exit 1, 6 findings (import order, one pre-existing line length in `present.py`).

Working directory `frontend`:

- `npm test` — 3 files, 13 tests passed.

# Tests Executed

Backend pytest includes the previous V0/V1 suite, `tests/test_itinerary_smoke.py`, `tests/test_itinerary_units.py`, and `evals/multi_agent/test_scenarios.py`. Those tests fail if date night does not produce an itinerary, if a single activity is routed into the itinerary graph, if a second approve creates extra events, if a provider timeout drops the successful branch, if a partial write cannot be retried, or if cancel proceeds without confirmation. `test_revision_limit_stays_approvable` fails if the revision cap or a bad itinerary id prevents a later real approval from writing.

Frontend tests cover the existing plan workspace plus one itinerary card approval click. They would not catch a backend routing bug.

# Results

95 backend tests passed. 13 frontend tests passed. Ruff did not pass.

Independent review before the fix was not approved: a plan could stay `awaiting_approval` after the graph had already finished, so approve could not write. That path was changed so a stop with itineraries still on screen returns to the approval interrupt. The new test covers the revision cap and a bad itinerary id. Review was not repeated after that change.

Security review found no blocking issue. Research agents are not on the create or delete allow-list. The first calendar write happens only after an approve resume. OAuth tokens are not returned to the frontend.

# Edge Cases

`test_revision_limit_stays_approvable` revises until `MAX_REPLAN_ATTEMPTS` is 1, then revises once more, then approves. Status stays `awaiting_approval` through the cap, and the real itinerary id schedules the plan.

# Failure Cases

The scenario file injects an event-provider timeout, a restaurant-provider failure, a calendar read failure, a critic rejection, a partial calendar write, and a cancel without confirmation. Those tests passed in the 16-test run and in the full 95-test run.

# UI Verification

The itinerary card and specialist checklist were not opened in a browser. Vitest rendered the card and recorded an approve click. No viewport was inspected.

# AI Evaluation

The itinerary agents are deterministic. `evals/multi_agent/test_scenarios.py` ran inside pytest. There is no separate probabilistic baseline-versus-candidate evaluation, and none is required for this policy.

# Known Gaps

- The approval-resume fix was not re-reviewed by the reviewer.
- Retry can still run when status is `failed` even if discovery failed before any approval, as long as an itinerary row exists.
- The "Finish earlier" chip is not a distinct revision rule. It falls through to rerunning restaurant and event research.
- Postgres checkpoint restart and a live Google Calendar account were not exercised.
- Ruff reports unsorted imports in the itinerary package. That does not change behavior.
- Google's Calendar URL still contains `/calendar/v3/`. That is Google's API path.

# Final Verification Status

verified with gaps
