# Engineering principles

These principles govern future product work. They are the long form of `AGENTS.md`.

## Priorities

Correctness, then security, then maintainability, then simplicity, then implementation speed. A faster path that breaks an invariant or a trust boundary is the wrong path.

## Capability is not authority

An agent can reason at a principal level and still be read-only. Permission to think about production is not permission to change it.

## Complexity budget

Prefer the simplest system that meets the actual requirement. New services, datastores, queues, frameworks, agents, and dependencies must pay for themselves with a constraint that a simpler design cannot meet.

## Decisions

Type 1 decisions are expensive to reverse: public API contracts, tenancy, authentication architecture, core persistence, data ownership, agent execution isolation, the security model, the event model, and the major infrastructure platform. They need alternatives, tradeoffs, security and operational consequences, and migration implications. Record them with `docs/templates/architecture-decision.md` when they are being made.

Type 2 decisions are easy to reverse: helper implementation, local naming, small internal libraries, file organization, and minor developer tooling. Make them without a ceremony stop.

## Evidence

No fake certainty. Untested behavior, uninspected UI, unevaluated model behavior, unavailable integrations, and unknown production behavior are reported as unknown.

## Scope of this repository's workflow

The workflow tells agents how to build later. It is not authorization to scaffold the product while doing workflow maintenance.
