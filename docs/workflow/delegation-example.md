# Delegation example

This is a documentation-only walkthrough. It does not authorize building the feature.

## Request

"Add organization-level API keys."

## Classification

Large and security-sensitive. Type 1 issues are present: authentication architecture, a public API contract, secret handling, and organization data ownership. Human plan approval is required. The orchestrator does not implement it.

## Order

1. Explorer, read-only. Find any existing organization model, auth boundary, API style, config, and tests. Return file references and unknowns.
2. API/DX engineer, read-only. Sketch key issue, revoke, list, and authenticate contracts. Persistence stays internal. Idempotency and error semantics are part of the sketch.
3. Agent runtime engineer only if keys can authorize agent tools. Otherwise omit.
4. Security reviewer, advisory and read-only, on the sketch: storage of secrets, tenant isolation, leakage in logs, and revocation.
5. Planner, read-only. Produce an implementation plan that labels facts, assumptions, decisions, recommendations, and risks. Unsettled contract or storage choices stay open.
6. Human plan approval. Implementation waits here.
7. After approval, implementer writes the approved increment and tests.
8. Reviewer and security reviewer, in parallel, on the diff.
9. Verifier runs the checks and writes evidence, including the failure case for a revoked or cross-organization key.
10. Release engineer, only if a commit and pull request were requested, and only after the verification report exists.

## Explicitly not in this pass

No frontend unless a management UI was part of the request. No production migration. No merge to `main`.
