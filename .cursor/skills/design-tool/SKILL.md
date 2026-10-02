---
name: design-tool
description: Specifies an agent or model tool contract, including schema, authorization, side effects, idempotency, and approval. Use when adding or changing a tool.
---

# Design a tool

Specify the contract before anyone binds it to a model.

## Workflow

Define each item:

- Purpose and the caller
- Input schema and output schema
- Authorization, including tenant and resource context
- Side effects
- Idempotency
- Timeout and retries
- Whether a human must approve the call
- Auditability
- Error semantics
- What the model is not allowed to decide

Arguments produced by a model are untrusted input. Validation and authorization happen in code before the side effect.

## Prohibitions

Do not accept free-form shell or URL fields without a constraint that the product can enforce. Do not make a tool "admin" to simplify the first version.
