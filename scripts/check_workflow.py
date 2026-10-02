#!/usr/bin/env python3
"""Check that the engineering workflow files agree with each other."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

AGENTS = {
    "orchestrator": False,
    "explorer": True,
    "planner": True,
    "product-ui-designer": True,
    "frontend-design-engineer": False,
    "ai-ml-engineer": True,
    "agent-runtime-engineer": True,
    "rag-data-engineer": True,
    "api-dx-engineer": True,
    "platform-mlops-engineer": True,
    "implementer": False,
    "reviewer": True,
    "security-reviewer": True,
    "verifier": False,
    "release-engineer": False,
}

AGENT_SECTIONS = [
    "## Purpose",
    "## Capability",
    "## Authority",
    "## Responsibilities",
    "## Expected inputs",
    "## Expected outputs",
    "## Escalation",
    "## Prohibitions",
]

SKILLS = [
    "plan-feature",
    "implement-feature",
    "fix-bug",
    "design-ui",
    "implement-ui",
    "visual-review",
    "design-ai-agent",
    "design-tool",
    "design-rag",
    "run-evals",
    "model-evaluation",
    "review-change",
    "security-review",
    "verify-change",
    "prepare-pr",
    "release",
]

COMMANDS = {
    "plan-feature": "plan-feature",
    "implement-feature": "implement-feature",
    "fix-bug": "fix-bug",
    "design-ui": "design-ui",
    "implement-ui": "implement-ui",
    "review": "review-change",
    "security-review": "security-review",
    "verify": "verify-change",
    "run-evals": "run-evals",
    "prepare-pr": "prepare-pr",
    "release": "release",
}

RULES = [
    "core-engineering.mdc",
    "architecture.mdc",
    "planning.mdc",
    "python.mdc",
    "typescript.mdc",
    "frontend.mdc",
    "ui-ux.mdc",
    "backend.mdc",
    "api-design.mdc",
    "ai-engineering.mdc",
    "agent-runtime.mdc",
    "rag-data.mdc",
    "evaluations.mdc",
    "security.mdc",
    "testing.mdc",
    "observability.mdc",
    "git-release.mdc",
]

DOCS = [
    "docs/engineering/engineering-principles.md",
    "docs/engineering/development-workflow.md",
    "docs/engineering/delegation-protocol.md",
    "docs/engineering/definition-of-done.md",
    "docs/engineering/verification-policy.md",
    "docs/engineering/skill-coverage-framework.md",
    "docs/workflow/agent-roles.md",
    "docs/workflow/planning-process.md",
    "docs/workflow/review-process.md",
    "docs/workflow/ui-development-process.md",
    "docs/workflow/ai-development-process.md",
    "docs/workflow/release-process.md",
    "docs/workflow/human-approval-gates.md",
    "docs/workflow/delegation-example.md",
    "docs/templates/implementation-plan.md",
    "docs/templates/architecture-decision.md",
    "docs/templates/feature-spec.md",
    "docs/templates/ui-spec.md",
    "docs/templates/ai-agent-spec.md",
    "docs/templates/evaluation-plan.md",
    "docs/templates/security-review.md",
    "docs/templates/verification-report.md",
    "docs/templates/release-report.md",
]

TEMPLATE_HEADINGS = {
    "docs/templates/implementation-plan.md": [
        "# Goal",
        "# User / Business Outcome",
        "# Facts",
        "# Assumptions",
        "# Human Approval Requirements",
    ],
    "docs/templates/ui-spec.md": [
        "# User Goal",
        "# Loading State",
        "# Empty State",
        "# Error State",
        "# Accessibility",
    ],
    "docs/templates/ai-agent-spec.md": [
        "# Purpose",
        "# Tools",
        "# Permissions",
        "# Security Boundary",
        "# Evaluation",
    ],
    "docs/templates/verification-report.md": [
        "# Commands Executed",
        "# Results",
        "# Known Gaps",
        "# Final Verification Status",
    ],
}


def frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    data: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def main() -> int:
    errors: list[str] = []

    for name, readonly in AGENTS.items():
        path = ROOT / ".cursor" / "agents" / f"{name}.md"
        if not path.exists():
            errors.append(f"missing agent {path}")
            continue
        text = path.read_text(encoding="utf-8")
        meta = frontmatter(text)
        if meta.get("name") != name:
            errors.append(f"{path} name is {meta.get('name')!r}")
        expected = "true" if readonly else "false"
        if meta.get("readonly") != expected:
            errors.append(f"{path} readonly is {meta.get('readonly')!r}, expected {expected}")
        for section in AGENT_SECTIONS:
            if section not in text:
                errors.append(f"{path} missing {section}")

    for skill in SKILLS:
        path = ROOT / ".cursor" / "skills" / skill / "SKILL.md"
        if not path.exists():
            errors.append(f"missing skill {path}")
            continue
        text = path.read_text(encoding="utf-8")
        meta = frontmatter(text)
        if meta.get("name") != skill:
            errors.append(f"{path} name is {meta.get('name')!r}")
        if "## Workflow" not in text and "## Output" not in text:
            errors.append(f"{path} missing workflow section")

    for command, skill in COMMANDS.items():
        path = ROOT / ".cursor" / "commands" / f"{command}.md"
        if not path.exists():
            errors.append(f"missing command {path}")
            continue
        needle = f".cursor/skills/{skill}/SKILL.md"
        if needle not in path.read_text(encoding="utf-8"):
            errors.append(f"{path} does not reference {needle}")

    for rule in RULES:
        path = ROOT / ".cursor" / "rules" / rule
        if not path.exists():
            errors.append(f"missing rule {path}")
            continue
        text = path.read_text(encoding="utf-8")
        if "alwaysApply:" not in text or "description:" not in text:
            errors.append(f"{path} missing rule frontmatter")

    for relative in DOCS:
        if not (ROOT / relative).exists():
            errors.append(f"missing doc {relative}")

    for relative, headings in TEMPLATE_HEADINGS.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for heading in headings:
            if heading not in text:
                errors.append(f"{relative} missing {heading}")

    constitution = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for phrase in [
        "Correctness",
        "Capability is not authority",
        "No fake certainty",
        "/plan-feature",
        "/verify",
        "/prepare-pr",
    ]:
        if phrase not in constitution:
            errors.append(f"AGENTS.md missing {phrase}")

    delegation = (ROOT / "docs/engineering/delegation-protocol.md").read_text(encoding="utf-8")
    for phrase in [
        "Security-sensitive",
        "Verifier, then release engineer",
        "Human plan approval",
    ]:
        if phrase not in delegation:
            errors.append(f"delegation protocol missing {phrase}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("workflow consistency checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
