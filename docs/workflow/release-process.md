# Release process

```text
Verifier
  → release engineer
  → commit on a feature branch
  → push the non-protected branch
  → pull request
  → CI
  → human merge
  → release or deploy only with explicit approval
```

Branch names: `feature/<description>`, `fix/<description>`, `chore/<description>`. `main` is the protected integration branch.

Commit messages state intent. "Update files" and "fix stuff" are not messages. Conventional Commits are not required unless a later policy adopts them.

The pull request uses `.github/pull_request_template.md` and drops empty sections. Claims in Testing, Evaluation, and Screenshots must match evidence.

The release skill prepares notes and `docs/templates/release-report.md`. It does not publish a tag or GitHub Release unless the user explicitly approved that publication. Deployment, production migration, and IAM changes are separate human gates.

## Prohibited without explicit human approval

Protected-branch merge, force-push, hook bypass, shared history rewrite, production deploy, production database mutation, credential rotation, IAM changes, and irreversible release publication.

The shell guard in `.cursor/hooks/guard_shell.py` blocks or asks for a subset of these commands. The policy here is the full rule. The hook is only a backstop.
