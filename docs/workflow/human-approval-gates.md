# Human approval gates

These actions require a human. An agent may prepare them and then stop.

## Always

- Merge into `main` or `master`, including `gh pr merge`
- Force-push, `--force-with-lease`, and other history rewrite on shared branches
- Push directly to `main` or `master` (the shell guard denies this rather than asking)
- Bypass branch protection or skip Git hooks (`--no-verify`, `--admin` merge)
- Production deployment
- Production database migration or any destructive database command
- Credential rotation, secret changes, and printing credentials
- IAM or directory changes
- Cloud or cluster resource deletion
- Publishing a GitHub Release or release tag
- Irreversible data deletion outside a clearly local, approved path

## Plan approval

Required before implementation when the work is large or architecture-sensitive, or when a Type 1 decision is being made and is not already accepted.

Not required for a narrow, obvious, reversible change that does not move architecture or a security boundary.

## Not a gate

Type 2 choices: local naming, private helpers, and small file layout. The implementer makes them and mentions them.

## Shell backstop

`.cursor/hooks.json` runs `python .cursor/hooks/guard_shell.py` before matching shell commands. It denies catastrophic and protected-branch writes, and asks for ambiguous pushes, force-pushes of feature branches, hard resets, releases, deploys, and merges. A hook miss does not make the action allowed. Agents still follow this document.
