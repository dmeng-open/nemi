# Skill coverage

Commands are the user-facing entry points. Skills are the process. Agents are the roles. Templates are the output shape.

| Skill | Command | Primary role | Template |
| --- | --- | --- | --- |
| plan-feature | `/plan-feature` | planner, coordinated by orchestrator | implementation-plan |
| implement-feature | `/implement-feature` | implementer | — |
| fix-bug | `/fix-bug` | implementer | — |
| design-ui | `/design-ui` | product UI designer | ui-spec |
| implement-ui | `/implement-ui` | frontend design engineer | ui-spec |
| visual-review | invoked after implement-ui | independent of the implementer | — |
| design-ai-agent | invoked from AI/agent planning | agent runtime engineer | ai-agent-spec |
| design-tool | invoked with agent or tool design | agent runtime engineer | — |
| design-rag | invoked from retrieval planning | RAG/data engineer | evaluation-plan |
| run-evals | `/run-evals` | AI/ML engineer or verifier of eval artifacts | evaluation-plan |
| model-evaluation | with `/run-evals` when selecting a model | AI/ML engineer | evaluation-plan |
| review-change | `/review` | reviewer | — |
| security-review | `/security-review` | security reviewer | security-review |
| verify-change | `/verify` | verifier | verification-report |
| prepare-pr | `/prepare-pr` | release engineer | pull request template |
| release | `/release` | release engineer | release-report |

Feature specs use `docs/templates/feature-spec.md` when the requirement itself needs a product statement before planning. Architecture decisions use `docs/templates/architecture-decision.md` for Type 1 choices.

Rules in `.cursor/rules/` constrain the work those skills perform. They do not replace the skill's order of steps.
