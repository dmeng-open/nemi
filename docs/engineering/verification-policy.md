# Verification policy

Verification is independent of implementation. The verifier runs checks and writes `docs/templates/verification-report.md`. The implementer's summary does not count as the report.

## What to run

Choose the smallest set that would fail if the claimed behavior were absent: unit, integration, contract, API, browser, regression, or an already produced evaluation. Maximize confidence, not count.

## Evidence

Record the command, the environment, and the result. For UI, name the viewports actually inspected. For AI, link the evaluation or say it did not run. For an integration that was down, say it was not exercised.

Allowed statuses:

- verified
- verified with gaps
- not verified

"Everything looks good" is not a status.

## Limits

The verifier does not fix the product, commit, push, or merge. Defects go back to the implementer. Release work starts only after a verification report exists.
