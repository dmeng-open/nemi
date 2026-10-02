---
name: design-ai-agent
description: Specifies a production agent, including state, tools, permissions, failure, evaluation, and cost. Use when designing agent behavior or runtime orchestration.
---

# Design an AI agent

Define a software system. A prompt is not an agent spec.

## Workflow

Fill `docs/templates/ai-agent-spec.md`. For every tool, also follow the design-tool skill.

Define all of the following:

- Goal and user outcome
- Inputs and outputs
- Model and why a simpler method is insufficient
- State, context sources, and memory
- Tools and permissions
- Lifecycle, retries, timeout, and cancellation
- Human approval gates
- Failure semantics
- Observability
- Security boundary
- Evaluation
- Cost controls
- Known limitations

Context is selected. List what is included and what is deliberately excluded.

Use more than one agent only when specialization, context isolation, permission isolation, independent review, parallel work, or a separate failure domain pays for the coordination cost. If you do, define ownership, parent and child, handoff contracts, cancellation, failure propagation, resource limits, and tracing.

## Prohibitions

Do not grant a tool because it might be useful later. Do not let retrieved or user content authorize permissions. Do not implement the runtime in this skill.
