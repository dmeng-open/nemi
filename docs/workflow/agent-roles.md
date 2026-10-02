# Agent roles

Role prompts live in `.cursor/agents/`. Authority is the constraint. Capability does not raise it.

| Agent | Capability | Authority | Writes product code |
| --- | --- | --- | --- |
| Orchestrator | Principal / tech lead | Medium. Trivial edits only. | Only trivial, low-risk fixes |
| Explorer | Senior / staff | Read only | No |
| Planner | Principal | Read only | No |
| Product UI designer | Senior product designer | Spec only | No |
| Frontend design engineer | Staff frontend | Frontend implementation from an approved spec | UI only |
| AI/ML engineer | Staff AI/ML | Read only | No |
| Agent runtime engineer | Principal AI systems | Read only | No |
| RAG/data engineer | Staff retrieval | Read only | No |
| API/DX engineer | Staff API | Read only | No |
| Platform/MLOps engineer | Staff platform | Read only. No production provisioning | No |
| Implementer | Staff implementation | Application code from an approved plan | Yes |
| Reviewer | Principal | Read only | No |
| Security reviewer | Principal, security | Read only | No |
| Verifier | Senior / staff | Local checks and browser. No product edits | No |
| Release engineer | Staff / principal release | Git and PR on non-protected branches | No |

The reviewer does not replace the security reviewer or the verifier. The release engineer does not replace the verifier. Domain specialists specify; the implementer and the frontend design engineer build.
