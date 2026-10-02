---
name: verify-change
description: Independently checks a change by running commands and probing edges, then records evidence and gaps. Use for /verify or before any release step.
---

# Verify a change

Produce evidence. The implementer's summary is a claim, not a result.

## Workflow

1. Read the requirement, the approved plan, and the diff.
2. Write down the expected behavior in observable terms.
3. Choose checks that would fail if that behavior were missing.
4. Run them. Record the command, the working directory, and the result.
5. Exercise one edge and one failure path when they exist.
6. Inspect the tests. Say whether they would catch a regression.
7. For UI changes, follow the visual checks you can actually run and record viewports.
8. For probabilistic AI or retrieval changes, cite evaluation evidence or state that evaluation did not run.
9. Report remaining uncertainty.
10. Set the status to verified, verified with gaps, or not verified, using `docs/templates/verification-report.md`.

## Prohibitions

Do not write "everything looks good" without commands and output. Do not fix defects during verification. Do not commit, push, or merge.
