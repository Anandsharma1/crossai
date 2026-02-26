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

# ---------------------------------------------------------------------------
# Per-project cleanup helpers
# ---------------------------------------------------------------------------

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
if not data.get('inputs'):
    data.pop('inputs', None)

with open('$tasks_file', 'w') as f:
    json.dump(data, f, indent=2)
    f.write('\n')

print(f"  Removed {removed} CrossAI task(s) from $tasks_file")
PYEOF
    echo -e "  ${GREEN}✓${NC}  VS Code tasks cleaned: $tasks_file"
}

# Offer to remove .crossai/ generated debate artifacts from a project dir.
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

# Offer VS Code task cleanup and artifact removal for a single project.
_cleanup_project() {
    local project="$1"
    echo ""
    echo -e "  ${BOLD}Project: $project${NC}"
    if [[ ! -d "$project" ]]; then
        echo -e "  ${YELLOW}-${NC}  Directory no longer exists, skipping."
        return
    fi
    # Remove orchestrate.py symlink (safe — only removes if it is actually a symlink)
    local symlink="$project/.crossai/orchestrate.py"
    if [[ -L "$symlink" ]]; then
        rm "$symlink"
        echo -e "  ${GREEN}✓${NC}  Removed shortcut: $symlink"
    fi
    if [[ -f "$project/.vscode/tasks.json" ]]; then
        read -rp "  Remove CrossAI tasks from .vscode/tasks.json? [y/N] " ans
        [[ "$ans" =~ ^[Yy]$ ]] && strip_vscode_tasks "$project/.vscode/tasks.json"
    fi
    offer_remove_artifacts "$project"
}

# ---------------------------------------------------------------------------
# Install modes
# ---------------------------------------------------------------------------

uninstall_user_level() {
    local meta_file="$HOME/.crossai/.meta.json"

    # Read project list BEFORE removing ~/.crossai (meta lives there)
    local projects=()
    if [[ -f "$meta_file" ]]; then
        while IFS= read -r p; do
            [[ -n "$p" ]] && projects+=("$p")
        done < <(_get_meta_projects "$meta_file")
    fi

    echo ""
    echo -e "${BOLD}Uninstalling CrossAI (user-level)...${NC}"
    echo ""
    read -rp "This will remove ~/.crossai/, ~/.claude/skills/crossai-conducting/, and ~/.codex/skills/crossai-challenging/. Continue? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 0

    _remove "$HOME/.crossai"
    _remove "$HOME/.claude/skills/crossai-conducting"
    _remove "$HOME/.codex/skills/crossai-challenging"

    # Project-level cleanup
    if [[ ${#projects[@]} -gt 0 ]]; then
        echo ""
        echo -e "${BOLD}Project cleanup (${#projects[@]} project(s) had CrossAI tasks installed):${NC}"
        for project in "${projects[@]}"; do
            _cleanup_project "$project"
        done
    else
        # No metadata — fall back to asking
        echo ""
        read -rp "Remove CrossAI tasks from a project's .vscode/tasks.json? [y/N] " ans
        if [[ "$ans" =~ ^[Yy]$ ]]; then
            local target_project
            read -rp "Project path: " target_project
            target_project="${target_project/#\~/$HOME}"
            [[ -d "$target_project" ]] && _cleanup_project "$target_project"
        fi
    fi

    echo ""
    echo -e "${GREEN}CrossAI removed.${NC}"
}

uninstall_repo_level() {
    local cwd
    cwd="$(pwd)"
    local meta_file="$cwd/cross_ai/.meta.json"

    # Read project list before removing cross_ai/
    local projects=()
    if [[ -f "$meta_file" ]]; then
        while IFS= read -r p; do
            [[ -n "$p" ]] && projects+=("$p")
        done < <(_get_meta_projects "$meta_file")
    fi

    echo ""
    echo -e "${BOLD}Uninstalling CrossAI (repo-level) from $cwd...${NC}"
    echo ""
    read -rp "This will remove cross_ai/, .claude/skills/crossai-conducting/, and .codex/skills/crossai-challenging/. Continue? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 0

    _remove "$cwd/cross_ai"
    _remove "$cwd/.claude/skills/crossai-conducting"
    _remove "$cwd/.codex/skills/crossai-challenging"

    # Project-level cleanup (for repo-level this is always the cwd)
    if [[ ${#projects[@]} -gt 0 ]]; then
        echo ""
        echo -e "${BOLD}Project cleanup:${NC}"
        for project in "${projects[@]}"; do
            _cleanup_project "$project"
        done
    else
        # No metadata — clean the current project directly
        _cleanup_project "$cwd"
    fi

    echo ""
    echo -e "${GREEN}CrossAI removed from this repo.${NC}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

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
