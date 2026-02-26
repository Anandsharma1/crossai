# Manual Installation

This guide covers every file that needs to be placed, with exact paths,
for both install modes. No script required.

## Prerequisites

Ensure all of the following are installed and on your PATH:

| Tool | Min version | Install |
|------|-------------|---------|
| Claude Code CLI | latest | https://claude.ai/code |
| Codex CLI | latest | https://github.com/openai/codex |
| Python | 3.10+ | https://python.org |
| uv | latest | https://docs.astral.sh/uv/ |
| git | any | https://git-scm.com |

Verify:

```bash
claude --version
codex --version
python3 --version   # must be ≥3.10
uv --version
git --version
```

## Clone the CrossAI repo

```bash
git clone https://github.com/Anandsharma1/crossai.git
cd crossai
```

---

## Option A: User-level install

Use this when you want CrossAI available across all your projects.

### 1. Create directories

```bash
mkdir -p ~/.crossai/prompts
mkdir -p ~/.claude/skills/crossai-conducting
mkdir -p ~/.codex/skills/crossai-challenging
```

### 2. Copy the tool

```bash
cp orchestrate.py         ~/.crossai/orchestrate.py
chmod +x                  ~/.crossai/orchestrate.py
cp -r prompts/.           ~/.crossai/prompts/
cp principles.example.md  ~/.crossai/principles.example.md
```

### 3. Copy the skills

```bash
cp skills/claude/SKILL.md  ~/.claude/skills/crossai-conducting/SKILL.md
cp skills/codex/SKILL.md   ~/.codex/skills/crossai-challenging/SKILL.md
```

### 4. Record the installed version

```bash
cat VERSION > ~/.crossai/.version
```

### 5. (Optional) Inject VS Code tasks

For each project where you want task shortcuts:

```bash
cd /your/project
mkdir -p .vscode
sed 's|{{ORCHESTRATE_PATH}}|${env:HOME}/.crossai/orchestrate.py|g' \
    /path/to/crossai/vscode/tasks.template.json \
    > .vscode/tasks.json
```

If `.vscode/tasks.json` already exists, manually copy the `tasks` and `inputs`
arrays from `vscode/tasks.template.json` into it, replacing `{{ORCHESTRATE_PATH}}`
with `${env:HOME}/.crossai/orchestrate.py`.

---

## Option B: Repo-level install

Use this when you want CrossAI checked into a specific project.
Run all commands from your **project root**.

### 1. Create directories

```bash
mkdir -p cross_ai/prompts
mkdir -p .claude/skills/crossai-conducting
mkdir -p .codex/skills/crossai-challenging
mkdir -p .vscode
```

### 2. Copy the tool

```bash
cp /path/to/crossai/orchestrate.py         cross_ai/orchestrate.py
chmod +x                                   cross_ai/orchestrate.py
cp -r /path/to/crossai/prompts/.           cross_ai/prompts/
cp /path/to/crossai/principles.example.md  cross_ai/principles.example.md
```

### 3. Copy the skills

```bash
cp /path/to/crossai/skills/claude/SKILL.md  .claude/skills/crossai-conducting/SKILL.md
cp /path/to/crossai/skills/codex/SKILL.md   .codex/skills/crossai-challenging/SKILL.md
```

### 4. Write the VS Code tasks

```bash
sed 's|{{ORCHESTRATE_PATH}}|cross_ai/orchestrate.py|g' \
    /path/to/crossai/vscode/tasks.template.json \
    > .vscode/tasks.json
```

### 5. Record the installed version

```bash
cat /path/to/crossai/VERSION > cross_ai/.version
```

### 6. Add to git

```bash
git add cross_ai/ .claude/ .codex/ .vscode/tasks.json
git commit -m "chore: add CrossAI"
```

### 7. Add runtime artifacts to .gitignore

```bash
echo ".crossai/" >> .gitignore
```

---

## Updating

### User-level

```bash
cd /path/to/crossai
git pull
cp orchestrate.py         ~/.crossai/orchestrate.py
cp -r prompts/.           ~/.crossai/prompts/
cp principles.example.md  ~/.crossai/principles.example.md
cp skills/claude/SKILL.md ~/.claude/skills/crossai-conducting/SKILL.md
cp skills/codex/SKILL.md  ~/.codex/skills/crossai-challenging/SKILL.md
cat VERSION > ~/.crossai/.version
```

> Your `~/.crossai/principles.md` is **never overwritten** — only `principles.example.md` is updated.

### Repo-level

```bash
cd /path/to/crossai
git pull
# Repeat the copy commands from Option B above, then commit.
```

---

## Uninstalling

### User-level

```bash
rm -rf ~/.crossai
rm -rf ~/.claude/skills/crossai-conducting
rm -rf ~/.codex/skills/crossai-challenging
```

Runtime artifacts in your projects' `.crossai/` directories are not touched.
Delete them manually if you no longer need them.

### Repo-level

```bash
rm -rf cross_ai/
rm -rf .claude/skills/crossai-conducting
rm -rf .codex/skills/crossai-challenging
# Edit .vscode/tasks.json to remove CrossAI tasks if desired.
```
