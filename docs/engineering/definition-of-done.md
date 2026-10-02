# Definition of done

Implementation alone is not done. Use the items that apply to the change. Say which items do not apply.

A meaningful change is done when:

- The requirement's observable outcome holds.
- The result matches the approved architecture and plan contract.
- User-facing work matches the UX spec, including empty, loading, and error states.
- Tests cover the behavior and at least one relevant failure or edge.
- Probabilistic AI or retrieval behavior has evaluation evidence, kept separate from unit tests.
- Accessibility and keyboard behavior were considered for UI, and gaps are stated.
- Error handling is defined, not implied.
- Required security review is complete, with residual risk named.
- Operability is enough to diagnose the new path, and secrets are not logged.
- Docs or API contracts that the change invalidates were updated.
- The verifier recorded commands, results, and remaining uncertainty.
- Release impact is understood: migration, compatibility, and rollback.

A pull request is not done until verification evidence exists. A merge still requires a human. A deployment or production migration requires its own approval.
