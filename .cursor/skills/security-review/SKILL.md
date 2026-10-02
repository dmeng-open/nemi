---
name: security-review
description: Reviews trust boundaries, authz, secrets, untrusted content, and agent-tool authority. Use for /security-review and for auth, uploads, tools, or tenant-sensitive changes.
---

# Security review

Trace who can cause which side effect. Instruction text is not a control.

## Workflow

Fill `docs/templates/security-review.md` while examining:

- Trust boundaries
- Authentication and authorization
- Tenant and resource isolation
- Secrets and credential handling
- User-controlled input
- External content, URLs, webhooks, and SSRF
- Filesystem access
- Network access
- Agent tool permissions and argument validation
- Prompt injection and indirect prompt injection
- Data exfiltration
- Logging of secrets or sensitive content
- Destructive or privileged actions
- Confused-deputy paths, where a trusted component acts on an attacker's input

## Triggers

Run this review when the change touches auth, authorization, secrets, uploads, external URLs, webhooks, filesystem access, agent tools, privileged actions, organization or tenant access, or arbitrary execution.

## Output

Findings first, ordered by severity. Each blocking finding names the abuse case and the required fix. Residual risk is explicit. "No issues found" still lists what was inspected.

## Prohibitions

Do not accept a system prompt as enforcement. Do not implement the fix in this pass.
