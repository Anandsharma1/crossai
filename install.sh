#!/usr/bin/env bash
# CrossAI Installer / Updater
# Usage: ./install.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION="$(cat "$SCRIPT_DIR/VERSION")"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# ---------------------------------------------------------------------------
# Prerequisites
# ---------------------------------------------------------------------------

check_prerequisites() {
    local all_ok=true
    echo ""
    echo -e "${BOLD}Checking prerequisites...${NC}"
    echo ""

    _check_cmd() {
        local cmd="$1" label="$2" install_url="$3"
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver="$("$cmd" --version 2>/dev/null | head -1 || echo "unknown")"
            echo -e "  ${GREEN}✓${NC}  $label   $ver"
        else
            echo -e "  ${RED}✗${NC}  $label   not found  →  $install_url"
            all_ok=false
        fi
    }

    _check_cmd claude  "claude " "https://claude.ai/code"
    _check_cmd codex   "codex  " "https://github.com/openai/codex"
    _check_cmd uv      "uv     " "https://docs.astral.sh/uv/"
    _check_cmd git     "git    " "https://git-scm.com"

    # python3 needs version check
    if command -v python3 &>/dev/null; then
        local py_ver major minor
        py_ver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
        major="$(echo "$py_ver" | cut -d. -f1)"
        minor="$(echo "$py_ver" | cut -d. -f2)"
        if [[ "$major" -gt 3 ]] || [[ "$major" -eq 3 && "$minor" -ge 10 ]]; then
            echo -e "  ${GREEN}✓${NC}  python3  $py_ver"
        else
            echo -e "  ${RED}✗${NC}  python3  $py_ver  (need ≥3.10)  →  https://python.org"
            all_ok=false
        fi
    else
        echo -e "  ${RED}✗${NC}  python3  not found  →  https://python.org"
        all_ok=false
    fi

    echo ""
    if [[ "$all_ok" != "true" ]]; then
        echo -e "${RED}Some prerequisites are missing. Install them and re-run this script.${NC}"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

detect_existing_install() {
    if [[ -f "$HOME/.crossai/.version" ]]; then
        echo "user"
    elif [[ -f "$(pwd)/cross_ai/.version" ]]; then
        echo "repo"
    else
        echo "none"
    fi
}

confirm_update() {
    local dest="$1"
    local installed_version
    installed_version="$(cat "$dest/.version" 2>/dev/null || echo "unknown")"
    if [[ "$installed_version" == "$VERSION" ]]; then
        echo -e "${YELLOW}CrossAI $VERSION is already installed.${NC}"
        read -rp "Reinstall anyway? [y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] || exit 0
    else
        echo -e "Updating CrossAI: ${YELLOW}$installed_version${NC} → ${GREEN}$VERSION${NC}"
        read -rp "Continue? [y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] || exit 0
    fi
}

copy_core_files() {
    local dest="$1"
    mkdir -p "$dest/prompts" "$dest/scripts"
    cp "$SCRIPT_DIR/orchestrate.py"        "$dest/orchestrate.py"
    chmod +x "$dest/orchestrate.py"
    cp -r "$SCRIPT_DIR/prompts/."          "$dest/prompts/"
    cp -r "$SCRIPT_DIR/scripts/."          "$dest/scripts/"
    chmod +x "$dest/scripts/"*.py
    cp "$SCRIPT_DIR/principles.example.md" "$dest/principles.example.md"
    cp "$SCRIPT_DIR/README.md"             "$dest/README.md"
    echo "$VERSION"                        > "$dest/.version"
}

copy_skill_files() {
    local claude_dest="$1" codex_dest="$2"
    mkdir -p "$claude_dest" "$codex_dest"
    cp "$SCRIPT_DIR/.claude/skills/crossai-conductor/SKILL.md" "$claude_dest/SKILL.md"
    cp "$SCRIPT_DIR/skills/codex/SKILL.md"  "$codex_dest/SKILL.md"
}

copy_command_files() {
    # Install the /crossai-* slash commands for Claude Code.
    local commands_dest="$1"
    mkdir -p "$commands_dest"
    local src="$SCRIPT_DIR/.claude/commands"
    local count=0
    for f in "$src"/crossai-*.md; do
        [[ -f "$f" ]] || continue
        cp "$f" "$commands_dest/"
        count=$((count + 1))
    done
    echo -e "  ${GREEN}✓${NC}  Installed $count slash commands → $commands_dest"
}

# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

# Print one project path per line from .meta.json; empty output if no meta.
_get_meta_projects() {
    local meta_file="$1"
    python3 - <<PYEOF
import json
try:
    with open('$meta_file') as f:
        data = json.load(f)
    for p in data.get('vscode_projects', []):
        print(p)
except Exception:
    pass
PYEOF
}

# Create or update the .meta.json file at the install root.
_write_meta() {
    local meta_file="$1" install_type="$2"
    python3 - <<PYEOF
import json, datetime

meta_file = '$meta_file'
install_type = '$install_type'
version = '$VERSION'
now = datetime.datetime.now().isoformat(timespec='seconds')

try:
    with open(meta_file) as f:
        data = json.load(f)
    data['version'] = version
    data['updated_at'] = now
except (FileNotFoundError, json.JSONDecodeError):
    data = {
        'version': version,
        'install_type': install_type,
        'installed_at': now,
        'updated_at': now,
        'vscode_projects': []
    }

with open(meta_file, 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')
PYEOF
}

# Append a project path to vscode_projects in .meta.json (idempotent).
_record_vscode_project() {
    local meta_file="$1" project_path="$2"
    python3 - <<PYEOF
import json

meta_file = '$meta_file'
project_path = '$project_path'

try:
    with open(meta_file) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {'vscode_projects': []}

projects = data.setdefault('vscode_projects', [])
if project_path not in projects:
    projects.append(project_path)
    with open(meta_file, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
PYEOF
}

# ---------------------------------------------------------------------------
# VS Code tasks
# ---------------------------------------------------------------------------

generate_tasks_json() {
    local dest_file="$1" orchestrate_path="$2"
    mkdir -p "$(dirname "$dest_file")"
    sed "s|{{ORCHESTRATE_PATH}}|$orchestrate_path|g" \
        "$SCRIPT_DIR/vscode/tasks.template.json" > "$dest_file"
    echo -e "  ${GREEN}✓${NC}  VS Code tasks written to $dest_file"
}

merge_tasks_json() {
    # Adds CrossAI tasks to an existing tasks.json without duplicating them.
    # Uses python3 (already a verified prerequisite) for JSON parsing.
    local dest_file="$1" orchestrate_path="$2"
    python3 - <<PYEOF
import json

with open('$dest_file') as f:
    existing = json.load(f)

with open('$SCRIPT_DIR/vscode/tasks.template.json') as f:
    template = json.load(f)

existing_labels = {t.get('label') for t in existing.get('tasks', [])}
to_add = []
for t in template.get('tasks', []):
    if t.get('label') not in existing_labels:
        t_str = json.dumps(t).replace('{{ORCHESTRATE_PATH}}', '$orchestrate_path')
        to_add.append(json.loads(t_str))

existing.setdefault('tasks', []).extend(to_add)

existing_input_ids = {i.get('id') for i in existing.get('inputs', [])}
for inp in template.get('inputs', []):
    if inp.get('id') not in existing_input_ids:
        existing.setdefault('inputs', []).append(inp)

with open('$dest_file', 'w') as f:
    json.dump(existing, f, indent=2)
    f.write('\n')
PYEOF
    echo -e "  ${GREEN}✓${NC}  CrossAI tasks merged into $dest_file"
}

handle_vscode_tasks() {
    local dest_file="$1" orchestrate_path="$2"
    if [[ -f "$dest_file" ]]; then
        merge_tasks_json "$dest_file" "$orchestrate_path"
    else
        generate_tasks_json "$dest_file" "$orchestrate_path"
    fi
}

merge_claude_settings() {
    local project_root="$1" hook_path="$2"
    local settings_file="$project_root/.claude/settings.json"
    mkdir -p "$(dirname "$settings_file")"
    python3 - <<PYEOF
import json
from pathlib import Path

settings_file = Path(r'''$settings_file''')
hook_path = r'''$hook_path'''

try:
    data = json.loads(settings_file.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError("settings root must be an object")
except Exception:
    data = {}

hooks = data.setdefault("hooks", {})
entries = {
    "SessionStart": {
        "matcher": "",
        "hooks": [{
            "type": "command",
            "command": f"python3 {hook_path} session-start",
            "timeout": 10,
        }],
    },
    "Stop": {
        "matcher": "",
        "hooks": [{
            "type": "command",
            "command": f"python3 {hook_path} stop-check",
            "timeout": 10,
        }],
    },
}

def _is_crossai_command(cmd):
    return "crossai_hook.py" in str(cmd)

for event, entry in entries.items():
    existing = hooks.get(event, [])
    if not isinstance(existing, list):
        existing = []
    filtered = []
    for item in existing:
        if not isinstance(item, dict):
            filtered.append(item)
            continue
        # Legacy broken shape: direct command dict at the top level — drop ours.
        if "command" in item and "hooks" not in item:
            if _is_crossai_command(item.get("command", "")):
                continue
            filtered.append(item)
            continue
        # Correct shape: matcher + hooks[]. Strip our command from the inner list.
        inner = item.get("hooks")
        if isinstance(inner, list):
            inner_filtered = [
                h for h in inner
                if not (isinstance(h, dict) and _is_crossai_command(h.get("command", "")))
            ]
            if inner_filtered:
                item = {**item, "hooks": inner_filtered}
                filtered.append(item)
            # else: drop the whole matcher group (it was ours-only)
        else:
            filtered.append(item)
    filtered.append(entry)
    hooks[event] = filtered

settings_file.write_text(json.dumps(data, indent=2) + "\n", encoding='utf-8')
PYEOF
    echo -e "  ${GREEN}✓${NC}  Claude hooks merged into $settings_file"
}

# ---------------------------------------------------------------------------
# Per-project setup (reusable for --add-project and install_user_level)
# ---------------------------------------------------------------------------

# Sets up a single project: symlink + (optional) VS Code tasks + registry entry.
# Expects CrossAI to already be installed at ~/.crossai/.
# Usage: _setup_project <path> [vscode]
#   vscode: "true" (default) or "false" — whether to inject VS Code tasks
_setup_project() {
    local target_project="$1"
    local with_vscode="${2:-true}"
    local meta_file="$HOME/.crossai/.meta.json"

    target_project="${target_project/#\~/$HOME}"   # expand leading ~
    target_project="${target_project%\$}"          # strip trailing $ (shell-prompt bleed)
    target_project="${target_project%/}"           # strip trailing slash
    # Resolve to absolute path
    local original_path="$target_project"
    target_project="$(cd "$target_project" 2>/dev/null && pwd)"

    if [[ ! -d "$target_project" ]]; then
        echo -e "  ${RED}✗${NC}  Directory not found: ${original_path:-<empty path>}"
        return 1
    fi

    # Create artifact dir and symlink
    mkdir -p "$target_project/.crossai"
    local symlink="$target_project/.crossai/orchestrate.py"
    local wrapper_symlink="$target_project/.crossai/crossai_cli.py"
    local hook_symlink="$target_project/.crossai/crossai_hook.py"
    if [[ -L "$symlink" ]]; then
        ln -sf "$HOME/.crossai/orchestrate.py" "$symlink"
        echo -e "  ${GREEN}✓${NC}  Symlink updated: $symlink"
    elif [[ ! -e "$symlink" ]]; then
        ln -s "$HOME/.crossai/orchestrate.py" "$symlink"
        echo -e "  ${GREEN}✓${NC}  Shortcut created: $symlink"
        echo -e "       Legacy run: python .crossai/orchestrate.py --feature ..."
    else
        echo -e "  ${YELLOW}-${NC}  $symlink exists and is not a symlink — skipping shortcut."
    fi

    if [[ -L "$wrapper_symlink" ]]; then
        ln -sf "$HOME/.crossai/scripts/crossai_cli.py" "$wrapper_symlink"
        echo -e "  ${GREEN}✓${NC}  Wrapper symlink updated: $wrapper_symlink"
    elif [[ ! -e "$wrapper_symlink" ]]; then
        ln -s "$HOME/.crossai/scripts/crossai_cli.py" "$wrapper_symlink"
        echo -e "  ${GREEN}✓${NC}  Wrapper shortcut created: $wrapper_symlink"
        echo -e "       Run with: python3 .crossai/crossai_cli.py plan --feature ..."
    else
        echo -e "  ${YELLOW}-${NC}  $wrapper_symlink exists and is not a symlink — skipping wrapper shortcut."
    fi

    if [[ -L "$hook_symlink" ]]; then
        ln -sf "$HOME/.crossai/scripts/crossai_hook.py" "$hook_symlink"
        echo -e "  ${GREEN}✓${NC}  Hook symlink updated: $hook_symlink"
    elif [[ ! -e "$hook_symlink" ]]; then
        ln -s "$HOME/.crossai/scripts/crossai_hook.py" "$hook_symlink"
        echo -e "  ${GREEN}✓${NC}  Hook shortcut created: $hook_symlink"
    else
        echo -e "  ${YELLOW}-${NC}  $hook_symlink exists and is not a symlink — skipping hook shortcut."
    fi

    # Symlink the CrossAI README so users have quickstart docs inside the project
    local readme_symlink="$target_project/.crossai/README.md"
    if [[ -f "$HOME/.crossai/README.md" ]]; then
        if [[ -L "$readme_symlink" ]]; then
            ln -sf "$HOME/.crossai/README.md" "$readme_symlink"
            echo -e "  ${GREEN}✓${NC}  README symlink updated: $readme_symlink"
        elif [[ ! -e "$readme_symlink" ]]; then
            ln -s "$HOME/.crossai/README.md" "$readme_symlink"
            echo -e "  ${GREEN}✓${NC}  Quickstart docs linked: $readme_symlink"
        else
            echo -e "  ${YELLOW}-${NC}  $readme_symlink exists and is not a symlink — skipping README link."
        fi
    fi

    merge_claude_settings "$target_project" ".crossai/crossai_hook.py"

    if [[ "$with_vscode" == "true" ]]; then
        handle_vscode_tasks \
            "$target_project/.vscode/tasks.json" \
            '${env:HOME}/.crossai/orchestrate.py'
    fi
    _record_vscode_project "$meta_file" "$target_project"
}

# ---------------------------------------------------------------------------
# Install modes
# ---------------------------------------------------------------------------

install_user_level() {
    local dest="$HOME/.crossai"
    local meta_file="$dest/.meta.json"

    echo ""
    echo -e "${BOLD}Installing CrossAI (user-level) → $dest${NC}"
    echo ""

    [[ -f "$dest/.version" ]] && confirm_update "$dest"

    copy_core_files "$dest"
    rm -rf "$HOME/.claude/skills/crossai-conducting"
    copy_skill_files \
        "$HOME/.claude/skills/crossai-conductor" \
        "$HOME/.codex/skills/crossai-challenging"
    copy_command_files "$HOME/.claude/commands"

    _write_meta "$meta_file" "user"

    # Project registration — always ask; user can press Enter to skip
    echo ""
    echo -e "Register a project? This creates .crossai/ with a symlink in your"
    echo -e "project so you can run: ${BOLD}python3 .crossai/crossai_cli.py plan --feature ...${NC}"
    read -rp "Project path (Enter to skip): " target_project
    if [[ -n "$target_project" ]]; then
        local with_vscode="false"
        read -rp "Also inject VS Code task shortcuts? [y/N] " vscode_ans
        [[ "$vscode_ans" =~ ^[Yy]$ ]] && with_vscode="true"
        _setup_project "$target_project" "$with_vscode"
        echo ""
        echo -e "  ${BLUE}Tip:${NC} Add more projects later with: ./install.sh --add-project <path>"
    fi

    echo ""
    echo -e "${GREEN}${BOLD}CrossAI $VERSION installed.${NC}"
    echo ""
    echo -e "  Skills registered:"
    echo -e "    ~/.claude/skills/crossai-conductor/"
    echo -e "    ~/.codex/skills/crossai-challenging/"
    echo -e "  Slash commands registered:"
    echo -e "    ~/.claude/commands/crossai-*.md"
    echo ""
    _print_next_steps_user
}

_print_next_steps_user() {
    cat <<EOF
Next steps:
  1. Create your principles file:
       cp ~/.crossai/principles.example.md ~/.crossai/principles.md
       \$EDITOR ~/.crossai/principles.md

  2. Write a feature prompt (inside your project):
       echo "Describe your feature here" > prompt.md

  3. Run ideation:
       cd /your/project
       python3 ~/.crossai/scripts/crossai_cli.py plan \\
         --feature my-feature \\
         --prompt prompt.md

  Full docs: https://github.com/Anandsharma1/crossai
EOF
}

install_repo_level() {
    local cwd
    cwd="$(pwd)"
    local dest="$cwd/cross_ai"
    local meta_file="$dest/.meta.json"

    # Must be run from a git repo root
    if ! git -C "$cwd" rev-parse --show-toplevel &>/dev/null 2>&1; then
        echo -e "${RED}Not inside a git repository. Run from your project root.${NC}"
        exit 1
    fi

    echo ""
    echo -e "${BOLD}Installing CrossAI (repo-level) → $dest${NC}"
    echo ""

    [[ -f "$dest/.version" ]] && confirm_update "$dest"

    copy_core_files "$dest"
    rm -rf "$cwd/.claude/skills/crossai-conducting"
    copy_skill_files \
        "$cwd/.claude/skills/crossai-conductor" \
        "$cwd/.codex/skills/crossai-challenging"
    copy_command_files "$cwd/.claude/commands"
    mkdir -p "$cwd/.crossai"
    ln -snf "../cross_ai/scripts/crossai_hook.py" "$cwd/.crossai/crossai_hook.py"
    merge_claude_settings "$cwd" ".crossai/crossai_hook.py"

    _write_meta "$meta_file" "repo"

    handle_vscode_tasks \
        "$cwd/.vscode/tasks.json" \
        "cross_ai/orchestrate.py"
    _record_vscode_project "$meta_file" "$cwd"

    echo ""
    echo -e "${GREEN}${BOLD}CrossAI $VERSION installed.${NC}"
    echo ""
    echo -e "  Files added to your repo:"
    echo -e "    cross_ai/"
    echo -e "    .crossai/crossai_hook.py"
    echo -e "    .claude/skills/crossai-conductor/"
    echo -e "    .claude/commands/crossai-*.md"
    echo -e "    .claude/settings.json"
    echo -e "    .codex/skills/crossai-challenging/"
    echo -e "    .vscode/tasks.json"
    echo ""
    echo -e "  ${YELLOW}Tip:${NC} Add cross_ai/ and .claude/ and .codex/ to git — they're part of your project."
    echo -e "  ${YELLOW}Tip:${NC} Add .crossai/ to .gitignore — it holds runtime debate artifacts."
    echo ""
    _print_next_steps_repo
}

_print_next_steps_repo() {
    cat <<EOF
Next steps:
  1. Create your principles file:
       cp cross_ai/principles.example.md cross_ai/principles.md
       \$EDITOR cross_ai/principles.md

  2. Write a feature prompt:
       echo "Describe your feature here" > prompt.md

  3. Run ideation:
       python3 cross_ai/scripts/crossai_cli.py plan \\
         --feature my-feature \\
         --prompt prompt.md

  4. Commit the CrossAI files:
       git add cross_ai/ .claude/ .codex/ .vscode/tasks.json
       git commit -m "chore: add CrossAI"
EOF
}

# ---------------------------------------------------------------------------
# Subcommands: --add-project, --list-projects
# ---------------------------------------------------------------------------

cmd_add_project() {
    local project_path="$1"
    project_path="${project_path%\$}"   # strip trailing $ (shell-prompt bleed)
    project_path="${project_path%/}"    # strip trailing slash

    if [[ ! -f "$HOME/.crossai/.version" ]]; then
        echo -e "${RED}CrossAI is not installed at user level (~/.crossai/).${NC}"
        echo "Run ./install.sh first, then use --add-project."
        exit 1
    fi

    echo ""
    echo -e "${BOLD}Adding project: $project_path${NC}"
    echo ""

    _setup_project "$project_path"

    echo ""
    echo -e "${GREEN}Done.${NC} You can now run CrossAI from that project:"
    echo ""
    echo "  cd $project_path"
    echo "  python3 .crossai/crossai_cli.py plan --feature my-feature --prompt prompt.md"
    echo ""
}

_unregister_project() {
    local meta_file="$1" project_path="$2"
    python3 - <<PYEOF
import json

meta_file = '$meta_file'
project_path = '$project_path'

try:
    with open(meta_file) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    data = {'vscode_projects': []}

projects = data.setdefault('vscode_projects', [])
if project_path in projects:
    projects.remove(project_path)
    with open(meta_file, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print('removed')
else:
    print('not-registered')
PYEOF
}

unmerge_claude_settings() {
    local project_root="$1"
    local settings_file="$project_root/.claude/settings.json"
    [[ -f "$settings_file" ]] || return 0
    python3 - <<PYEOF
import json
from pathlib import Path

settings_file = Path(r'''$settings_file''')

try:
    data = json.loads(settings_file.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError
except Exception:
    raise SystemExit(0)

hooks = data.get("hooks")
if not isinstance(hooks, dict):
    raise SystemExit(0)

def _is_crossai_command(cmd):
    return "crossai_hook.py" in str(cmd)

changed = False
for event in ("SessionStart", "Stop"):
    existing = hooks.get(event)
    if not isinstance(existing, list):
        continue
    filtered = []
    for item in existing:
        if not isinstance(item, dict):
            filtered.append(item)
            continue
        # Legacy broken shape: direct command dict.
        if "command" in item and "hooks" not in item:
            if _is_crossai_command(item.get("command", "")):
                continue
            filtered.append(item)
            continue
        # Correct shape: matcher + hooks[].
        inner = item.get("hooks")
        if isinstance(inner, list):
            inner_filtered = [
                h for h in inner
                if not (isinstance(h, dict) and _is_crossai_command(h.get("command", "")))
            ]
            if inner_filtered:
                filtered.append({**item, "hooks": inner_filtered})
            # else: whole matcher group was ours — drop it
        else:
            filtered.append(item)
    if len(filtered) != len(existing):
        changed = True
    if filtered:
        hooks[event] = filtered
    else:
        hooks.pop(event, None)
        changed = True

if changed and not hooks:
    data.pop("hooks", None)

if changed:
    if data:
        settings_file.write_text(json.dumps(data, indent=2) + "\n", encoding='utf-8')
    else:
        settings_file.unlink()
PYEOF
}

unmerge_vscode_tasks() {
    local project_root="$1"
    local tasks_file="$project_root/.vscode/tasks.json"
    [[ -f "$tasks_file" ]] || return 0
    python3 - <<PYEOF
import json
from pathlib import Path

tasks_file = Path(r'''$tasks_file''')

try:
    data = json.loads(tasks_file.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError
except Exception:
    raise SystemExit(0)

tasks = data.get("tasks")
if not isinstance(tasks, list):
    raise SystemExit(0)

filtered = [
    t for t in tasks
    if not (isinstance(t, dict) and str(t.get("label", "")).startswith("CrossAI:"))
]
if len(filtered) == len(tasks):
    raise SystemExit(0)

data["tasks"] = filtered
tasks_file.write_text(json.dumps(data, indent=2) + "\n", encoding='utf-8')
PYEOF
}

cmd_remove_project() {
    local project_path="$1"
    local meta_file="$HOME/.crossai/.meta.json"

    project_path="${project_path/#\~/$HOME}"
    project_path="${project_path%\$}"   # strip trailing $ (shell-prompt bleed)
    project_path="${project_path%/}"    # strip trailing slash
    # Resolve to absolute path if the directory still exists; otherwise keep
    # the input as-is so stale registry entries can still be removed.
    if [[ -d "$project_path" ]]; then
        project_path="$(cd "$project_path" && pwd)"
    fi

    echo ""
    echo -e "${BOLD}Removing project: $project_path${NC}"
    echo ""

    # 1. Unregister from metadata
    if [[ -f "$meta_file" ]]; then
        local status
        status="$(_unregister_project "$meta_file" "$project_path")"
        if [[ "$status" == "removed" ]]; then
            echo -e "  ${GREEN}✓${NC}  Unregistered from $meta_file"
        else
            echo -e "  ${YELLOW}-${NC}  Not found in registry (continuing anyway)"
        fi
    fi

    # 2. Remove our symlinks (only if they ARE symlinks — never touch real files)
    if [[ -d "$project_path/.crossai" ]]; then
        local link removed_any=0
        for name in orchestrate.py crossai_cli.py crossai_hook.py README.md; do
            link="$project_path/.crossai/$name"
            if [[ -L "$link" ]]; then
                rm "$link"
                echo -e "  ${GREEN}✓${NC}  Removed symlink: .crossai/$name"
                removed_any=1
            fi
        done
        # If .crossai/ is now empty, clean it up. Otherwise keep feature artifacts.
        if [[ "$removed_any" -eq 1 ]] && [[ -z "$(ls -A "$project_path/.crossai" 2>/dev/null)" ]]; then
            rmdir "$project_path/.crossai"
            echo -e "  ${GREEN}✓${NC}  Removed empty .crossai/ directory"
        elif [[ -d "$project_path/.crossai" ]] && [[ -n "$(ls -A "$project_path/.crossai" 2>/dev/null)" ]]; then
            echo -e "  ${YELLOW}-${NC}  Kept .crossai/ (contains debate artifacts)"
        fi
    fi

    # 3. Strip CrossAI hook entries from .claude/settings.json
    if [[ -f "$project_path/.claude/settings.json" ]]; then
        unmerge_claude_settings "$project_path"
        echo -e "  ${GREEN}✓${NC}  Cleaned Claude hooks from .claude/settings.json"
    fi

    # 4. Strip CrossAI: tasks from .vscode/tasks.json
    if [[ -f "$project_path/.vscode/tasks.json" ]]; then
        unmerge_vscode_tasks "$project_path"
        echo -e "  ${GREEN}✓${NC}  Cleaned CrossAI tasks from .vscode/tasks.json"
    fi

    echo ""
    echo -e "${GREEN}Done.${NC}"
    echo ""
}

cmd_list_projects() {
    local meta_file="$HOME/.crossai/.meta.json"

    if [[ ! -f "$meta_file" ]]; then
        echo ""
        echo -e "${YELLOW}No CrossAI metadata found.${NC} Either not installed or no projects registered."
        exit 0
    fi

    echo ""
    echo -e "${BOLD}Registered projects:${NC}"
    echo ""

    local count=0
    while IFS= read -r p; do
        [[ -z "$p" ]] && continue
        count=$((count + 1))
        if [[ -d "$p" ]]; then
            echo -e "  ${GREEN}✓${NC}  $p"
        else
            echo -e "  ${YELLOW}?${NC}  $p  (directory not found)"
        fi
    done < <(_get_meta_projects "$meta_file")

    if [[ "$count" -eq 0 ]]; then
        echo "  (none)"
    fi
    echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_print_usage() {
    cat <<EOF
Usage: ./install.sh [OPTIONS]

Options:
  --add-project <path>    Register an existing project (symlink + VS Code tasks)
  --remove-project <path> Unregister a project and remove CrossAI symlinks / hooks
  --list-projects         Show all registered projects
  -h, --help              Show this help

Without options, runs the full install/update flow.
EOF
}

main() {
    # Handle subcommands before the full install flow
    case "${1:-}" in
        --add-project)
            if [[ -z "${2:-}" ]]; then
                echo -e "${RED}Usage: ./install.sh --add-project <project-path>${NC}"
                exit 1
            fi
            cmd_add_project "$2"
            exit 0
            ;;
        --remove-project)
            if [[ -z "${2:-}" ]]; then
                echo -e "${RED}Usage: ./install.sh --remove-project <project-path>${NC}"
                exit 1
            fi
            cmd_remove_project "$2"
            exit 0
            ;;
        --list-projects)
            cmd_list_projects
            exit 0
            ;;
        -h|--help)
            _print_usage
            exit 0
            ;;
    esac

    echo ""
    echo -e "${BLUE}${BOLD}CrossAI Installer v$VERSION${NC}"
    echo ""

    check_prerequisites

    local existing
    existing="$(detect_existing_install)"

    if [[ "$existing" != "none" ]]; then
        # Update path: go straight to the detected mode
        if [[ "$existing" == "user" ]]; then
            install_user_level
        else
            install_repo_level
        fi
        exit 0
    fi

    # Fresh install: ask which mode
    echo "Where would you like to install CrossAI?"
    echo ""
    echo -e "  ${BOLD}1) User-level${NC}  — ~/.crossai/  (shared across all your projects)"
    echo -e "  ${BOLD}2) Repo-level${NC}  — ./cross_ai/  (checked into this project's repo)"
    echo ""
    read -rp "Choice [1/2]: " choice

    case "$choice" in
        1) install_user_level ;;
        2) install_repo_level ;;
        *)
            echo -e "${RED}Invalid choice. Run ./install.sh and enter 1 or 2.${NC}"
            exit 1
            ;;
    esac
}

main "$@"
