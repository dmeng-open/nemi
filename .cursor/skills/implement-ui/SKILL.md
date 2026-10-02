---
name: implement-ui
description: Implements an approved UI spec in TypeScript, React, and Next.js, including accessibility, states, tests, and browser verification. Use for /implement-ui or assigned UI implementation.
---

# Implement UI

Build the approved spec. Visual polish does not replace the interaction model.

## Workflow

1. Read the approved UX spec and the API contract it depends on.
2. Inspect the existing design system and match it.
3. Set component boundaries and where state lives: server, URL, or local UI.
4. Implement the primary workflow, responsive layout, and keyboard access.
5. Implement loading, empty, error, and partial-failure states from the spec.
6. Connect the real API or document the stub. Do not fake success.
7. Add frontend tests for behavior that a rendering bug would hide, especially forms, errors, and conditional actions.
8. When browser tools exist, run the flow on desktop, tablet, and mobile widths. Check overflow, focus, and error display.
9. Hand off to independent visual review using the visual-review skill. The implementer does not self-approve.
10. Hand the diff to the reviewer and the verifier.

## Prohibitions

Do not redesign information architecture in code. Do not ship a page whose only content is raw JSON. Do not claim a viewport was checked if it was not.
