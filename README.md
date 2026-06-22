# CrossAI

> Debate before you build. Run two AIs against each other until they agree on a plan — then implement it.

CrossAI orchestrates a structured debate between **Claude Code** and **Codex CLI** across
five workflows — generic, ideation, planning, implementation, and cross-review. Each AI independently
forms a position, critiques the other's work, and revises its own. By the time you write
code, two separate intelligence systems have stress-tested the design.

CrossAI now has **two entrypoints**:
- **Legacy orchestrator**: `orchestrate.py` for the original artifact-first workflow
- **Claude-native wrapper**: `scripts/crossai_cli.py` plus project-local `.claude/` commands for native Claude Code usage, native Claude/Codex session reuse, and implementation-review loops

```
$ python ~/.crossai/orchestrate.py --feature user-auth --prompt idea.md --phase ideation

[Round 0] Claude  → grooming idea...
[Round 0] Codex   → grooming idea...
[Round 1] Claude  → critiquing Codex's direction...
[Round 1] Codex   → critiquing Claude's direction...
[Round 2] Claude  → revising direction...
[Round 2] Codex   → revising direction... (FINAL)

✓ Ideation complete → .crossai/user-auth/ideation/ideation_summary.md
```

---

## What you get

| Phase | Output |
|-------|--------|
| **Generic** | Improved responses for any prompt via cross-verification |
| **Ideation** | Agreed direction: architecture, v1 scope, build sequence |
| **Plan** | Full technical design: data model, API, security, work plan, tests |
| **Implement** | Two independent implementations in separate git worktrees |
| **Review** | Each AI reviews the other's code against the agreed plan |

---

## Which entrypoint should I use?

| Entry | Best for | Notes |
|---|---|---|
| `python3 scripts/crossai_cli.py ...` | Day-to-day use going forward | Supports native Claude/Codex session reuse, implementation-review loops, scope-policy control, and Claude-native commands in `.claude/` |
| `python .crossai/orchestrate.py ...` | Backward compatibility and the original flow | Keeps the older artifact-first behavior and original interactive scope guard |

If you are starting fresh on this repo, use **`scripts/crossai_cli.py`**.

For the full Claude-native guide, see [Claude-native workflow](docs/claude-native.md).

---

## Prerequisites

