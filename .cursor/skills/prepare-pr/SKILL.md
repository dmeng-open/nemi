---
name: prepare-pr
description: Prepares a logical commit and pull request on a non-protected branch after review and verification. Use for /prepare-pr when the user wants a PR.
---

# Prepare a pull request

Package verified work. Do not implement the feature in this skill.

## Workflow

1. Confirm the user asked to commit or open a pull request.
2. Confirm the branch is not `main` or `master`. Create a `feature/`, `fix/`, or `chore/` branch if the work is still on a protected branch locally and that move is safe.
3. Inspect status and diff. Exclude secrets and unrelated files.
4. Confirm review status. If security review was required, confirm it happened.
5. Confirm verification evidence exists and read the gaps. If verification did not run, stop.
6. Stage a logical commit. The message states why the change exists.
7. Push only a non-protected branch.
8. Open or update the pull request from `.github/pull_request_template.md`.

## Pull request body

Include only the sections that apply:

- What
- Why
- Architecture
- UI / UX
- AI / ML
- Testing
- Evaluation
- Security
- Migration
- Risks
- Screenshots / visual verification

Testing and evaluation sections must match evidence that exists. If a section has nothing honest to say, delete it.

## Prohibitions

Do not merge. Do not force-push. Do not use `--no-verify` unless the user explicitly approved it. Do not push to `main` or `master`.
