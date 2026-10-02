---
name: design-ui
description: Specifies user journeys, hierarchy, states, accessibility, and AI interaction without writing production UI. Use for /design-ui or before implementing a product surface.
---

# Design UI

Specify the experience. Do not write production code.

## Workflow

1. State the user goal and the situation in which they are working.
2. Map the primary journey, including how the user knows they succeeded.
3. Define information architecture and screen hierarchy. Remove steps that do not serve the goal.
4. Define the interaction model: primary action, secondary actions, and what is progressive disclosure.
5. Specify loading, empty, error, partial failure, destructive confirmation, and recovery.
6. Specify responsive behavior for desktop, tablet, and mobile.
7. Specify accessibility and keyboard behavior, aiming at WCAG 2.2 AA where practical.
8. Note component implications for the existing design system. Do not invent a second visual language.
9. For AI features, specify streaming, long-running progress, citations, provenance, tool activity, approval, retry, cancellation, uncertainty, and history only where the user needs them.
10. Deliver `docs/templates/ui-spec.md` filled in for this feature.

## Quality bar

The spec should make a generic card dashboard or chatbot clone look like the wrong answer. Hierarchy, language, and state design do the work that decoration cannot.

## Prohibitions

Do not implement the interface. Do not expose agent internals as navigation. Do not leave error and empty states as "TBD" when the primary flow can fail.
