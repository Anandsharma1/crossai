#!/usr/bin/env bash
# CrossAI Uninstaller
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

_remove() {
    local path="$1"
    if [[ -e "$path" ]]; then
        rm -rf "$path"
        echo -e "  ${GREEN}✓${NC}  Removed $path"
    else
        echo -e "  ${YELLOW}-${NC}  Not found (skipping) $path"
    fi
}

# Remove CrossAI tasks and inputs from a .vscode/tasks.json, leaving other tasks intact.
strip_vscode_tasks() {
    local tasks_file="$1"
    if [[ ! -f "$tasks_file" ]]; then
        echo -e "  ${YELLOW}-${NC}  Not found (skipping) $tasks_file"
        return
    fi
    python3 - <<PYEOF
import json

CROSSAI_LABELS = {
    "CrossAI: Ideation",
    "CrossAI: Plan",
    "CrossAI: Implement (Claude)",
    "CrossAI: Implement (Codex)",
    "CrossAI: Implement (both)",
    "CrossAI: Review",
}
CROSSAI_INPUT_IDS = {"featureName", "promptFile", "roundCount"}

with open('$tasks_file') as f:
    data = json.load(f)

before = len(data.get('tasks', []))
data['tasks'] = [t for t in data.get('tasks', []) if t.get('label') not in CROSSAI_LABELS]
removed = before - len(data['tasks'])

data['inputs'] = [i for i in data.get('inputs', []) if i.get('id') not in CROSSAI_INPUT_IDS]
if not data['inputs']:
    del data['inputs']

with open('$tasks_file', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')

print(f"  Removed {removed} CrossAI task(s) from $tasks_file")
PYEOF
    echo -e "  ${GREEN}✓${NC}  VS Code tasks cleaned: $tasks_file"
}

# Offer to remove .crossai/ generated debate artifacts from a given project dir.
offer_remove_artifacts() {
    local project_dir="$1"
    local artifacts_dir="$project_dir/.crossai"
    if [[ ! -d "$artifacts_dir" ]]; then
        return
    fi
    echo ""
    echo -e "  ${YELLOW}!${NC}  Generated debate artifacts found: $artifacts_dir"
    read -rp "  Remove generated artifacts (.crossai/)? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        _remove "$artifacts_dir"
    else
        echo -e "  ${YELLOW}-${NC}  Kept $artifacts_dir"
    fi
}

uninstall_user_level() {
    echo ""
    echo -e "${BOLD}Uninstalling CrossAI (user-level)...${NC}"
    echo ""
    read -rp "This will remove ~/.crossai/, ~/.claude/skills/crossai-conducting/, and ~/.codex/skills/crossai-challenging/. Continue? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 0

    _remove "$HOME/.crossai"
    _remove "$HOME/.claude/skills/crossai-conducting"
    _remove "$HOME/.codex/skills/crossai-challenging"

    # VS Code tasks — ask for project path
    echo ""
    read -rp "Remove CrossAI tasks from a project's .vscode/tasks.json? [y/N] " ans
    if [[ "$ans" =~ ^[Yy]$ ]]; then
        local target_project
        read -rp "Project path: " target_project
        target_project="${target_project/#\~/$HOME}"
        if [[ ! -d "$target_project" ]]; then
            echo -e "  ${RED}✗${NC}  Directory not found: $target_project — skipping."
        else
            strip_vscode_tasks "$target_project/.vscode/tasks.json"
            offer_remove_artifacts "$target_project"
        fi
    fi

    echo ""
    echo -e "${GREEN}CrossAI removed.${NC}"
}

uninstall_repo_level() {
    local cwd
    cwd="$(pwd)"
    echo ""
    echo -e "${BOLD}Uninstalling CrossAI (repo-level) from $cwd...${NC}"
    echo ""
    read -rp "This will remove cross_ai/, .claude/skills/crossai-conducting/, and .codex/skills/crossai-challenging/. Continue? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 0

    _remove "$cwd/cross_ai"
    _remove "$cwd/.claude/skills/crossai-conducting"
    _remove "$cwd/.codex/skills/crossai-challenging"

    # VS Code tasks — same project, strip automatically (with confirmation)
    if [[ -f "$cwd/.vscode/tasks.json" ]]; then
        echo ""
        read -rp "Remove CrossAI tasks from .vscode/tasks.json? [y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] && strip_vscode_tasks "$cwd/.vscode/tasks.json"
    fi

    offer_remove_artifacts "$cwd"

    echo ""
    echo -e "${GREEN}CrossAI removed from this repo.${NC}"
}

main() {
    echo ""
    echo -e "${BOLD}CrossAI Uninstaller${NC}"

    if [[ -f "$HOME/.crossai/.version" ]] && [[ -f "$(pwd)/cross_ai/.version" ]]; then
        echo ""
        echo "Both user-level and repo-level installs detected."
        echo "  1) Uninstall user-level (~/.crossai/)"
        echo "  2) Uninstall repo-level (./cross_ai/)"
        read -rp "Choice [1/2]: " choice
        case "$choice" in
            1) uninstall_user_level ;;
            2) uninstall_repo_level ;;
            *) echo -e "${RED}Invalid choice.${NC}"; exit 1 ;;
        esac
    elif [[ -f "$HOME/.crossai/.version" ]]; then
        uninstall_user_level
    elif [[ -f "$(pwd)/cross_ai/.version" ]]; then
        uninstall_repo_level
    else
        echo -e "${YELLOW}No CrossAI installation detected.${NC}"
        exit 0
    fi
}

main "$@"
