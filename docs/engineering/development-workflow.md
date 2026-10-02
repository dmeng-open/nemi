# Development workflow

Future product work follows this path. The session agent coordinates and does not skip gates because the implementation looks small once coding has started.

```text
Requirement
  → orchestrator classifies
  → exploration, when the code is unfamiliar
  → product / UX design, when a human will use a surface
  → architecture planning
  → human plan review, when the delegation protocol requires it
  → implementation
  → specialist review
  → AI evaluation, when behavior is probabilistic or retrieved
  → UI / visual review, when a surface changed
  → security review, when a trigger applies
  → verification
  → release engineering, when a commit or PR was requested
  → pull request
  → CI
  → human merge
  → release or deploy only under explicit approval
```

Trivial edits can be shorter. They still get a check that the edit did what was asked. The short path is defined in `delegation-protocol.md`.

An approved plan is the contract for implementation. If the plan is materially wrong, implementation of the affected part stops and planning resumes.

Release engineering is separate from implementation. The release engineer does not verify by declaring the implementer's summary sufficient.
