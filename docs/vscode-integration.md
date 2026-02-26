# VS Code Integration

CrossAI provides six VS Code task shortcuts for running each phase
without memorizing command-line arguments.

## Setup

The installer handles this automatically. To set it up manually, see
[Manual Installation](manual-install.md).

## Available Tasks

Open the Command Palette (`Ctrl+Shift+P`) → **Tasks: Run Task**:

| Task | Phase | Prompts for |
|------|-------|-------------|
| CrossAI: Ideation | ideation | Feature name, prompt file, round count |
| CrossAI: Plan | plan | Feature name, round count |
| CrossAI: Implement (Claude) | implement | Feature name |
| CrossAI: Implement (Codex) | implement | Feature name |
| CrossAI: Implement (both) | implement | Feature name |
| CrossAI: Review | review | Feature name |

## Inputs

All tasks share the same inputs (VS Code remembers recent values):

- **Feature name** — directory name used under `.crossai/` (e.g. `user-auth`)
- **Prompt file** — path to your initial prompt file (e.g. `prompt.md`)
- **Round count** — number of debate rounds (default: 3)

## Recommended keybindings

Add to your `keybindings.json` (`Ctrl+Shift+P` → **Open Keyboard Shortcuts (JSON)**):

```json
[
  { "key": "ctrl+shift+alt+i", "command": "workbench.action.tasks.runTask", "args": "CrossAI: Ideation" },
  { "key": "ctrl+shift+alt+p", "command": "workbench.action.tasks.runTask", "args": "CrossAI: Plan" },
  { "key": "ctrl+shift+alt+b", "command": "workbench.action.tasks.runTask", "args": "CrossAI: Implement (both)" },
  { "key": "ctrl+shift+alt+r", "command": "workbench.action.tasks.runTask", "args": "CrossAI: Review" }
]
```
