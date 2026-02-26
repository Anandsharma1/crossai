# CrossAI

> Debate before you build. Run two AIs against each other until they agree on a plan — then implement it.

CrossAI orchestrates a structured debate between **Claude Code** and **Codex CLI** across
four phases — ideation, planning, implementation, and cross-review. Each AI independently
forms a position, critiques the other's work, and revises its own. By the time you write
code, two separate intelligence systems have stress-tested the design.

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
| **Ideation** | Agreed direction: architecture, v1 scope, build sequence |
| **Plan** | Full technical design: data model, API, security, work plan, tests |
| **Implement** | Two independent implementations in separate git worktrees |
| **Review** | Each AI reviews the other's code against the agreed plan |

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
| Running the tool | `python cross_ai/orchestrate.py` | `python ~/.crossai/orchestrate.py` or `python .crossai/orchestrate.py` (via symlink) |
| Team setup | Everyone gets it on `git pull` | Each developer installs separately |
| Updating CrossAI | Re-run `./install.sh` per project | Update once, all projects benefit |
| Multiple projects | Duplicates files in each repo | Single copy, shared across all |

**Start with repo-level** if you're using CrossAI on a specific project — artifacts land where you expect them and the team gets it for free. Switch to user-level if you find yourself installing it across many repos frequently.

Prefer doing it by hand? See [Manual Installation](docs/manual-install.md).

---

## Adding CrossAI to a new project (user-level install already done)

**1. Create and open the project**

```bash
mkdir ~/projects/my-new-thing
code ~/projects/my-new-thing
```

**2. Set up the project shortcut (one-time per project)**

From the project root, create the artifact directory and a symlink so you can
run CrossAI with a short path:

```bash
mkdir -p .crossai
ln -s ~/.crossai/orchestrate.py .crossai/orchestrate.py
```

**3. (Optional) Add VS Code task shortcuts**

```bash
mkdir -p .vscode
sed 's|{{ORCHESTRATE_PATH}}|${env:HOME}/.crossai/orchestrate.py|g' \
    ~/.crossai/vscode/tasks.template.json \
    > .vscode/tasks.json
```

This gives you `Ctrl+Shift+P` → **Tasks: Run Task** → `CrossAI: Ideation` etc.
See [VS Code Integration](docs/vscode-integration.md) for details.

From here, follow the usual [Getting started](#getting-started) workflow below.

---

## Getting started

**1. Write your feature prompt**

```bash
cat > prompt.md <<'EOF'
Add JWT-based user authentication to the API.
Users sign up with email + password. Tokens expire after 24 hours.
Refresh tokens are not required for v1.
EOF
```

**2. Run ideation** (3 rounds of debate, ~5 minutes)

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

**3. Run planning** (reads ideation output automatically)

```bash
python .crossai/orchestrate.py --feature user-auth --phase plan
```

**4. Implement** (both agents in parallel git worktrees)

```bash
python .crossai/orchestrate.py --feature user-auth --phase implement --both
```

**5. Cross-review**

```bash
python .crossai/orchestrate.py --feature user-auth --phase review
```

Artifacts land in `.crossai/user-auth/` at the detected project root.

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

Each phase follows a **heading contract** — a strict Markdown structure that makes
the two agents' outputs directly comparable. The orchestrator:

1. Sends both agents the same prompt (with full debate history from previous rounds)
2. Saves each response as a dated artifact with metadata
3. Runs a **scope guard** after Round 0 — analyzes both plans for scope creep,
   asks you to confirm what to exclude, and injects exclusions as constraints
4. On the final round, uses a convergence prompt that pushes for concrete,
   implementable deliverables rather than continued debate

See [The Four Phases](docs/phases.md) for a full technical walkthrough.

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

**`git worktree` errors during implement phase**
Ensure you're running from inside a git repository. CrossAI creates worktrees
relative to the repo root.

**Orchestrator times out**
Default timeout is 300s per agent. Large plans with long history can hit this.
Run with fewer rounds (`--rounds 1`) or from a clean state.

**Debate history truncated unexpectedly**
History auto-summarizes when it exceeds ~80k characters. This is expected behavior.
The summary is injected as context for subsequent rounds.

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
