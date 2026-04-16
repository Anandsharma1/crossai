---
description: Run the CrossAI implementation-review-fix loop
argument-hint: <feature> [--implementer claude|codex] [--reviewer claude|codex] [--passes N] [--implementer-session-policy auto|fresh|resume] [--reviewer-session-policy auto|fresh|resume] [--display-mode inline|tmux]
---

Run the CrossAI implementation-review-fix loop.

Workflow policy:
- Keep the implementer worktree stable across passes.
- Start a fresh reviewer run for each review pass.
- Save every review artifact under `.crossai/<feature>/reviews/`.
- `--implementer-session-policy` controls whether the implementer starts from an existing native session.
- `--reviewer-session-policy` controls whether the reviewer starts fresh or reuses the previous review session chain.
- If tmux display mode is unavailable, fall back to inline mode.

Steps:
1. Resolve:
   - feature slug from `$1`
   - implementer (`claude` default)
   - reviewer (`codex` default)
   - passes (`3` default)
   - display mode (`inline` default)
2. Run:
   `python3 scripts/crossai_cli.py loop --feature "$1"`
   plus any additional flags in `$ARGUMENTS`.
3. Stream the active pass status live.
4. When complete, summarize:
   - worktree used
   - review pass artifacts
   - unresolved findings
   - whether another pass is recommended
