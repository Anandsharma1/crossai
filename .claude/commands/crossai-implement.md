---
description: Run CrossAI implementation in a dedicated worktree
argument-hint: <feature> [--implementer claude|codex] [--session-policy auto|fresh|resume] [--codex-home PATH] [--codex-cmd CMD]
---

Use CrossAI to implement a feature in a dedicated worktree.

Execution rules:
- Treat `$1` as the feature slug.
- Default the implementer to `claude` unless the user explicitly says otherwise.
- Reuse an existing worktree if one already exists.
- `--session-policy auto|fresh|resume` controls whether a previously saved native implementation session is reused.
- If `--codex-home PATH` appears in `$ARGUMENTS`, extract it, strip it from the passthrough args, and set `CODEX_HOME=PATH` as an env var prefix on the Python call.
- If `--codex-cmd CMD` appears in `$ARGUMENTS`, extract it, strip it from the passthrough args, and set `CROSSAI_CODEX_CMD=CMD` as an env var prefix (overrides the codex binary and any top-level flags, e.g. `"codex --yolo"`). Takes precedence over `--codex-home` for the binary itself; both may be used together.
- Pass any remaining flags from `$ARGUMENTS` through to the wrapper.
- Persist implementation metadata under `.crossai/<feature>/`.

Steps:
1. Resolve the feature slug and implementer.
2. Run:
   `CROSSAI_CODEX_CMD="..." CODEX_HOME="..." python3 scripts/crossai_cli.py implement --feature "$1"`
   plus any additional flags in `$ARGUMENTS`. Omit env var prefixes that were not supplied.
3. Stream progress live.
4. Report:
   - worktree path
   - branch name
   - implementation log path
   - any follow-up review recommendation
