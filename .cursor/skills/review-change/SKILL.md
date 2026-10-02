---
name: review-change
description: Reviews a diff against the requirement and plan for correctness, architecture, data integrity, tests, and operability. Use for /review or after implementation.
---

# Review a change

Review as an independent reader. Green tests are not approval.

## Workflow

1. Read the requirement and the approved plan.
2. Read the diff. Note unexplained files.
3. Check correctness against the expected behavior, including a failure path.
4. Check architecture. Confirm Type 1 decisions were not drifted.
5. Check API contracts and compatibility.
6. Check data integrity, concurrency, and tenancy where relevant.
7. Check authorization and untrusted input. If security triggers apply, require the security-review skill rather than substituting a paragraph.
8. Check tests. A test that cannot fail is not coverage.
9. Check observability and operational impact: migrations, retries, and rollback.
10. Report findings by severity: blocking, should-fix, and note. End with approved or not approved, plus residual risk.

Ask: "What assumption would make this implementation fail?"

## Prohibitions

Do not spend the review on formatting. Do not edit the code in this skill. Do not approve work that skipped a required security review or a required evaluation.
