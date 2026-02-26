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
    mkdir -p "$dest/prompts"
    cp "$SCRIPT_DIR/orchestrate.py"        "$dest/orchestrate.py"
    chmod +x "$dest/orchestrate.py"
    cp -r "$SCRIPT_DIR/prompts/."          "$dest/prompts/"
    cp "$SCRIPT_DIR/principles.example.md" "$dest/principles.example.md"
    echo "$VERSION"                        > "$dest/.version"
}

copy_skill_files() {
    local claude_dest="$1" codex_dest="$2"
    mkdir -p "$claude_dest" "$codex_dest"
    cp "$SCRIPT_DIR/skills/claude/SKILL.md" "$claude_dest/SKILL.md"
    cp "$SCRIPT_DIR/skills/codex/SKILL.md"  "$codex_dest/SKILL.md"
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

# ---------------------------------------------------------------------------
# Install modes
# ---------------------------------------------------------------------------

install_user_level() {
    local dest="$HOME/.crossai"

    echo ""
    echo -e "${BOLD}Installing CrossAI (user-level) → $dest${NC}"
    echo ""

    [[ -f "$dest/.version" ]] && confirm_update "$dest"

    copy_core_files "$dest"
    copy_skill_files \
        "$HOME/.claude/skills/crossai-conducting" \
        "$HOME/.codex/skills/crossai-challenging"

    # VS Code tasks — ask for target project path
    echo ""
    read -rp "Inject VS Code task shortcuts into a project? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        local target_project
        read -rp "Project path (absolute, must be a git repo): " target_project
        target_project="${target_project/#\~/$HOME}"   # expand leading ~
        if [[ ! -d "$target_project" ]]; then
            echo -e "  ${RED}✗${NC}  Directory not found: $target_project — skipping VS Code tasks."
        elif ! git -C "$target_project" rev-parse --git-dir &>/dev/null 2>&1; then
            echo -e "  ${RED}✗${NC}  Not a git repository: $target_project — skipping VS Code tasks."
        else
            handle_vscode_tasks \
                "$target_project/.vscode/tasks.json" \
                '${env:HOME}/.crossai/orchestrate.py'
        fi
    fi

    echo ""
    echo -e "${GREEN}${BOLD}CrossAI $VERSION installed.${NC}"
    echo ""
    echo -e "  Skills registered:"
    echo -e "    ~/.claude/skills/crossai-conducting/"
    echo -e "    ~/.codex/skills/crossai-challenging/"
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
       python ~/.crossai/orchestrate.py \\
         --feature my-feature \\
         --prompt prompt.md \\
         --phase ideation

  Full docs: https://github.com/<your-org>/crossai
EOF
}

install_repo_level() {
    local cwd
    cwd="$(pwd)"
    local dest="$cwd/cross_ai"

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
    copy_skill_files \
        "$cwd/.claude/skills/crossai-conducting" \
        "$cwd/.codex/skills/crossai-challenging"

    handle_vscode_tasks \
        "$cwd/.vscode/tasks.json" \
        "cross_ai/orchestrate.py"

    echo ""
    echo -e "${GREEN}${BOLD}CrossAI $VERSION installed.${NC}"
    echo ""
    echo -e "  Files added to your repo:"
    echo -e "    cross_ai/"
    echo -e "    .claude/skills/crossai-conducting/"
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
       python cross_ai/orchestrate.py \\
         --feature my-feature \\
         --prompt prompt.md \\
         --phase ideation

  4. Commit the CrossAI files:
       git add cross_ai/ .claude/ .codex/ .vscode/tasks.json
       git commit -m "chore: add CrossAI"
EOF
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
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
