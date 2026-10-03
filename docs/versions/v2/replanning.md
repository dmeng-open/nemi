# Replanning

Replanning starts from the failed check or from the person’s revision. It does not start the graph over.

## Automatic

The constraint engine and the critic attach a target:

| Failure | Task set back to pending | Left alone |
| --- | --- | --- |
| Dietary problem on the chosen restaurant | Restaurant research | Calendar, events |
| Event time, sold-out event, or “replace the activity” | Event research | Calendar, restaurants |
| Budget, order, or a weak sequence that the existing candidates can still solve | Itinerary only | All research |
| Calendar data still valid | None | Calendar |

The planner also receives `rejected_candidate_ids` so the next itinerary cannot repeat the candidate that just failed. If nothing new can be rejected and the same tasks would run again, the supervisor stops instead of looping.

`replan_count` increments on each critic replan and each user revision. At `MAX_REPLAN_ATTEMPTS` the graph returns the best itineraries it has, or a summary that names the limiting constraint. Example: the budget cannot cover dinner and a show, with the checked total called out in the summary.

A provider timeout on events, with restaurants and calendar intact, is a partial result. The supervisor does not discard the restaurant artifact. The person can approve a dinner-only itinerary when one exists.

## Revisions

`POST /api/plans/{id}/revise` resumes the paused thread.

| Message contains | Effect |
| --- | --- |
| cheaper, less expensive, lower budget | Lower `budget_max` by 20% and rebuild itineraries. No new search. |
| restaurant, dinner, place to eat | Reject the current restaurants, rerun restaurant research, rebuild. |
| quieter, activity, event, show | Reject the current events, rerun event research, rebuild. |
| later, one hour | Ask the planner to start dinner later. Ticketed event times stay. If the show cannot move, the summary says so. |
| Anything else | Rerun restaurant and event research once. |

Calendar analysis is not in that list. It reruns only when its own task is pending, which these revisions do not do.

## Supervisor decisions

`CONTINUE`, `RETRY_BRANCH`, `REPLAN`, `ASK_USER`, `PARTIAL_RESULT`, `FAIL`.

`RETRY_BRANCH` is a single extra attempt for a retryable branch failure (timeout or 429-style provider error). It does not increment `replan_count`. Validation errors and 400, 401, and 403 responses are not retried. `SUPERVISOR_RETRY` in tests forces one retryable event failure and then success.

`ASK_USER` is the approval interrupt, or a stop when the replan cap is hit and a person has to change the request.

## Failure injection

`FAILURE_INJECTION` is empty by default. `ENVIRONMENT=production` ignores it even if it is set. Tests set values such as `EVENT_PROVIDER_TIMEOUT`, `RESTAURANT_PROVIDER_FAILURE`, `CALENDAR_READ_FAILURE`, `CALENDAR_WRITE_FAILURE`, `PLANNER_INVALID_OUTPUT`, `CRITIC_REJECT`, and `SUPERVISOR_RETRY`.
