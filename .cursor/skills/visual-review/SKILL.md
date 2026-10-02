---
name: visual-review
description: Independently reviews hierarchy, spacing, responsiveness, accessibility, and UI states. Use after UI implementation and before calling an interface done.
---

# Visual review

Review the interface independently of the person who built it.

## Workflow

1. Read the UI spec and the diff. Judge the result against the spec, not against personal taste.
2. Check hierarchy, typography, spacing, alignment, and consistency with the existing system.
3. Check desktop, tablet, and mobile behavior, including overflow and touch targets.
4. Check interaction feedback, focus order, and keyboard operation.
5. Check loading, empty, error, and partial-failure states.
6. Check accessibility basics: names, contrast, focus visibility, and errors tied to controls.
7. Note decoration or complexity that does not help the task.
8. Report findings by severity and say which viewports were actually inspected.

If browser tools are unavailable to this role, ask the verifier to capture the flows and review that evidence. Say that the review used evidence rather than a live session.

## Prohibitions

Do not treat a screenshot of the happy path as a complete review. Do not implement fixes in this pass.
