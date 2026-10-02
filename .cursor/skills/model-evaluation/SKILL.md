---
name: model-evaluation
description: Compares candidate models on quality, latency, cost, structured output, and operational fit. Use when selecting or replacing a model.
---

# Evaluate models

Compare models against the product constraint. A leaderboard does not replace your dataset.

## Workflow

1. State the task, the constraint that matters most, and the simpler method you are not using.
2. Select candidates, including an open-source option when deployment or data control requires it.
3. Compare, with evidence where you can run them and explicit unknowns where you cannot:
   - Quality on the versioned set
   - Latency
   - Cost
   - Structured-output reliability
   - Tool-use behavior, if tools are in scope
   - Context the task actually needs
   - Memory and throughput, if self-hosted
   - Deployment complexity
4. Run the same evaluation through the run-evals skill when outputs can be scored.
5. Recommend one candidate and the condition that would reverse the choice.

## Prohibitions

Do not pick the largest model by default. Do not report numbers you did not measure.
