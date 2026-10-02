# Delegation protocol

The orchestrator routes work here. Do not add agents to look thorough. Parallelize only work that is actually independent: separate exploration questions, frontend and backend after the API contract is approved, security review beside ordinary review, independent tests, and evaluation jobs. Do not parallelize an unresolved Type 1 decision.

## Trivial

Examples: a typo, a tiny documentation fix, an obvious narrow configuration correction.

The session agent may do it directly when risk is low, architecture is untouched, security is untouched, and the change is easy to reverse. Verify the result anyway.

## Normal engineering

Explorer, then planner, then implementer, then reviewer, then verifier.

Human plan approval may be skipped only when the scope is narrow, the design is obvious, no security boundary moves, architecture is unchanged, and reversal is cheap.

## Large or architecture-sensitive

Explorer, then the relevant specialists, then planner, then human plan approval, then implementer, then reviewer, then verifier, then release engineer when a commit or PR is requested.

## UI or product surface

Explorer, then product UI designer, then planner, then frontend design engineer or implementer, then reviewer, then visual review, then verifier.

The agent that implemented the UI does not perform the only visual review.

## AI or ML

Explorer, then AI/ML engineer, then any other relevant AI specialist, then planner, then implementer, then evaluation, then reviewer, then verifier.

## Agent behavior

Explorer, then agent runtime engineer, then AI/ML engineer when model choice matters, then planner, then implementer, then AI evaluation, then security reviewer when tools or permissions are involved, then reviewer, then verifier.

## RAG or retrieval

Explorer, then RAG/data engineer, then AI/ML engineer, then planner, then implementer, then retrieval evaluation, then reviewer, then verifier.

## Security-sensitive

Always include the security reviewer before release.

Triggers: authentication, authorization, secrets, external URLs, uploaded files, filesystem access, agent tools, privileged or autonomous actions, organization or tenant access, and arbitrary execution.

## Bug fix

Follow the fix-bug skill. Escalate to the large or security path if the root cause changes architecture or a trust boundary.

## Release

Verifier, then release engineer. The release engineer does not verify by proxy.

## Who writes code

The implementer writes application code from an approved plan. The frontend design engineer writes UI from an approved UI spec. Domain specialists (AI/ML, agent runtime, RAG, API/DX, platform/MLOps) specify and review. They do not take write access in those roles. The planner, explorer, product UI designer, reviewer, and security reviewer are read-only.

## Orchestrator limit

The coordinating agent does not implement large or architecture-sensitive work itself.
