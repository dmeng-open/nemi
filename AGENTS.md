# Engineering constitution

This file is the operating model for future product work. It is not the product. Detailed process lives in `.cursor/rules/`, `.cursor/skills/`, `.cursor/agents/`, and `docs/`.

## Priorities

When priorities conflict, use this order:

1. Correctness
2. Security
3. Maintainability
4. Simplicity
5. Implementation speed

## Capability, authority, and autonomy

Capability is not authority. Authority is not autonomy.

Principal-level judgment does not grant permission to deploy production, mutate production data, change IAM, rotate credentials, merge protected branches, force-push, or run destructive actions.

## Complexity

Complexity is a finite budget. Prefer the simplest design that satisfies the real requirement. Every dependency, service, datastore, queue, framework, agent, and integration needs a concrete reason.

## Decisions

Type 1 decisions are expensive to reverse: public contracts, tenancy, authentication, core persistence, data ownership, execution isolation, the security model, the event model, and major platform choices. They require alternatives, tradeoffs, consequences, and human review when the delegation protocol requires it.

Type 2 decisions are cheap to reverse: local naming, small helpers, and file layout details. Make them and continue.

## How work moves

Non-trivial work: understand, explore, plan, implement, review, verify.

UI work: understand the user, design, implement, visually verify.

AI work: define behavior, implement, evaluate, review.

Release work: verify, release engineer, pull request, CI, human approval.

Routing, gates, and parallelism: `docs/engineering/delegation-protocol.md`.

## Evidence

No fake certainty. If behavior was not tested, the UI was not inspected, AI behavior was not evaluated, an integration was unavailable, or production behavior is unknown, say so.

## Who does the work

The session agent coordinates. A planning request stops before a large implementation. An implementation command follows the approved plan and does not invent a new one. Trivial, low-risk edits may be done directly.

An approved plan is a contract. Implementers may make small local choices. They may not silently change architecture, public APIs, data ownership, the security model, tenancy, execution semantics, or major technology choices.

Roles: `.cursor/agents/`. Processes: `.cursor/skills/`. Constraints: `.cursor/rules/`. Output contracts: `docs/templates/`.

## Commands

`/plan-feature` `/implement-feature` `/fix-bug` `/design-ui` `/implement-ui` `/review` `/security-review` `/verify` `/run-evals` `/prepare-pr` `/release`

## Integration branch

`main` is the protected integration branch. Work happens on `feature/`, `fix/`, or `chore/` branches. Agents do not merge into `main`.
