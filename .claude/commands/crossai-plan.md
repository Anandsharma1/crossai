---
description: Run CrossAI ideation and planning for a feature
argument-hint: <feature> <prompt-file|--prompt-text "..."> [--rounds N] [--session-policy auto|fresh|resume] [--scope-policy adjudicate|interactive|off] [--read-codebase] [--display-mode inline|tmux] [--force]
---

Use CrossAI to run ideation and planning for the requested feature.

Execution rules:
- Treat `$1` as the feature slug.
- If `$2` is a file path that exists, treat it as the prompt file and pass `--prompt "$2"` to the wrapper.
- If the user provided inline prompt text instead of a file path, pass it through as `--prompt-text "<text>"` (exactly one of `--prompt` or `--prompt-text` is required).
- Pass any remaining flags from `$ARGUMENTS` through to the wrapper.
- `--session-policy auto|fresh|resume` controls whether prior native debate sessions are reused for this feature/phase.
- `--scope-policy adjudicate|interactive|off` controls how round-0 scope drift is handled.
- Prefer the project-local wrapper over ad hoc manual debate steps.
- Keep all artifacts under `.crossai/<feature>/`.

Steps:
1. Verify the feature slug and prompt path are present.
2. Run either:
   `python3 scripts/crossai_cli.py plan --feature "$1" --prompt "$2"`
   or (for inline text):
   `python3 scripts/crossai_cli.py plan --feature "$1" --prompt-text "<text>"`
   plus any extra arguments included in `$ARGUMENTS`.
3. Stream progress to the terminal.
4. When complete, summarize:
   - final artifact paths
   - latest debate outputs
   - unresolved questions

If the wrapper is missing or fails before starting, fall back to:
- `python3 .crossai/orchestrate.py --feature "$1" --prompt "$2" --phase ideation`
- `python3 .crossai/orchestrate.py --feature "$1" --phase plan`
