# UI development process

```text
Understand the user
  → design-ui (product UI designer)
  → plan
  → implement-ui (frontend design engineer or implementer)
  → visual review, by someone else
  → engineering review
  → verification, including a browser pass when tools exist
```

The spec is `docs/templates/ui-spec.md`. Standards are `.cursor/rules/ui-ux.mdc` and `.cursor/rules/frontend.mdc`.

Quality is enforced by the spec, not by a component library default:

- The primary job has a hierarchy, not a grid of equal cards.
- Loading, empty, error, and partial failure are designed.
- Keyboard use, focus, and responsive layout are part of the spec and the verification note.
- WCAG 2.2 AA is the practical target.
- AI-specific states (progress, sources, tool activity, uncertainty, cancellation) appear only when the user needs them.

A compiled page is not done. The verification report names the viewports that were inspected. If none were, the status cannot be a clean verified for a UI change.
