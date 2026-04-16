---
description: Show the current CrossAI state for a feature
argument-hint: <feature>
---

Show the current CrossAI state for a feature.

Steps:
1. Resolve the feature slug from `$1`.
2. Run:
   `python3 scripts/crossai_cli.py status --feature "$1"`
3. Summarize:
   - current phase
   - worktrees
   - latest artifacts
   - review pass history
   - implementation/review status
