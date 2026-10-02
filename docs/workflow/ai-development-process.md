# AI development process

```text
Define the behavior
  → choose the least powerful method
  → design retrieval, tools, or agents only if simpler methods fail
  → plan
  → implement
  → evaluate
  → review
  → verify
```

Method order is in `.cursor/rules/ai-engineering.mdc`: deterministic software, traditional ML, prompting or structured generation, retrieval, tools, agent orchestration, open-source specialization, fine-tuning.

## Evaluation is not unit testing

Deterministic tests check schemas, guards, and branching. They do not measure answer quality, retrieval rank, or tool judgment. Those use `.cursor/skills/run-evals/SKILL.md` and `docs/templates/evaluation-plan.md`.

An evaluation has a versioned dataset, a baseline, a candidate, metrics, and saved configuration. LLM-as-judge may be one noisy signal. It is not ground truth.

Fine-tuning is allowed only with a measured deficiency, a baseline, a dataset, a hypothesis, a metric, an expected benefit, and a cost justification.

Agent and tool designs use `.cursor/skills/design-ai-agent/SKILL.md` and `.cursor/skills/design-tool/SKILL.md`. RAG designs use `.cursor/skills/design-rag/SKILL.md` and include retrieval metrics.

Prompt, model, embedding, retrieval, and agent-definition changes that affect users are versioned and evaluated before they are treated as ready. See `.cursor/rules/evaluations.mdc`.
