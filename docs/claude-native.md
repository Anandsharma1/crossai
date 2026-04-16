# Claude-Native Workflow

This guide documents the newer CrossAI entrypoint:

```bash
python3 scripts/crossai_cli.py ...
```

Use this when you want:
- native Claude/Codex session reuse
- project-local Claude Code commands under `.claude/commands/`
- implementation-review-fix loops
- explicit control over session reuse and scope handling

If you want the older artifact-first flow, use `orchestrate.py` instead. See [The Phases](phases.md).

---

## High-level model

The Claude-native wrapper keeps the original CrossAI artifact model, but adds native CLI session continuity.

It does three things at once:

1. Runs Claude and Codex as real CLI sessions
2. Persists feature state in `.crossai/<feature>/`
3. Exposes a Claude-friendly command surface

The main commands are:

```bash
python3 scripts/crossai_cli.py generic ...
python3 scripts/crossai_cli.py plan ...
python3 scripts/crossai_cli.py implement ...
python3 scripts/crossai_cli.py review ...
python3 scripts/crossai_cli.py loop ...
python3 scripts/crossai_cli.py status ...
```

Inside Claude Code, the project-local aliases are:

- `/crossai-generic`
- `/crossai-plan`
- `/crossai-implement`
- `/crossai-loop`
- `/crossai-status`

---

## Recommended flow

### 0. Generic cross-verification

```bash
python3 scripts/crossai_cli.py generic \
  --feature table-descriptions \
  --prompt prompt.md \
  --session-policy fresh
```

Use this for standalone tasks that do not need the full ideation -> plan -> implement pipeline.

### 1. Plan

```bash
python3 scripts/crossai_cli.py plan \
  --feature user-auth \
  --prompt prompt.md \
  --session-policy fresh \
  --scope-policy adjudicate
```

What happens:
- runs native ideation debate
- runs native plan debate
- writes ideation and plan artifacts
- stores debate session ids in `sessions.json`
- stores current state in `run_state.json`
- writes scope artifacts if scope handling is enabled

### 2. Implement

```bash
python3 scripts/crossai_cli.py implement \
  --feature user-auth \
  --implementer claude \
  --session-policy auto
```

What happens:
- creates or reuses `wt-user-auth-claude/`
- loads the latest Claude plan
- starts or resumes Claude’s native implementation session
- writes implementation logs and updates `sessions.json`

### 3. Run the loop

```bash
python3 scripts/crossai_cli.py loop \
  --feature user-auth \
  --implementer claude \
  --reviewer codex \
  --passes 3 \
  --implementer-session-policy auto \
  --reviewer-session-policy fresh
```

What happens:
- Claude implements in a sticky session
- Codex reviews in a fresh review pass by default
- Claude resumes and applies the review
- repeat for `N` passes

### 4. Inspect state

```bash
python3 scripts/crossai_cli.py status --feature user-auth
```

This prints JSON showing:
- current phase/status
- worktree locations
- saved Claude session ids / Codex thread ids
- review pass history

---

## Session policies

Session policy controls whether CrossAI starts fresh or continues an existing native session.

Available values:

- `auto`
- `fresh`
- `resume`

### `auto`

- reuse a saved native session if one exists
- otherwise start a new one

Use this for day-to-day work.

### `fresh`

- ignore any saved native session
- start a new session even if one exists

Use this when:
- you want a clean rerun
- prior session state is misleading
- you are re-planning a feature from scratch

### `resume`

- require an existing native session
- fail if there is no saved session to continue

Use this when:
- continuity matters and you do not want silent fallback
- you are intentionally continuing prior generic, debate, or implementation state

### Where session ids are stored

In:

```text
.crossai/<feature>/sessions.json
```

Claude entries store `session_id`.
Codex entries store `thread_id`.

---

## Scope policies

Scope policy applies to `plan`.

Available values:

- `adjudicate`
- `interactive`
- `off`

### `adjudicate` (recommended)

After round 0:
- CrossAI generates candidate scope drift items
- Claude and Codex each classify them
- CrossAI merges those into `scope_decisions.md`
- the resulting constraints are injected into later rounds

