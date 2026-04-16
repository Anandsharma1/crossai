---
description: Run standalone CrossAI cross-verification for any task
argument-hint: <feature> <prompt-file|--prompt-text "..."> [--rounds N] [--session-policy auto|fresh|resume] [--read-codebase] [--display-mode inline|tmux] [--force]
---

Use CrossAI to cross-verify any standalone task prompt.

Execution rules:
- Treat `$1` as the feature slug.
- If `$2` is a file path that exists, treat it as the prompt file and pass `--prompt "$2"` to the wrapper.
- If the user provided inline prompt text instead of a file path, pass it through as `--prompt-text "<text>"` (exactly one of `--prompt` or `--prompt-text` is required).
- Pass any remaining flags from `$ARGUMENTS` through to the wrapper.
- `--session-policy auto|fresh|resume` controls whether prior native generic sessions are reused.
- Keep all artifacts under `.crossai/<feature>/generic/`.

Steps:
1. Verify the feature slug and prompt path are present.
2. Run either:
   `python3 scripts/crossai_cli.py generic --feature "$1" --prompt "$2"`
   or (for inline text):
   `python3 scripts/crossai_cli.py generic --feature "$1" --prompt-text "<text>"`
   plus any extra arguments included in `$ARGUMENTS`.
3. Stream progress to the terminal.
4. When complete, summarize:
   - final artifact paths
   - latest responses
   - any important disagreements that remained
