---
description: Run the CrossAI implementation-review-fix loop
argument-hint: <feature> [--implementer claude|codex] [--reviewer claude|codex] [--passes N] [--implementer-session-policy auto|fresh|resume] [--reviewer-session-policy auto|fresh|resume] [--display-mode inline|tmux] [--codex-home PATH] [--codex-cmd CMD]
---

Run the CrossAI implementation-review-fix loop.

Workflow policy:
- Keep the implementer worktree stable across passes.
- Start a fresh reviewer run for each review pass.
- Save every review artifact under `.crossai/<feature>/reviews/`.
- `--implementer-session-policy` controls whether the implementer starts from an existing native session.
- `--reviewer-session-policy` controls whether the reviewer starts fresh or reuses the previous review session chain.
- If tmux display mode is unavailable, fall back to inline mode.
- If `--codex-home PATH` appears in `$ARGUMENTS`, extract it, strip it from the passthrough args, and set `CODEX_HOME=PATH` as an env var prefix on the Python call.
- If `--codex-cmd CMD` appears in `$ARGUMENTS`, extract it, strip it from the passthrough args, and set `CROSSAI_CODEX_CMD=CMD` as an env var prefix (overrides the codex binary and any top-level flags, e.g. `"codex --yolo"`). Takes precedence over `--codex-home` for the binary itself; both may be used together.

Steps:
1. Resolve:
   - feature slug from `$1`
   - implementer (`claude` default)
   - reviewer (`codex` default)
   - passes (`3` default)
   - display mode (`inline` default)
2. Run:
   `CROSSAI_CODEX_CMD="..." CODEX_HOME="..." python3 scripts/crossai_cli.py loop --feature "$1"`
   plus any additional flags in `$ARGUMENTS`. Omit env var prefixes that were not supplied.
3. Stream the active pass status live.
4. When complete, summarize:
   - worktree used
   - review pass artifacts
   - unresolved findings
   - whether another pass is recommended
