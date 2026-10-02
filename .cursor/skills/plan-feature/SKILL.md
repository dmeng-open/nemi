---
name: plan-feature
description: Turns a requirement into an implementation plan with facts, assumptions, decisions, risks, and approval gates. Use for /plan-feature, feature planning, or before substantial implementation.
---

# Plan a feature

Produce a plan. Do not implement the feature.

## Workflow

1. Restate the user outcome and the non-goals from the request. Ask only if a missing fact would change a Type 1 decision.
2. Classify the work: trivial, normal, large or architecture-sensitive, UI, AI, agent, RAG, security-sensitive, or a combination. Routing rules are in `docs/engineering/delegation-protocol.md`.
3. Have the explorer inspect the repository. Do not plan from memory of files you have not seen.
4. Record constraints and invariants you can already defend.
5. Consult only the specialists the classification requires. They advise; they do not start coding.
6. Analyze architecture. Mark Type 1 choices. Write an ADR outline only when a Type 1 choice is being made, using `docs/templates/architecture-decision.md`.
7. Analyze security: trust boundary, authz, untrusted content, and secrets.
8. Define the test strategy and, when behavior is probabilistic or retrieval-based, the evaluation strategy.
9. Write the plan with `docs/templates/implementation-plan.md`.
10. If the protocol requires human approval, stop and request it. Do not continue into implementation in the same step.

## Specialist routing

- UI: product UI designer, using the design-ui skill, before the plan is frozen.
- Public API or contract change: API/DX engineer.
- AI or model choice: AI/ML engineer.
- Agent behavior or tools: agent runtime engineer, plus AI/ML when model behavior matters.
- Retrieval or embeddings: RAG/data engineer and AI/ML engineer.
- Delivery, CI, or model/prompt versioning: platform/MLOps engineer.
- Security triggers: include a security pass in the plan, and schedule the security reviewer before release.

## Output

Keep these labels explicit:

- Facts
- Assumptions
- Decisions
- Recommendations
- Risks
- Open questions

Unresolved Type 1 choices stay open. They are not silent decisions.

## Prohibitions

Do not write production code. Do not staff every agent. Do not parallelize specialists who are still debating the same Type 1 decision.
