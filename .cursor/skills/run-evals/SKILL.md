---
name: run-evals
description: Runs a versioned baseline-versus-candidate evaluation and records evidence. Use for /run-evals, prompt or model changes, retrieval quality, or agent behavior.
---

# Run evaluations

Measure a behavior change. Do not certify quality from a few impressive examples.

## Workflow

1. Define the target behavior in observable terms.
2. Choose a versioned dataset. Record its version and what it does not cover.
3. Define metrics and any deterministic assertions.
4. Run the baseline and keep the artifact.
5. Run the candidate with the same data and rubric.
6. Compare quality, latency, and cost.
7. Analyze failures, including cases the metric hides.
8. Store enough configuration to repeat the run: model, prompt version, retrieval config, and dataset version.
9. Recommend keep, revise, or reject. Tie the recommendation to the comparison.

Use `docs/templates/evaluation-plan.md` for the plan and record results against it. When the question is which model to run, also follow the model-evaluation skill.

LLM-as-judge may be one signal. It is not unquestionable ground truth. Prefer exact or schema checks where the output allows them.

## Prohibitions

Do not change the dataset between baseline and candidate without saying so. Do not drop failures to improve the score.
