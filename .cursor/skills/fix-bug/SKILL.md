---
name: fix-bug
description: Reproduces a bug, finds the root cause, adds a regression test, and applies a narrow fix. Use for /fix-bug or when correcting a defect.
---

# Fix a bug

Fix the cause. Do not patch past a misunderstood failure.

## Workflow

1. Restate the bug as expected behavior versus actual behavior.
2. Reproduce it, or state exactly why reproduction was impossible.
3. Reduce the reproduction to the smallest input and path that still fails.
4. Trace the execution path. Name the failing assumption.
5. Identify the root cause. If the cause is an architectural or security defect, stop and route through planning and the security reviewer as required.
6. Write a failing regression test when the project can host one.
7. Implement the narrowest fix that makes that test pass for the right reason.
8. Re-run the regression and the nearby tests.
9. Review unintended effects: callers, persisted data, and error paths.
10. Hand off to review and verification. Do not release it yourself.

## Escalation

Return to the planner when the fix needs a contract change, a migration, or a new security boundary.

## Prohibitions

Do not silence the error, retry blindly, or special-case the reported input while the general case remains broken.
