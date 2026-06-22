# Changelog

All notable changes to CrossAI are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added
- Configurable Codex instance: `CROSSAI_CODEX_CMD` overrides the codex binary and top-level flags, and `CODEX_HOME` selects an alternate Codex config dir. Honored by both `scripts/crossai_cli.py` and the legacy `orchestrate.py`.
- `--codex-home PATH` and `--codex-cmd CMD` flags on the `/crossai-generic`, `/crossai-plan`, `/crossai-implement`, and `/crossai-loop` slash commands, which set the matching env vars on the Python call.

### Fixed
- `orchestrate.py` no longer hardcodes the `codex` binary — it now respects `CROSSAI_CODEX_CMD`, matching `crossai_cli.py`.

---

## [0.1.0] — 2026-02-26

### Added
- Initial public release
- `install.sh` with user-level and repo-level install modes
- `uninstall.sh` for clean removal
- Four-phase pipeline: ideation → plan → implement → review
- VS Code task shortcuts via `tasks.template.json`
- Prerequisite verification (claude, codex, python3, uv, git)
- Update detection: re-running installer upgrades in place
- `principles.example.md` template for shared team principles
- Full documentation: README, manual install guide, phases, principles, VS Code integration