This is the best default when you want low interruption but still want a documented scope decision trail.

### `interactive`

After round 0:
- CrossAI lists candidate drift items
- you manually exclude items by number or free text
- exclusions are injected into later rounds

Use this when you want a hard human gate.

### `off`

- do not run scope handling

Use this only when you already trust the prompt and the debate boundaries.

### Scope artifacts

Depending on policy, CrossAI may write:

```text
.crossai/<feature>/<phase>/scope_candidates.md
.crossai/<feature>/<phase>/scope_adjudication.claude.md
.crossai/<feature>/<phase>/scope_adjudication.codex.md
.crossai/<feature>/<phase>/scope_decisions.md
```

---

## Artifact layout

Typical layout:

```text
.crossai/<feature>/
  sessions.json
  run_state.json
  generic/
    initial_prompt.md
    r0/
    r1/
    ...
    generic_summary.md
  ideation/
    initial_prompt.md
    r0/
    r1/
    ...
    scope_candidates.md
    scope_decisions.md
    ideation_summary.md
  plan/
    initial_prompt.md
    r0/
    r1/
    ...
    scope_candidates.md
    scope_decisions.md
    plan_summary.md
  implementation/
    claude.log.md
    pass-1.claude.applies_review.md
    ...
  reviews/
    pass-1.codex.reviews_claude.md
    pass-2.codex.reviews_claude.md
    ...
```

Worktrees live next to the repo root:

```text
wt-<feature>-claude/
wt-<feature>-codex/
```

`wt` means `worktree`.

---

## How the wrapper differs from the legacy orchestrator

### Legacy `orchestrate.py`

- artifact-first
- no native session reuse
- interactive scope check
- original implementation/review phases

### Claude-native `crossai_cli.py`

- artifact-first plus native session reuse
- standalone `generic` support
- Claude-native commands in `.claude/`
- sticky implementer sessions
- configurable reviewer reuse
- configurable scope handling
- explicit `status` command

The two systems can coexist. Use the wrapper for the newer flow and keep `orchestrate.py` for compatibility.

---

## Claude Code integration

Project-local integration files:

```text
.claude/
  commands/
  skills/
  agents/
  settings.json
```

Relevant files:
- `.claude/commands/crossai-generic.md`
- `.claude/commands/crossai-plan.md`
- `.claude/commands/crossai-implement.md`
- `.claude/commands/crossai-loop.md`
- `.claude/commands/crossai-status.md`
- `.claude/skills/crossai-conductor/SKILL.md`

These are wrappers and workflow hints. The actual execution logic remains in `scripts/crossai_cli.py`.
Installed projects point their Claude hooks at `.crossai/crossai_hook.py`, which the installer
creates as a stable shim for both repo-level and user-level layouts.

---

## Display modes

Review and loop commands support:

- `inline`
- `tmux`

### `inline`

- output is streamed in the current terminal
- simplest and most robust mode

### `tmux`

- if you are already in tmux, CrossAI can open a split pane for command output
- if tmux is unavailable, it falls back to `inline`

Use `inline` unless you specifically want pane-based visibility.

---

## Recommended defaults

For most users:

### Planning

```bash
python3 scripts/crossai_cli.py plan \
  --feature <name> \
  --prompt <file> \
  --session-policy fresh \
  --scope-policy adjudicate
```

### Continue planning later

```bash
python3 scripts/crossai_cli.py plan \
  --feature <name> \
  --prompt <file> \
  --session-policy resume \
  --scope-policy adjudicate
```

### Implementation loop

```bash
python3 scripts/crossai_cli.py loop \
  --feature <name> \
  --implementer claude \
  --reviewer codex \
  --passes 3 \
  --implementer-session-policy auto \
  --reviewer-session-policy fresh
```

---

## Current limitations

- native debate history compaction is automatic rather than exposed as a user-facing control
- the wrapper has been syntax-checked and CLI-checked, but you should still validate it on a real feature flow in your environment

---

## Related docs

- [The Phases](phases.md)
- [Configuring principles.md](principles.md)
- [VS Code Integration](vscode-integration.md)
- [Manual Installation](manual-install.md)
