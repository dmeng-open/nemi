---
name: implement-feature
description: Implements an approved plan in small increments with tests and a handoff to review. Use for /implement-feature or when an approved plan is ready to build.
---

# Implement a feature

Build the approved plan. Do not redesign it.

## Workflow

1. Read the approved plan and the current requirement.
2. Check that the repository still matches the plan's facts. If a Type 1 assumption is false, stop and return to planning.
3. Implement the smallest coherent increment. Reuse existing abstractions.
4. Add or update tests that fail if the intended behavior regresses.
5. Run the focused checks for this increment.
6. Report deviations, including anything you could not test.
7. Hand the diff to the reviewer. If the plan requires security review or evaluation, name those as still outstanding.

UI increments also follow `implement-ui`. AI behavior changes do not skip evaluation.

## Plan contract

You may choose local names, private helpers, and small file layout details.

You may not silently change architecture, public API, persistent data ownership, the security model, tenancy, execution semantics, or a major technology choice.

If the plan is wrong:

1. Stop the affected work.
2. Explain the broken assumption.
3. Propose a revised plan.
4. Wait for the appropriate review.

## Handoff

Include the files changed, commands run, results, and deviations. Do not claim the work is verified or releasable.
