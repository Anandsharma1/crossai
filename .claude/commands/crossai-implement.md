---
description: Run CrossAI implementation in a dedicated worktree
argument-hint: <feature> [--implementer claude|codex] [--session-policy auto|fresh|resume]
---

Use CrossAI to implement a feature in a dedicated worktree.

Execution rules:
- Treat `$1` as the feature slug.
- Default the implementer to `claude` unless the user explicitly says otherwise.
- Reuse an existing worktree if one already exists.
- `--session-policy auto|fresh|resume` controls whether a previously saved native implementation session is reused.
- Persist implementation metadata under `.crossai/<feature>/`.

Steps:
1. Resolve the feature slug and implementer.
2. Run:
   `python3 scripts/crossai_cli.py implement --feature "$1"`
   plus any additional flags in `$ARGUMENTS`.
3. Stream progress live.
4. Report:
   - worktree path
   - branch name
   - implementation log path
   - any follow-up review recommendation
