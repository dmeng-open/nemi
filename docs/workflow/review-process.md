# Review process

Two reviews are different jobs.

## Engineering review

The reviewer follows `.cursor/skills/review-change/SKILL.md`. They read the requirement, the plan, and the diff. They look for the assumption that would make the change fail. Findings are blocking, should-fix, or note. Green CI is not an approval.

## Security review

The security reviewer follows `.cursor/skills/security-review/SKILL.md` when delegation triggers apply. The engineering reviewer may notice a security issue and must still hand off rather than close it.

## Visual review

UI changes get `.cursor/skills/visual-review/SKILL.md` from someone other than the implementing agent.

## Evaluation

AI and retrieval changes need evaluation evidence before review can call the behavior acceptable. Review checks that the evidence exists and matches the claim. Review does not invent a score.

## Order

Evaluation and visual review can proceed beside engineering review when they do not depend on an unresolved design change. Security review can run beside engineering review. Verification follows the reviews that the change required, and it is still independent.
