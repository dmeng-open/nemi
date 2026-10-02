# Planning process

Planning follows `.cursor/skills/plan-feature/SKILL.md` and fills `docs/templates/implementation-plan.md`.

## When a plan is required

Any non-trivial change. Trivial typos and equally local corrections still need a look at the result, not a full plan.

## What the plan must separate

Facts, assumptions, decisions, recommendations, risks, and open questions. A recommendation is not a decision. An assumption is not a fact.

## Approval

Human plan approval is required for large or architecture-sensitive work, and for any Type 1 decision that is not already settled: public contracts, tenancy, authentication, core persistence, data ownership, execution isolation, security model, event model, or major platform.

Normal work may skip that approval only when the scope is narrow, the design is obvious, security boundaries stay put, architecture stays put, and the change is cheap to reverse.

## After approval

The plan is the contract. Implementation uses `.cursor/skills/implement-feature/SKILL.md`. Changing the contract means stopping and replanning the affected part.
