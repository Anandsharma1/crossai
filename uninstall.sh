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

uninstall_user_level() {
    echo ""
    echo -e "${BOLD}Uninstalling CrossAI (user-level)...${NC}"
    echo ""
    read -rp "This will remove ~/.crossai/, ~/.claude/skills/crossai-conducting/, and ~/.codex/skills/crossai-challenging/. Continue? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 0

    _remove "$HOME/.crossai"
    _remove "$HOME/.claude/skills/crossai-conducting"
    _remove "$HOME/.codex/skills/crossai-challenging"

    echo ""
    echo -e "${GREEN}CrossAI removed.${NC}"
    echo -e "${YELLOW}Note:${NC} Runtime artifacts in your projects' .crossai/ directories were NOT removed."
    echo -e "      Delete them manually if you no longer need them."
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

    echo ""
    echo -e "${GREEN}CrossAI removed from this repo.${NC}"
    echo -e "${YELLOW}Note:${NC} .vscode/tasks.json was NOT modified. Remove CrossAI tasks from it manually."
    echo -e "${YELLOW}Note:${NC} .crossai/ runtime artifacts were NOT removed. Delete manually if desired."
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
