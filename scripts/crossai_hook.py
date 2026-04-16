#!/usr/bin/env python3
"""Minimal Claude hook helpers for project-local CrossAI state."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _project_dir() -> Path:
    env_dir = Path.cwd()
    project_env = None
    try:
        import os
        project_env = os.environ.get("CLAUDE_PROJECT_DIR")
    except Exception:
        project_env = None
    if project_env:
        return Path(project_env).resolve()
    return env_dir.resolve()


def _find_active_run_state(project_dir: Path) -> tuple[Path, dict] | None:
    crossai_dir = project_dir / ".crossai"
    if not crossai_dir.exists():
        return None

    candidates = []
    for path in crossai_dir.glob("*/run_state.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        candidates.append((path, data))

    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0].stat().st_mtime, reverse=True)
    return candidates[0]


def session_start() -> int:
    found = _find_active_run_state(_project_dir())
    if not found:
        return 0

    path, data = found
    feature = data.get("feature", path.parent.name)
    phase = data.get("phase", "unknown")
    status = data.get("status", "unknown")
    current_pass = data.get("current_pass")
    max_passes = data.get("max_passes")

    extra = [
        f"Active CrossAI feature: {feature}",
        f"CrossAI phase: {phase}",
        f"CrossAI status: {status}",
        f"CrossAI state file: {path}",
    ]
    if current_pass is not None and max_passes is not None:
        extra.append(f"CrossAI review loop progress: pass {current_pass} of {max_passes}")

    payload = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "\n".join(extra),
        }
    }
    print(json.dumps(payload))
    return 0


def stop_check() -> int:
    # Reserved for future gating. Keep this hook non-blocking for now.
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: crossai_hook.py <session-start|stop-check>", file=sys.stderr)
        return 1

    command = sys.argv[1]
    if command == "session-start":
        return session_start()
    if command == "stop-check":
        return stop_check()

    print(f"unknown command: {command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
