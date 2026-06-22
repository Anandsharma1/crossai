---
name: crossai-conductor
description: Use CrossAI for adversarial planning, implementation-review loops, and Claude+Codex collaboration with persisted artifacts and worktree-aware execution.
---

# CrossAI Conductor

Use this skill when:
- the user asks for CrossAI, dual-agent debate, or adversarial planning
- the user wants Claude to implement while Codex reviews
- the user wants iterative review/fix passes
- the task benefits from separate worktrees and persisted artifacts

## Operating Principles

- CrossAI artifacts in `.crossai/` are the audit trail.
- Worktree state matters; keep implementation work isolated to the correct worktree.
- Reuse implementer worktrees.
- Default reviewer behavior is fresh per pass, but session reuse is controllable via wrapper flags.
- Prefer the project-local CrossAI wrapper over ad hoc shell commands.

## Commands

- `/crossai-generic` for standalone cross-verification
- `/crossai-plan` for ideation + plan
- `/crossai-implement` for implementation only
- `/crossai-loop` for implementation-review-fix loops
- `/crossai-status` for state inspection

Session policy flags:
- `auto`: reuse an existing native session if one is saved, otherwise start fresh
- `fresh`: ignore any saved native session and start a new one
- `resume`: require an existing native session and continue it

Scope policy flags for planning:
- `adjudicate`: have Claude and Codex classify possible scope drift and merge the result into `scope_decisions.md`
- `interactive`: use manual exclusions after round 0
- `off`: skip scope drift handling

Codex instance flags (on `/crossai-generic`, `/crossai-plan`, `/crossai-implement`, `/crossai-loop`):
- `--codex-cmd CMD`: override the codex binary and top-level flags (e.g. `"codex --yolo"`); sets `CROSSAI_CODEX_CMD`
- `--codex-home PATH`: point Codex at an alternate config dir; sets `CODEX_HOME`
- `--codex-cmd` wins over `--codex-home` for the binary itself; the two may be combined

## Reporting Requirements

Always report:
- feature slug
- active worktree(s)
- artifact paths
- unresolved issues
- whether the current state is ready for another review pass

## Current Limits

- The wrapper fronts planning, implementation, status, and single/multi-pass review-fix loops.
- Planning, implementation, and review-fix flows all support native Claude/Codex session reuse, controlled by wrapper flags.
- Tmux display mode is best-effort and falls back to inline streaming when unavailable.