| Tool | Min version | Install |
|------|-------------|---------|
| [Claude Code CLI](https://claude.ai/code) | latest | `npm install -g @anthropic-ai/claude-code` |
| [Codex CLI](https://github.com/openai/codex) | latest | see repo |
| Python | 3.10+ | https://python.org |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | any | https://git-scm.com |

---

## Which models does CrossAI use?

CrossAI does **not** pin a model for either agent. It shells out to the underlying CLIs (`claude` and `codex`) without a `--model` flag, so each agent uses whatever its own CLI is configured to use.

| Agent | How the model is chosen | Where to change it |
|-------|-------------------------|--------------------|
| **Claude** | Inherits the Claude Code CLI default | `~/.claude/settings.json` → `"model"` key (e.g. `"opus"`, `"sonnet"`, or a full model ID) |
| **Codex** | Inherits the Codex CLI default | `~/.codex/config.toml` → `model = "..."` and `model_reasoning_effort = "..."` |

To override for a single run without changing global config:
- **Codex**: edit the `codex exec` invocation in `scripts/crossai_cli.py` (see `run_codex_session`) to pass `-c model="gpt-5.4"` or similar.
- **Claude**: add `--model <id>` to the `claude -p` invocation in `run_claude_session` in the same file.

If you want reproducible cross-machine behavior, pin the model in each CLI's config rather than relying on whatever default happens to be active.

### Pointing at a specific Codex instance (home or command)

You can swap the Codex binary, its top-level flags, or its config directory per run — no source edits required. Both `scripts/crossai_cli.py` and the legacy `orchestrate.py` honor these:

| Knob | How to set it | Effect |
|------|---------------|--------|
| **Codex command** | `CROSSAI_CODEX_CMD` env var, e.g. `CROSSAI_CODEX_CMD='codex --yolo'` | Overrides the codex binary and any top-level flags (parsed with shell quoting). |
| **Codex home** | `CODEX_HOME` env var, e.g. `CODEX_HOME=~/.codex-work` | Points Codex at an alternate config dir; the codex subprocess inherits it natively. |

```bash
CROSSAI_CODEX_CMD='codex --yolo' CODEX_HOME=~/.codex-work \
  python3 scripts/crossai_cli.py generic --feature my-feat --prompt task.md
```

From the Claude-native slash commands, pass the same knobs as flags — `--codex-cmd "codex --yolo"` and `--codex-home ~/.codex-work` — on `/crossai-generic`, `/crossai-plan`, `/crossai-implement`, and `/crossai-loop`. The command strips them from the passthrough args and sets the matching env vars on the Python call. `--codex-cmd` takes precedence over `--codex-home` for the binary itself; both may be combined.

---

## Install

```bash
git clone https://github.com/Anandsharma1/crossai.git
cd crossai
./install.sh
```

The installer checks prerequisites, asks whether you want a **user-level** install
(`~/.crossai/` — shared across all projects) or a **repo-level** install
(`./cross_ai/` — checked into one project), then copies everything into place.

### Which mode should I choose?

| | Repo-level | User-level |
|---|---|---|
| Debate artifacts (`.crossai/`) | Land in the project automatically | Auto-detected — land at the nearest project root (`.git/`, `.vscode/`, etc.) |
| Running the tool | `python3 cross_ai/scripts/crossai_cli.py` | `python3 ~/.crossai/scripts/crossai_cli.py` or `python3 .crossai/crossai_cli.py` (via symlink) |
| Team setup | Everyone gets it on `git pull` | Each developer installs separately |
| Updating CrossAI | Re-run `./install.sh` per project | Update once, all projects benefit |
| Multiple projects | Duplicates files in each repo | Single copy, shared across all — see [Adding CrossAI to a new project](#adding-crossai-to-a-new-project-user-level-install-already-done) |

**Start with repo-level** if you're using CrossAI on a specific project — artifacts land where you expect them and the team gets it for free. Switch to user-level if you find yourself installing it across many repos frequently.

Prefer doing it by hand? See [Manual Installation](docs/manual-install.md).

---

## Adding CrossAI to a new project (user-level install already done)

```bash
./install.sh --add-project ~/projects/my-new-thing
```

This single command does everything needed:
- Creates `.crossai/` in the project and symlinks `orchestrate.py` back to `~/.crossai/`
- Creates `.crossai/crossai_cli.py` as a shortcut to the installed wrapper
- Creates `.crossai/crossai_hook.py` as a shortcut to the installed hook helper
- Symlinks `.crossai/README.md` to the CrossAI quickstart so docs live with the project
- Merges CrossAI hook entries into `.claude/settings.json`
- Injects VS Code task shortcuts (`.vscode/tasks.json`)
- Registers the project so `--list-projects` and uninstall can find it later

**Registering several projects** — run the flag once per project. It's safe to
re-run on a project you've already added; existing symlinks are refreshed and
the registry is deduplicated.

```bash
./install.sh --add-project ~/projects/project-a
./install.sh --add-project ~/projects/project-b
./install.sh --add-project ~/work/service-c
```

To see all registered projects:

```bash
./install.sh --list-projects
```

**Removing a project** — unregisters it and cleans up everything CrossAI added,
without touching your debate artifacts:

```bash
./install.sh --remove-project ~/projects/project-a
```

This removes the symlinks (`.crossai/orchestrate.py`, `crossai_cli.py`,
`crossai_hook.py`, `README.md`), strips CrossAI hook entries from `.claude/settings.json`,
and removes `CrossAI:` tasks from `.vscode/tasks.json`. Feature artifacts under
`.crossai/<feature>/` are preserved — delete that directory manually if you
want a full wipe.

**Manual alternative** — if you prefer doing it by hand or don't have the CrossAI
repo cloned locally:

```bash
cd ~/projects/my-new-thing
mkdir -p .crossai
ln -s ~/.crossai/orchestrate.py .crossai/orchestrate.py
ln -s ~/.crossai/scripts/crossai_cli.py .crossai/crossai_cli.py
ln -s ~/.crossai/scripts/crossai_hook.py .crossai/crossai_hook.py
```

From here, follow the usual [Getting started](#getting-started) workflow below.

---

## Quick start (recommended wrapper)

These examples use the newer Claude-native wrapper.

**1. Write your feature prompt**

```bash
cat > prompt.md <<'EOF'
Add JWT-based user authentication to the API.
Users sign up with email + password. Tokens expire after 24 hours.
Refresh tokens are not required for v1.
EOF
```

**2. Run ideation + planning with native debate sessions**

```bash
python3 scripts/crossai_cli.py plan \
  --feature user-auth \
  --prompt prompt.md \
  --session-policy fresh \
  --scope-policy adjudicate
```

This produces:
- `.crossai/user-auth/ideation/...`
- `.crossai/user-auth/plan/...`
- `.crossai/user-auth/sessions.json`
- `.crossai/user-auth/run_state.json`
- scope artifacts such as `scope_candidates.md` and `scope_decisions.md`

**3. Run implementation in a dedicated worktree**

```bash
python3 scripts/crossai_cli.py implement \
  --feature user-auth \
  --implementer claude \
  --session-policy auto
```

**4. Run the implementation-review-fix loop**

```bash
python3 scripts/crossai_cli.py loop \
  --feature user-auth \
  --implementer claude \
  --reviewer codex \
  --passes 3 \
  --implementer-session-policy auto \
  --reviewer-session-policy fresh
```

**5. Inspect current state**

```bash
python3 scripts/crossai_cli.py status --feature user-auth
```

---

## Claude Code usage

When this repo is opened in Claude Code, the project-local commands under `.claude/commands/`
are available:

- `/crossai-generic`
- `/crossai-plan`
- `/crossai-implement`
- `/crossai-loop`
- `/crossai-status`

The workflow guidance lives in `.claude/skills/crossai-conductor/`, and minimal hook wiring
is configured in `.claude/settings.json`. Installed projects use `.crossai/crossai_hook.py`
as the stable hook target, so the hook path works for repo-level and user-level installs.

Examples inside Claude Code:

```text
/crossai-generic table-descriptions prompt.md --session-policy fresh
/crossai-plan user-auth prompt.md --session-policy fresh --scope-policy adjudicate
/crossai-implement user-auth --implementer claude --session-policy auto
/crossai-loop user-auth --implementer claude --reviewer codex --passes 3
```

For a full operational guide, see [Claude-native workflow](docs/claude-native.md).

---

## Getting started (legacy orchestrator)

**1. Write your feature prompt**

```bash
cat > prompt.md <<'EOF'
Add JWT-based user authentication to the API.
Users sign up with email + password. Tokens expire after 24 hours.
Refresh tokens are not required for v1.
EOF
```

**2. Optional: run generic mode for any task** (for example, table descriptions)

```bash
python .crossai/orchestrate.py --feature table-descriptions --prompt prompt.md --phase generic
```

**3. Run ideation** (3 rounds of debate, ~5 minutes)

```bash
# Repo-level install
python cross_ai/orchestrate.py --feature user-auth --prompt prompt.md --phase ideation

# User-level install (full path)
python ~/.crossai/orchestrate.py --feature user-auth --prompt prompt.md --phase ideation

# User-level install (via project symlink, if created during install)
python .crossai/orchestrate.py --feature user-auth --prompt prompt.md --phase ideation
```

CrossAI automatically detects the project root by looking for `.git/`, `.vscode/`,
`pyproject.toml`, `package.json`, and similar markers — artifacts always land in
`.crossai/<feature>/` at the detected root. Use `--project-dir /path` to override.

**4. Run planning** (reads ideation output automatically)

```bash
python .crossai/orchestrate.py --feature user-auth --phase plan
```

**5. Implement** (both agents in parallel git worktrees)

```bash
python .crossai/orchestrate.py --feature user-auth --phase implement --both
```

**6. Cross-review**

```bash
python .crossai/orchestrate.py --feature user-auth --phase review
```

Artifacts land in `.crossai/user-auth/` at the detected project root.

---

## Wrapper CLI reference

`scripts/crossai_cli.py` supports:

| Command | Purpose |
|---|---|
| `generic` | Run standalone cross-verification for any task prompt |
| `plan` | Run ideation + plan using native Claude/Codex debate sessions |
| `implement` | Run implementation for one agent in a dedicated worktree |
| `review` | Run a single review pass against an implementation |
| `loop` | Run implement -> review -> fix iterations |
| `status` | Show current CrossAI feature state |

### `generic`

```bash
python3 scripts/crossai_cli.py generic --feature <name> --prompt <file> [options]
```

Options:
- `--rounds <N>`: debate rounds, default `3`
- `--session-policy auto|fresh|resume`
- `--read-codebase`
- `--project-dir <dir>`

### `plan`

```bash
python3 scripts/crossai_cli.py plan --feature <name> --prompt <file> [options]
```

Options:
- `--rounds <N>`: debate rounds, default `3`
- `--session-policy auto|fresh|resume`: whether to reuse saved native debate sessions
- `--scope-policy adjudicate|interactive|off`: how round-0 scope drift is handled
- `--read-codebase`: allow agent codebase inspection during debate
- `--no-scope-check`: shortcut for `--scope-policy off`
- `--project-dir <dir>`: override project-root detection

### `implement`

```bash
python3 scripts/crossai_cli.py implement --feature <name> [options]
```

Options:
- `--implementer claude|codex`
- `--session-policy auto|fresh|resume`
- `--project-dir <dir>`

### `review`

```bash
python3 scripts/crossai_cli.py review --feature <name> [options]
```

Options:
- `--reviewer claude|codex`
- `--target claude|codex`
- `--pass-number <N>`
- `--session-policy auto|fresh|resume`
- `--display-mode inline|tmux`
- `--project-dir <dir>`

### `loop`

```bash
python3 scripts/crossai_cli.py loop --feature <name> [options]
```

Options:
- `--implementer claude|codex`
- `--reviewer claude|codex`
- `--passes <N>`
- `--implementer-session-policy auto|fresh|resume`
- `--reviewer-session-policy auto|fresh|resume`
- `--display-mode inline|tmux`
- `--project-dir <dir>`

### `status`

```bash
python3 scripts/crossai_cli.py status --feature <name>
```

Outputs the current feature state as JSON, including worktrees, saved sessions, and latest artifacts.

---

## Session and scope policies

### Session policy

Used by `plan` and `implement`, and separately for implementer/reviewer in `loop`.

- `auto`: reuse a saved native session if one exists; otherwise start fresh
- `fresh`: ignore saved native sessions and start a new one
- `resume`: require an existing saved native session and continue it

Use `fresh` when you want a clean re-run, and `resume` when you explicitly want continuity.

### Scope policy

Used by `plan`.

- `adjudicate`: default; Claude and Codex classify possible scope drift after round 0, then CrossAI merges the result into `scope_decisions.md`
- `interactive`: present candidate drift items and let you exclude them manually
- `off`: disable scope drift handling

The adjudication flow writes:
- `.crossai/<feature>/<phase>/scope_candidates.md`
- `.crossai/<feature>/<phase>/scope_adjudication.claude.md`
- `.crossai/<feature>/<phase>/scope_adjudication.codex.md`
- `.crossai/<feature>/<phase>/scope_decisions.md`

The final `scope_decisions.md` is then injected into subsequent debate rounds as constraints.

---

## CLI options reference

`orchestrate.py` supports the following flags:

| Flag | Required | Applies to | Default | Notes |
|---|---|---|---|---|
| `--feature <name>` | Yes | all phases | n/a | Feature slug used for artifact paths (`.crossai/<feature>/...`). |
| `--phase <generic\|ideation\|plan\|implement\|review>` | No | all phases | `ideation` | Main workflow selector. |
| `--prompt <file>` | Sometimes | `generic`, `ideation`, optional in `plan` | n/a | Required for `generic` + `ideation`; `plan` can auto-chain from ideation outputs. |
| `--rounds <int>` | No | debate phases (`generic`, `ideation`, `plan`) | `3` | Number of rounds. `1` means groom only (no critique/revise rounds). |
| `--no-scope-check` | No | `ideation`, `plan` | off | Skips the interactive scope guard after round 0. (`generic` already has scope check disabled.) |
| `--read-codebase` | No | debate phases (`generic`, `ideation`, `plan`) | off | Enables Claude tools in debate (`--max-turns 10`) so it can inspect code/files. |
| `--project-dir <dir>` | No | all phases | auto-detect | Overrides project-root detection for artifact placement. |
| `--agent <claude\|codex>` | Conditional | `implement` | n/a | Run implementation for one agent only. |
| `--both` | Conditional | `implement` | off | Run implementations for both Claude and Codex in separate worktrees. |

`implement` requires either `--agent` or `--both`.

Examples:

```bash
# Debate with codebase reading enabled
python .crossai/orchestrate.py --feature user-auth --prompt prompt.md --phase ideation --read-codebase

# Skip scope confirmation prompts
python .crossai/orchestrate.py --feature user-auth --phase plan --no-scope-check

# Put artifacts under a specific repo root
python .crossai/orchestrate.py --feature user-auth --prompt prompt.md --phase generic --project-dir ~/projects/my-repo

# Fast single-round idea pass
python .crossai/orchestrate.py --feature user-auth --prompt prompt.md --phase ideation --rounds 1
```

---

## Configuration

CrossAI injects a `principles.md` file into every prompt, letting you encode
team conventions and quality bars that both AIs must respect.

```bash
# Repo-level (lives alongside cross_ai/)
cp cross_ai/principles.example.md cross_ai/principles.md
$EDITOR cross_ai/principles.md

# User-level, project-scoped (lives in .crossai/ — auto-detected at project root)
cp ~/.crossai/principles.example.md .crossai/principles.md
$EDITOR .crossai/principles.md

# User-level, shared across all projects
cp ~/.crossai/principles.example.md ~/.crossai/principles.md
$EDITOR ~/.crossai/principles.md
```

CrossAI checks for principles in order: `.crossai/<feature>/principles.md` (feature override) →
`.crossai/principles.md` (project-wide) → `~/.crossai/principles.md` (user-level global).

See [Configuring principles.md](docs/principles.md) for details.

---

## VS Code integration

If you have VS Code, the installer adds six task shortcuts
(`Ctrl+Shift+P` → **Tasks: Run Task**). See [VS Code Integration](docs/vscode-integration.md).

---

## Updating

```bash
cd /path/to/crossai
git pull
./install.sh      # detects existing install, shows version diff, updates in place
```

Your `principles.md` is never overwritten.

---

## Uninstalling

```bash
cd /path/to/crossai
./uninstall.sh
```

Runtime artifacts in your projects' `.crossai/` directories are left untouched.

---

## How it works

Each debate step follows a **prompt contract** so the two agents' outputs stay
directly comparable while still allowing task-specific flexibility.

### Legacy orchestrator

The original orchestrator:

1. Sends both agents the same prompt (with full debate history from previous rounds)
2. Saves each response as a dated artifact with metadata
3. Runs a **scope guard** after Round 0 — analyzes both plans for scope creep,
   asks you to confirm what to exclude, and injects exclusions as constraints
4. On the final round, uses a convergence prompt that pushes for concrete,
   implementable deliverables rather than continued debate

### Claude-native wrapper

The newer wrapper:

1. Starts or resumes native Claude/Codex sessions based on session policy
2. Writes artifacts for every debate, implementation, and review step
3. Persists feature state in:
   - `.crossai/<feature>/sessions.json`
   - `.crossai/<feature>/run_state.json`
4. For planning, optionally resolves scope drift using:
   - agent adjudication (`adjudicate`)
   - manual exclusions (`interactive`)
   - no scope handling (`off`)
5. For implementation loops, keeps the implementer session sticky while allowing reviewer sessions to be fresh, resumed, or auto-reused depending on flags

### Artifact model

Common artifact families now include:

- debate artifacts under `.crossai/<feature>/ideation/` and `.crossai/<feature>/plan/`
- implementation logs under `.crossai/<feature>/implementation/`
- review artifacts under `.crossai/<feature>/reviews/`
- scope artifacts under `.crossai/<feature>/<phase>/scope_*.md`
- state files:
  - `.crossai/<feature>/sessions.json`
  - `.crossai/<feature>/run_state.json`

See [The Phases](docs/phases.md) for a full technical walkthrough.
For the newer wrapper-centric model, see [Claude-native workflow](docs/claude-native.md).

---

## Project context and information isolation

CrossAI instructs agents not to browse your source code by default (see `--read-codebase`
if you want to enable that explicitly). However, **Claude Code reads `CLAUDE.md` automatically
from the working directory**. If you run CrossAI from inside an existing project, its
`CLAUDE.md` will be loaded into Claude's system prompt and can influence the debate.

**This is usually fine** — your coding conventions and architecture principles are often
useful context. But if you want a completely clean slate (new idea, no codebase bias):

**Option 1 — Run from an empty directory**

```bash
mkdir /tmp/my-idea && cd /tmp/my-idea
python ~/.crossai/orchestrate.py --feature my-feature --prompt /path/to/prompt.md --phase ideation
```

Artifacts still land at the auto-detected project root (wherever your prompt lives, or
specify with `--project-dir`).

**Option 2 — Open VS Code or Cursor with just the prompt file**

Open an empty workspace (no project folder) before running CrossAI tasks. Without a
`CLAUDE.md` in the working directory, no project context is loaded.

---

## Troubleshooting

**`claude: command not found`**
Install Claude Code CLI: https://claude.ai/code

**`codex: command not found`**
Install Codex CLI: https://github.com/openai/codex

**`python3: version too old`**
CrossAI requires Python 3.10+. Install via your distro or https://python.org.

**`python: command not found`**
Use `python3` for the new wrapper commands. The repository examples for `scripts/crossai_cli.py`
assume `python3`.

**`git worktree` errors during implement phase**
Ensure you're running from inside a git repository. CrossAI creates worktrees
relative to the repo root.

**Orchestrator times out**
Default timeout is 300s per agent. Large plans with long history can hit this.
Run with fewer rounds (`--rounds 1`) or from a clean state.

**`Error: Reached max turns (1)` in Claude output**
In debate phases, this usually means your prompt asked Claude to read files or inspect code,
but tools were disabled (default mode is `--tools "" --max-turns 1` for Claude debate calls).

Options:
- Enable codebase access for debate: add `--read-codebase`
- Keep the prompt self-contained (don't require browsing local files)
- If you want a clean no-context run, start from an empty directory to avoid extra
  environment instructions influencing tool use

**`Error: Reached max turns (N)` where `N > 1`**
This usually happens when tools are enabled and Claude spends turns exploring files
instead of producing the final response.

If you're using `--read-codebase`, options:
- Increase the max-turns limit in `run_claude()` (the `allow_tools=True` branch
  defaults to 10 — raise it if your codebase is large)
- Narrow your prompt so Claude doesn't need to read as many files
- Increase the timeout (`CLAUDE_TIMEOUT` in `orchestrate.py`, default 300s)

**Debate history truncated unexpectedly**
History auto-summarizes when it exceeds ~80k characters. This is expected behavior.
The summary is injected as context for subsequent rounds.

**Why did debate continue without asking me about scope?**
If you are using `scripts/crossai_cli.py plan`, scope handling depends on `--scope-policy`:
- `adjudicate`: agents decide and document drift
- `interactive`: you are prompted
- `off`: no scope handling

**Where are native session ids stored?**
In `.crossai/<feature>/sessions.json`. Claude entries store `session_id`; Codex entries store `thread_id`.

---

## Contributing

PRs welcome. When changing `install.sh`:
- Run `bash -n install.sh` to verify syntax
- Test user-level install in a temp home directory
- Test repo-level install in a temp git repo
- Test the update path (run installer twice, different versions)

When changing documentation:
- Verify all links resolve (relative paths only)
- Check that `docs/manual-install.md` stays in sync with `install.sh` logic
