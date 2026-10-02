---
name: release
description: Prepares release notes, version metadata, and a release report, then stops at human approval. Use for /release when the user intends a release.
---

# Prepare a release

Prepare the release. A human approves publishing it.

## Workflow

1. Confirm the user asked for a release and which version or range is in scope.
2. Confirm the source commit and that CI for it is known. If CI was not inspected, say so.
3. Confirm verification evidence for the changes included.
4. Inspect compatibility, migrations, and rollback.
5. Inspect release risk: data, downtime, and irreversible steps.
6. Draft release notes from user-visible behavior, not from a file list.
7. Prepare version or tag changes only if repository policy allows the preparation.
8. Fill `docs/templates/release-report.md`.
9. Publish a tag or GitHub Release only when the current user request explicitly authorizes that exact publication. Otherwise stop and name the missing approval. Deployment and production migration always stop for a separate approval.

## Prohibitions

Do not deploy. Do not mutate production. Do not publish a tag or GitHub Release unless this request explicitly authorized that publication. Do not treat this skill as a substitute for verification.
