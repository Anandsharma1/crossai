#!/usr/bin/env python3
"""Claude-native wrapper around the current CrossAI orchestrator."""

from __future__ import annotations

import argparse
import json
import os
import re
import selectors
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR = ROOT / "orchestrate.py"
PROMPTS_DIR = ROOT / "prompts"
PROJECT_MARKERS = [
    ".git",
    ".vscode",
    "pyproject.toml",
    "package.json",
    "Cargo.toml",
    "go.mod",
]
AGENTS = {"claude", "codex"}
SESSION_POLICIES = ("auto", "fresh", "resume")
SCOPE_POLICIES = ("adjudicate", "interactive", "off")
HISTORY_CHAR_LIMIT = 80_000
STREAM_IDLE_TIMEOUT_SECONDS = int(os.environ.get("CROSSAI_CLI_IDLE_TIMEOUT", "300"))
STREAM_TOTAL_TIMEOUT_SECONDS = int(os.environ.get("CROSSAI_CLI_TOTAL_TIMEOUT", "1800"))
# Override the codex binary + top-level flags via CROSSAI_CODEX_CMD, e.g.:
#   CROSSAI_CODEX_CMD='codex --yolo'
# Set CODEX_HOME separately in the shell environment if needed.
CODEX_CMD: list[str] = shlex.split(os.environ.get("CROSSAI_CODEX_CMD", "codex"))
FEATURE_SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
DEBATE_PHASES = {
    "generic": {
        "prefix": "response",
        "groom": "generic",
        "critique": "generic_critique",
        "revise": "generic_revise",
        "revise_final": "generic_revise_final",
        "scope_supported": False,
    },
    "ideation": {
        "prefix": "direction",
        "groom": "ideation",
        "critique": "ideation_critique",
        "revise": "ideation_revise",
        "revise_final": "ideation_revise_final",
        "scope_supported": True,
    },
    "plan": {
        "prefix": "plan",
        "groom": "groom",
        "critique": "critique",
        "revise": "revise",
        "revise_final": "revise_final",
        "scope_supported": True,
    },
}


class CrossAIError(RuntimeError):
    """Base error for wrapper failures."""


class OutputParseError(CrossAIError):
    """Raised when CLI JSON output cannot be parsed."""


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def find_project_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()

    current = Path.cwd().resolve()
    # First pass: prefer the nearest ancestor with an existing .crossai/ directory.
    # This respects projects explicitly registered via `install.sh --add-project`.
    for candidate in [current, *current.parents]:
        if (candidate / ".crossai").is_dir():
            return candidate
    # Second pass: fall back to the nearest project marker (.git, .vscode, etc.).
    for candidate in [current, *current.parents]:
        if any((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
    return current


def crossai_dir(project_root: Path) -> Path:
    return project_root / ".crossai"


def feature_dir(project_root: Path, feature: str) -> Path:
    return crossai_dir(project_root) / feature


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def sessions_path(project_root: Path, feature: str) -> Path:
    return feature_dir(project_root, feature) / "sessions.json"


def run_state_path(project_root: Path, feature: str) -> Path:
    return feature_dir(project_root, feature) / "run_state.json"


def load_sessions(project_root: Path, feature: str) -> dict:
    return load_json(
        sessions_path(project_root, feature),
        {
            "debate": {"ideation": {}, "plan": {}},
            "implement": {},
            "review": {"passes": []},
        },
    )


def save_sessions(project_root: Path, feature: str, payload: dict) -> None:
    write_json(sessions_path(project_root, feature), payload)


def save_run_state(project_root: Path, feature: str, payload: dict) -> None:
    write_json(run_state_path(project_root, feature), payload)


def load_prompt_template(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise CrossAIError(f"prompt template not found: {path}")
    return read_text(path)


def assemble_prompt(template_name: str, variables: dict[str, str]) -> str:
    template = load_prompt_template(template_name)
    for key, value in variables.items():
        template = template.replace(f"{{{{{key}}}}}", str(value))
    unresolved = sorted(set(re.findall(r"{{([A-Za-z0-9_]+)}}", template)))
    if unresolved:
        raise CrossAIError(
            f"prompt template '{template_name}' still has unresolved variables: {', '.join(unresolved)}"
        )
    return template


def load_principles(project_root: Path, feature: str) -> str:
    candidates = [
        feature_dir(project_root, feature) / "principles.md",
        crossai_dir(project_root) / "principles.md",
        ROOT / "principles.md",
    ]
    for candidate in candidates:
        if candidate.exists():
            return read_text(candidate)
    return "(No shared principles defined.)"


def latest_plan_file(project_root: Path, feature: str, agent: str) -> Path | None:
    plan_dir = feature_dir(project_root, feature) / "plan"
    if not plan_dir.exists():
        return None

    rounds = sorted(
        (
            path
            for path in plan_dir.iterdir()
            if path.is_dir() and path.name.startswith("r")
        ),
        key=lambda path: int(path.name[1:]) if path.name[1:].isdigit() else -1,
        reverse=True,
    )

    for round_dir in rounds:
        candidate = round_dir / f"{agent}.revised_plan.md"
        if candidate.exists():
            return candidate
        candidate = round_dir / f"{agent}.plan.md"
        if candidate.exists():
            return candidate
    return None


def latest_debate_output(
    project_root: Path, feature: str, phase: str, agent: str
) -> Path | None:
    phase_dir = feature_dir(project_root, feature) / phase
    if not phase_dir.exists():
        return None

    rounds = sorted(
        (
            path
            for path in phase_dir.iterdir()
            if path.is_dir() and path.name.startswith("r")
        ),
        key=lambda path: int(path.name[1:]) if path.name[1:].isdigit() else -1,
        reverse=True,
    )
    prefix = DEBATE_PHASES[phase]["prefix"]

    for round_dir in rounds:
        for candidate in [
            round_dir / f"{agent}.revised_{prefix}.md",
            round_dir / f"{agent}.{prefix}.md",
        ]:
            if candidate.exists():
                return candidate
    return None


def worktree_path(project_root: Path, feature: str, agent: str) -> Path:
    return project_root / f"wt-{feature}-{agent}"


def branch_name(feature: str, agent: str) -> str:
    return f"feat/{feature}-{agent}"


def quote_cmd(cmd: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def validate_feature_slug(feature: str) -> None:
    if not FEATURE_SLUG_RE.fullmatch(feature):
        raise CrossAIError(
            "feature must match [A-Za-z0-9][A-Za-z0-9._-]* and must not contain spaces or path separators"
        )


def stdin_is_tty() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def terminate_process(proc: subprocess.Popen[bytes]) -> str:
    try:
        proc.kill()
    except OSError:
        pass
    try:
        stdout, _ = proc.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, _ = proc.communicate()
    tail = stdout.decode("utf-8", errors="replace") if stdout else ""
    if tail:
        print(tail, end="", flush=True)
    return tail


def stream_command(
    cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None
) -> str:
    print(f"$ {quote_cmd(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=False,
        bufsize=0,
    )

    chunks: list[str] = []
    assert proc.stdout is not None
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    start_time = time.monotonic()
    last_output_time = start_time

    while True:
        now = time.monotonic()
        if now - start_time > STREAM_TOTAL_TIMEOUT_SECONDS:
            output = "".join(chunks) + terminate_process(proc)
            raise CrossAIError(
                f"command exceeded total timeout of {STREAM_TOTAL_TIMEOUT_SECONDS}s: {quote_cmd(cmd)}\n{output.strip()}"
            )

        events = selector.select(timeout=1)
        if events:
            for key, _ in events:
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                text = chunk.decode("utf-8", errors="replace")
                print(text, end="", flush=True)
                chunks.append(text)
                last_output_time = time.monotonic()
        elif (
            proc.poll() is None and now - last_output_time > STREAM_IDLE_TIMEOUT_SECONDS
        ):
            output = "".join(chunks) + terminate_process(proc)
            raise CrossAIError(
                f"command produced no output for {STREAM_IDLE_TIMEOUT_SECONDS}s: {quote_cmd(cmd)}\n{output.strip()}"
            )

        if proc.poll() is not None and not selector.get_map():
            break

    code = proc.wait()
    output = "".join(chunks)
    if code != 0:
        raise subprocess.CalledProcessError(code, cmd, output=output)
    return output


def run_capture(cmd: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd, output=result.stdout, stderr=result.stderr
        )
    return result.stdout


def run_command_checked(cmd: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip()
        raise SystemExit(f"command failed: {quote_cmd(cmd)}\n{details}")


def tmux_available() -> bool:
    return bool(os.environ.get("TMUX")) and shutil.which("tmux") is not None


def stream_command_with_mode(
    cmd: list[str], *, cwd: Path | None, display_mode: str
) -> str:
    if display_mode != "tmux":
        return stream_command(cmd, cwd=cwd)

    if not stdin_is_tty():
        print(
            "tmux mode requested without an interactive TTY; falling back to inline mode."
        )
        return stream_command(cmd, cwd=cwd)

    if not tmux_available():
        print(
            "tmux mode requested but tmux is unavailable in this session; falling back to inline mode."
        )
        return stream_command(cmd, cwd=cwd)

    import tempfile

    with tempfile.NamedTemporaryFile(
        prefix="crossai-tmux-", suffix=".log", delete=False
    ) as handle:
        log_path = Path(handle.name)

    shell_cmd = f"cd {shlex.quote(str(cwd or Path.cwd()))} && {quote_cmd(cmd)} | tee {shlex.quote(str(log_path))}"
    result = subprocess.run(
        ["tmux", "split-window", "-v", "-c", str(cwd or Path.cwd()), shell_cmd],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("tmux split-window failed; falling back to inline mode.")
        return stream_command(cmd, cwd=cwd)

    print(f"Spawned tmux pane for command output. Log: {log_path}")
    print("Press Enter here after the pane command finishes to continue.")
    input()
    try:
        return read_text(log_path)
    finally:
        try:
            log_path.unlink()
        except OSError:
            pass


def get_worktree_diff(wt_path: Path) -> str:
    diff = run_capture(["git", "diff", "HEAD"], cwd=wt_path).strip()
    if diff:
        return diff

    diff = run_capture(["git", "diff", "--cached"], cwd=wt_path).strip()
    if diff:
        return diff

    status = run_capture(["git", "status", "--short"], cwd=wt_path).strip()
    return f"[No diff available. Git status:\n{status}\n]"


def ensure_agent(name: str, label: str) -> str:
    if name not in AGENTS:
        raise SystemExit(f"{label} must be one of: {', '.join(sorted(AGENTS))}")
    return name


def native_session_id(entry: dict | None) -> str | None:
    if not entry:
        return None
    if entry.get("provider") == "claude":
        return entry.get("session_id")
    if entry.get("provider") == "codex":
        return entry.get("thread_id")
    native = entry.get("native_session")
    if isinstance(native, dict):
        return native.get("session_id") or native.get("thread_id")
    return None


def native_session_payload(agent: str, session_id: str) -> dict:
    payload = {"provider": "claude" if agent == "claude" else "codex"}
    if session_id:
        if agent == "claude":
            payload["session_id"] = session_id
        else:
            payload["thread_id"] = session_id
    return payload


def resolved_session_id(entry: dict | None, policy: str, label: str) -> str | None:
    session_id = native_session_id(entry)
    if policy == "fresh":
        return None
    if policy == "resume":
        if not session_id:
            raise SystemExit(
                f"no saved native session found for {label}; use --session-policy fresh or auto first"
            )
        return session_id
    return session_id


def parse_claude_json_output(output: str) -> dict:
    stripped = output.strip()
    if not stripped:
        raise OutputParseError("Claude returned empty output")
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise OutputParseError(f"unable to parse Claude JSON output: {exc}") from exc
    if payload.get("type") != "result":
        raise OutputParseError("unexpected Claude JSON output format")
    return {
        "text": payload.get("result", "").strip(),
        "session_id": payload.get("session_id"),
        "raw": payload,
    }


def parse_codex_json_output(output: str) -> dict:
    thread_id = None
    final_text = None
    events = []

    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        events.append(event)
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
        item = event.get("item")
        if (
            event.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "agent_message"
        ):
            final_text = item.get("text", "").strip()

    if final_text is None:
        event_types = ", ".join(event.get("type", "?") for event in events[-5:])
        raise OutputParseError(
            "unable to parse final Codex message from JSON output"
            + (f" (recent event types: {event_types})" if event_types else "")
        )

    return {
        "text": final_text,
        "session_id": thread_id,
        "raw": events,
    }


def run_claude_session(
    prompt: str,
    *,
    cwd: Path,
    display_mode: str,
    session_id: str | None = None,
    max_turns: int = 20,
    tools_enabled: bool = True,
) -> dict:
    cmd = ["claude", "-p", "--output-format", "json"]
    if session_id:
        cmd.extend(["--resume", session_id])
    if not tools_enabled:
        cmd.extend(["--tools", ""])
    cmd.extend(["--max-turns", str(max_turns), prompt])
    output = stream_command_with_mode(cmd, cwd=cwd, display_mode=display_mode)
    parsed = parse_claude_json_output(output)
    parsed["session_id"] = parsed["session_id"] or session_id
    parsed["provider"] = "claude"
    return parsed


def run_codex_session(
    prompt: str,
    *,
    cwd: Path,
    display_mode: str,
    thread_id: str | None = None,
    sandbox_mode: str = "workspace-write",
    full_auto: bool = True,
) -> dict:
    if thread_id:
        # `codex exec resume` does not accept -s/--sandbox; use -c config override.
        cmd = [*CODEX_CMD, "exec", "resume", "--json"]
        if full_auto:
            cmd.append("--full-auto")
        else:
            cmd.extend(["-c", f'sandbox_mode="{sandbox_mode}"'])
        cmd.extend([thread_id, prompt])
    else:
        cmd = [*CODEX_CMD, "exec", "--json"]
        if full_auto:
            cmd.append("--full-auto")
        else:
            cmd.extend(["-s", sandbox_mode])
        cmd.append(prompt)

    output = stream_command_with_mode(cmd, cwd=cwd, display_mode=display_mode)
    parsed = parse_codex_json_output(output)
    parsed["session_id"] = parsed["session_id"] or thread_id
    parsed["provider"] = "codex"
    return parsed


def run_agent_session(
    agent: str,
    prompt: str,
    *,
    cwd: Path,
    display_mode: str,
    session_id: str | None = None,
    review_mode: bool = False,
) -> dict:
    if agent == "claude":
        return run_claude_session(
            prompt,
            cwd=cwd,
            display_mode=display_mode,
            session_id=session_id,
            max_turns=1 if review_mode else 20,
            tools_enabled=not review_mode,
        )
    return run_codex_session(
        prompt,
        cwd=cwd,
        display_mode=display_mode,
        thread_id=session_id,
        sandbox_mode="read-only" if review_mode else "workspace-write",
        full_auto=not review_mode,
    )


def setup_worktree(project_root: Path, feature: str, agent: str) -> Path:
    wt_path = worktree_path(project_root, feature, agent)
    if wt_path.exists():
        return wt_path

    branch = branch_name(feature, agent)
    subprocess.run(
        ["git", "branch", branch], cwd=str(project_root), capture_output=True, text=True
    )
    run_command_checked(
        ["git", "worktree", "add", str(wt_path), branch], cwd=project_root
    )
    return wt_path


def prepare_implementation_context(
    project_root: Path, feature: str, agent: str
) -> tuple[Path, str, str]:
    wt_path = setup_worktree(project_root, feature, agent)
    plan_path = latest_plan_file(project_root, feature, agent)
    if plan_path is None:
        raise SystemExit(f"no {agent} plan artifact found for feature {feature}")

    plan = read_text(plan_path)
    principles = load_principles(project_root, feature)

    wt_crossai = wt_path / ".crossai" / feature
    write_text(wt_crossai / "plan.md", plan)
    write_text(wt_crossai / "principles.md", principles)
    return wt_path, plan, principles


def write_artifact(
    path: Path, content: str, *, phase: str, round_num: int, step: str, agent: str
) -> None:
    header = (
        f"<!-- CrossAI | phase: {phase} | round: {round_num} | step: {step} "
        f"| agent: {agent} | timestamp: {iso_now()} -->\n\n"
    )
    write_text(path, header + content.strip() + "\n")


def format_history(entries: list[dict], initial_prompt: str) -> str:
    parts = [f"### Initial Prompt\n{initial_prompt}"]
    for entry in entries:
        parts.append(
            f"### Round {entry['round']} — {entry['step']} ({entry['agent']})\n{entry['content']}"
        )
    return "\n\n---\n\n".join(parts)


def format_history_with_summary(
    entries: list[dict], initial_prompt: str, summary: str | None, summarized_up_to: int
) -> str:
    parts = [f"### Initial Prompt\n{initial_prompt}"]
    if summary:
        parts.append(
            f"### Summary of Earlier Rounds (up to round {summarized_up_to})\n{summary}"
        )
    for entry in entries:
        parts.append(
            f"### Round {entry['round']} — {entry['step']} ({entry['agent']})\n{entry['content']}"
        )
    return "\n\n---\n\n".join(parts)


def summarize_history_if_needed(
    project_root: Path,
    *,
    initial_prompt: str,
    summary: str | None,
    summarized_up_to: int,
    history_entries: list[dict],
) -> tuple[str | None, int, list[dict]]:
    formatted = format_history_with_summary(
        history_entries, initial_prompt, summary, summarized_up_to
    )
    if len(formatted) <= HISTORY_CHAR_LIMIT or len(history_entries) <= 2:
        return summary, summarized_up_to, history_entries

    latest_round = max(entry["round"] for entry in history_entries)
    older = [entry for entry in history_entries if entry["round"] < latest_round]
    recent = [entry for entry in history_entries if entry["round"] >= latest_round]
    if not older:
        return summary, summarized_up_to, history_entries

    parts = []
    if summary:
        parts.append(f"Previous summary:\n{summary}")
    for entry in older:
        if entry["round"] > summarized_up_to:
            parts.append(
                f"Round {entry['round']} — {entry['step']} ({entry['agent']}):\n{entry['content']}"
            )

    if not parts:
        return summary, summarized_up_to, history_entries

    prompt = (
        "Summarize the following debate history concisely. Preserve key decisions, agreements, "
        "disagreements, scope choices, and open questions. Keep it under 2000 words.\n\n"
        + "\n\n---\n\n".join(parts)
    )
    result = run_claude_session(
        prompt,
        cwd=project_root,
        display_mode="inline",
        session_id=None,
        max_turns=1,
        tools_enabled=False,
    )
    new_summary = result["text"].strip()
    new_summarized_up_to = max(entry["round"] for entry in older)
    return new_summary, new_summarized_up_to, recent


def append_log(
    log_entries: list[dict], round_num: int, step: str, agent: str, content: str
) -> None:
    log_entries.append(
        {
            "timestamp": iso_now(),
            "round": round_num,
            "step": step,
            "agent": agent,
            "content": content.strip(),
        }
    )


def save_debate_log(
    project_root: Path, feature: str, phase: str, log_entries: list[dict]
) -> None:
    path = feature_dir(project_root, feature) / phase / "debate.log.md"
    lines = [
        f"# CrossAI Debate Log: {feature} ({phase})",
        "",
    ]
    for entry in log_entries:
        lines.extend(
            [
                f"## Round {entry['round']} — {entry['step']} ({entry['agent']})",
                f"*{entry['timestamp']}*",
                "",
                entry["content"],
                "",
                "---",
                "",
            ]
        )
    write_text(path, "\n".join(lines).rstrip() + "\n")


def latest_phase_artifact(
    project_root: Path, feature: str, phase: str, agent: str
) -> Path | None:
    return latest_debate_output(project_root, feature, phase, agent)


def parse_numbered_items(text: str) -> dict[int, str]:
    items: dict[int, str] = {}
    current_num: int | None = None
    current_text: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped and stripped[0].isdigit() and "." in stripped.split()[0]:
            if current_num is not None:
                items[current_num] = " ".join(current_text).strip()
            try:
                current_num = int(stripped.split(".")[0])
            except ValueError:
                current_num = None
                current_text = []
                continue
            current_text = [stripped.split(".", 1)[1].strip()]
        elif current_num is not None and stripped:
            current_text.append(stripped)

    if current_num is not None:
        items[current_num] = " ".join(current_text).strip()

    return items


def extract_constraints_section(markdown: str) -> str:
    marker = "# Constraints for Subsequent Rounds"
    if marker not in markdown:
        return markdown.strip()
    after = markdown.split(marker, 1)[1]
    next_heading = after.find("\n# ")
    if next_heading != -1:
        after = after[:next_heading]
    return after.strip()


def scope_artifact_path(
    project_root: Path, feature: str, phase: str, name: str
) -> Path:
    return feature_dir(project_root, feature) / phase / name


def run_scope_audit(
    initial_prompt: str, claude_output: str, codex_output: str, project_root: Path
) -> str:
    prompt = assemble_prompt(
        "scope_check",
        {
            "initial_prompt": initial_prompt,
            "claude_output": claude_output,
            "codex_output": codex_output,
        },
    )
    result = run_claude_session(
        prompt,
        cwd=project_root,
        display_mode="inline",
        session_id=None,
        max_turns=1,
        tools_enabled=False,
    )
    return result["text"].strip()


def resolve_scope_decisions(
    project_root: Path,
    *,
    feature: str,
    phase: str,
    initial_prompt: str,
    claude_output: str,
    codex_output: str,
    scope_policy: str,
) -> tuple[str | None, Path | None]:
    if scope_policy == "off":
        return None, None

    candidates = run_scope_audit(
        initial_prompt, claude_output, codex_output, project_root
    )
    candidates_path = scope_artifact_path(
        project_root, feature, phase, "scope_candidates.md"
    )
    write_text(candidates_path, candidates + "\n")

    if "NO_SCOPE_ISSUES" in candidates:
        decision_path = scope_artifact_path(
            project_root, feature, phase, "scope_decisions.md"
        )
        write_text(
            decision_path,
            "# Scope Drift Considered\n- No significant scope drift detected.\n\n# Notes\n- No extra scope constraints were added.\n",
        )
        return None, decision_path

    if scope_policy == "interactive":
        if not stdin_is_tty():
            print(
                "interactive scope policy requested without a TTY; falling back to adjudicate."
            )
            scope_policy = "adjudicate"
        else:
            print(f"\n{candidates}\n")
            print("Which items should be excluded from scope?")
            print("  - Enter numbers: 1,3")
            print("  - Or 'all' to exclude everything listed")
            print("  - Or free text to add another exclusion")
            print("  - Press Enter to accept all candidate items")
            try:
                answer = input("\nExclude: ").strip()
            except (EOFError, KeyboardInterrupt):
                answer = ""

            items = parse_numbered_items(candidates)
            excluded: list[str] = []
            free_text = ""
            if answer.lower() == "all":
                excluded = [items[n] for n in sorted(items)]
            elif answer:
                parts = [part.strip() for part in answer.split(",") if part.strip()]
                for part in parts:
                    if part.isdigit() and int(part) in items:
                        excluded.append(items[int(part)])
                    elif part:
                        free_text = f"{free_text} {part}".strip()

            decision_lines = [
                "# Scope Drift Considered",
                candidates,
                "",
                "# Accepted into Scope",
            ]
            if not excluded and not free_text:
                decision_lines.append(
                    "- All candidate items were accepted into scope for this run."
                )
            else:
                decision_lines.append(
                    "- Only non-excluded candidate items remain in scope."
                )
            decision_lines.extend(
                [
                    "",
                    "# Rejected from V1 Scope",
                ]
            )
            if excluded:
                decision_lines.extend([f"- {item}" for item in excluded])
            if free_text:
                decision_lines.append(f"- {free_text}")
            if not excluded and not free_text:
                decision_lines.append("- None.")
            decision_lines.extend(
                [
                    "",
                    "# Constraints for Subsequent Rounds",
                ]
            )
            if excluded:
                decision_lines.extend(
                    [f"- Do not expand scope to include: {item}" for item in excluded]
                )
            if free_text:
                decision_lines.append(f"- Do not expand scope to include: {free_text}")
            if not excluded and not free_text:
                decision_lines.append("- No extra scope constraints.")
            decision_lines.extend(
                [
                    "",
                    "# Notes",
                    "- Generated from interactive scope confirmation.",
                    "",
                ]
            )
            decision_text = "\n".join(decision_lines)
            decision_path = scope_artifact_path(
                project_root, feature, phase, "scope_decisions.md"
            )
            write_text(decision_path, decision_text)
            constraints = extract_constraints_section(decision_text)
            return (constraints if excluded or free_text else None), decision_path

    claude_prompt = assemble_prompt(
        "scope_adjudicate",
        {
            "initial_prompt": initial_prompt,
            "candidate_items": candidates,
            "own_output": claude_output,
            "other_output": codex_output,
        },
    )
    codex_prompt = assemble_prompt(
        "scope_adjudicate",
        {
            "initial_prompt": initial_prompt,
            "candidate_items": candidates,
            "own_output": codex_output,
            "other_output": claude_output,
        },
    )
    claude_scope = run_claude_session(
        claude_prompt,
        cwd=project_root,
        display_mode="inline",
        session_id=None,
        max_turns=1,
        tools_enabled=False,
    )["text"]
    codex_scope = run_codex_session(
        codex_prompt,
        cwd=project_root,
        display_mode="inline",
        thread_id=None,
        sandbox_mode="read-only",
        full_auto=False,
    )["text"]

    write_text(
        scope_artifact_path(
            project_root, feature, phase, "scope_adjudication.claude.md"
        ),
        claude_scope.strip() + "\n",
    )
    write_text(
        scope_artifact_path(
            project_root, feature, phase, "scope_adjudication.codex.md"
        ),
        codex_scope.strip() + "\n",
    )

    merge_prompt = assemble_prompt(
        "scope_merge",
        {
            "initial_prompt": initial_prompt,
            "candidate_items": candidates,
            "claude_scope": claude_scope,
            "codex_scope": codex_scope,
        },
    )
    merged = run_claude_session(
        merge_prompt,
        cwd=project_root,
        display_mode="inline",
        session_id=None,
        max_turns=1,
        tools_enabled=False,
    )["text"]
    decision_path = scope_artifact_path(
        project_root, feature, phase, "scope_decisions.md"
    )
    write_text(decision_path, merged.strip() + "\n")
    return extract_constraints_section(merged), decision_path


def run_debate_phase_native(
    project_root: Path,
    *,
    feature: str,
    phase: str,
    initial_prompt: str,
    rounds: int,
    session_policy: str,
    scope_policy: str,
    read_codebase: bool,
    display_mode: str = "inline",
) -> Path:
    if phase not in DEBATE_PHASES:
        raise SystemExit(f"unsupported debate phase: {phase}")
    if rounds < 1:
        raise SystemExit("--rounds must be >= 1")

    config = DEBATE_PHASES[phase]
    phase_root = feature_dir(project_root, feature) / phase
    ensure_dir(phase_root)
    write_text(phase_root / "initial_prompt.md", initial_prompt)

    principles = load_principles(project_root, feature)
    if not read_codebase:
        principles += (
            "\n\n## Codebase Access — RESTRICTED\n"
            "Do NOT read, browse, or analyze project source code files or directories. "
            "You may read CrossAI artifacts and prompt files only. "
            "If implementation details are missing, state them as assumptions or open questions."
        )

    sessions = load_sessions(project_root, feature)
    phase_sessions = sessions.setdefault("debate", {}).setdefault(phase, {})
    agent_sessions = {
        "claude": resolved_session_id(
            phase_sessions.get("claude"), session_policy, f"{feature}/{phase}/claude"
        ),
        "codex": resolved_session_id(
            phase_sessions.get("codex"), session_policy, f"{feature}/{phase}/codex"
        ),
    }

    history_entries: list[dict] = []
    log_entries: list[dict] = []
    outputs_by_round: dict[int, dict[str, str]] = {}
    scope_decision_artifact: Path | None = None
    history_summary: str | None = None
    summarized_up_to = -1

    effective_scope_policy = (
        scope_policy if config.get("scope_supported", False) else "off"
    )

    for round_num in range(rounds):
        round_root = phase_root / f"r{round_num}"
        ensure_dir(round_root)

        if round_num == 0:
            groom_prompt = assemble_prompt(
                config["groom"],
                {
                    "initial_prompt": initial_prompt,
                    "principles": principles,
                },
            )
            for agent in ("claude", "codex"):
                if agent == "claude":
                    result = run_claude_session(
                        groom_prompt,
                        cwd=project_root,
                        display_mode=display_mode,
                        session_id=agent_sessions[agent],
                        max_turns=10 if read_codebase else 1,
                        tools_enabled=read_codebase,
                    )
                else:
                    result = run_codex_session(
                        groom_prompt,
                        cwd=project_root,
                        display_mode=display_mode,
                        thread_id=agent_sessions[agent],
                        sandbox_mode="read-only",
                        full_auto=False,
                    )
                agent_sessions[agent] = result["session_id"] or agent_sessions[agent]
                phase_sessions[agent] = {
                    **native_session_payload(agent, agent_sessions[agent]),
                    "last_used_at": iso_now(),
                    "status": f"{phase}-round-{round_num}-groomed",
                }
                path = round_root / f"{agent}.{config['prefix']}.md"
                write_artifact(
                    path,
                    result["text"],
                    phase=phase,
                    round_num=round_num,
                    step="groom",
                    agent=agent.capitalize(),
                )
                outputs_by_round.setdefault(round_num, {})[agent] = result["text"]
                history_entries.append(
                    {
                        "round": round_num,
                        "step": "groom",
                        "agent": agent.capitalize(),
                        "content": result["text"].strip(),
                    }
                )
                append_log(
                    log_entries, round_num, "groom", agent.capitalize(), result["text"]
                )
            save_sessions(project_root, feature, sessions)

            if effective_scope_policy != "off":
                scope_constraints, scope_decision_artifact = resolve_scope_decisions(
                    project_root,
                    feature=feature,
                    phase=phase,
                    initial_prompt=initial_prompt,
                    claude_output=outputs_by_round[0]["claude"],
                    codex_output=outputs_by_round[0]["codex"],
                    scope_policy=effective_scope_policy,
                )
                if scope_constraints:
                    principles += "\n\n## Scope Decisions\n" + scope_constraints
            continue

        previous = outputs_by_round[round_num - 1]
        history_summary, summarized_up_to, history_entries = (
            summarize_history_if_needed(
                project_root,
                initial_prompt=initial_prompt,
                summary=history_summary,
                summarized_up_to=summarized_up_to,
                history_entries=history_entries,
            )
        )
        history = format_history_with_summary(
            history_entries, initial_prompt, history_summary, summarized_up_to
        )

        claude_critique_prompt = assemble_prompt(
            config["critique"],
            {
                "other_agent": "Codex",
                "other_plan": previous["codex"],
                "own_plan": previous["claude"],
                "principles": principles,
                "conversation_history": history,
            },
        )
        codex_critique_prompt = assemble_prompt(
            config["critique"],
            {
                "other_agent": "Claude",
                "other_plan": previous["claude"],
                "own_plan": previous["codex"],
                "principles": principles,
                "conversation_history": history,
            },
        )

        claude_critique = run_claude_session(
            claude_critique_prompt,
            cwd=project_root,
            display_mode=display_mode,
            session_id=agent_sessions["claude"],
            max_turns=10 if read_codebase else 1,
            tools_enabled=read_codebase,
        )
        codex_critique = run_codex_session(
            codex_critique_prompt,
            cwd=project_root,
            display_mode=display_mode,
            thread_id=agent_sessions["codex"],
            sandbox_mode="read-only",
            full_auto=False,
        )
        agent_sessions["claude"] = (
            claude_critique["session_id"] or agent_sessions["claude"]
        )
        agent_sessions["codex"] = (
            codex_critique["session_id"] or agent_sessions["codex"]
        )

        write_artifact(
            round_root / "claude.critiques_codex.md",
            claude_critique["text"],
            phase=phase,
            round_num=round_num,
            step="critique",
            agent="Claude",
        )
        write_artifact(
            round_root / "codex.critiques_claude.md",
            codex_critique["text"],
            phase=phase,
            round_num=round_num,
            step="critique",
            agent="Codex",
        )
        history_entries.append(
            {
                "round": round_num,
                "step": "critique",
                "agent": "Claude",
                "content": claude_critique["text"].strip(),
            }
        )
        history_entries.append(
            {
                "round": round_num,
                "step": "critique",
                "agent": "Codex",
                "content": codex_critique["text"].strip(),
            }
        )
        append_log(
            log_entries, round_num, "critique", "Claude", claude_critique["text"]
        )
        append_log(log_entries, round_num, "critique", "Codex", codex_critique["text"])

        revise_template = (
            config["revise_final"] if round_num == rounds - 1 else config["revise"]
        )
        history_summary, summarized_up_to, history_entries = (
            summarize_history_if_needed(
                project_root,
                initial_prompt=initial_prompt,
                summary=history_summary,
                summarized_up_to=summarized_up_to,
                history_entries=history_entries,
            )
        )
        history = format_history_with_summary(
            history_entries, initial_prompt, history_summary, summarized_up_to
        )

        claude_revise_prompt = assemble_prompt(
            revise_template,
            {
                "own_plan": previous["claude"],
                "feedback": codex_critique["text"],
                "feedback_source": "Codex",
                "principles": principles,
                "conversation_history": history,
            },
        )
        codex_revise_prompt = assemble_prompt(
            revise_template,
            {
                "own_plan": previous["codex"],
                "feedback": claude_critique["text"],
                "feedback_source": "Claude",
                "principles": principles,
                "conversation_history": history,
            },
        )

        claude_revised = run_claude_session(
            claude_revise_prompt,
            cwd=project_root,
            display_mode=display_mode,
            session_id=agent_sessions["claude"],
            max_turns=10 if read_codebase else 1,
            tools_enabled=read_codebase,
        )
        codex_revised = run_codex_session(
            codex_revise_prompt,
            cwd=project_root,
            display_mode=display_mode,
            thread_id=agent_sessions["codex"],
            sandbox_mode="read-only",
            full_auto=False,
        )
        agent_sessions["claude"] = (
            claude_revised["session_id"] or agent_sessions["claude"]
        )
        agent_sessions["codex"] = codex_revised["session_id"] or agent_sessions["codex"]

        write_artifact(
            round_root / f"claude.revised_{config['prefix']}.md",
            claude_revised["text"],
            phase=phase,
            round_num=round_num,
            step="revise",
            agent="Claude",
        )
        write_artifact(
            round_root / f"codex.revised_{config['prefix']}.md",
            codex_revised["text"],
            phase=phase,
            round_num=round_num,
            step="revise",
            agent="Codex",
        )
        outputs_by_round[round_num] = {
            "claude": claude_revised["text"],
            "codex": codex_revised["text"],
        }
        history_entries.append(
            {
                "round": round_num,
                "step": "revise",
                "agent": "Claude",
                "content": claude_revised["text"].strip(),
            }
        )
        history_entries.append(
            {
                "round": round_num,
                "step": "revise",
                "agent": "Codex",
                "content": codex_revised["text"].strip(),
            }
        )
        append_log(log_entries, round_num, "revise", "Claude", claude_revised["text"])
        append_log(log_entries, round_num, "revise", "Codex", codex_revised["text"])

        phase_sessions["claude"] = {
            **native_session_payload("claude", agent_sessions["claude"]),
            "last_used_at": iso_now(),
            "status": f"{phase}-round-{round_num}-revised",
        }
        phase_sessions["codex"] = {
            **native_session_payload("codex", agent_sessions["codex"]),
            "last_used_at": iso_now(),
            "status": f"{phase}-round-{round_num}-revised",
        }
        save_sessions(project_root, feature, sessions)

    if rounds == 1:
        outputs_by_round.setdefault(0, outputs_by_round.get(0, {}))

    save_debate_log(project_root, feature, phase, log_entries)
    final_round = rounds - 1
    claude_final = latest_phase_artifact(project_root, feature, phase, "claude")
    codex_final = latest_phase_artifact(project_root, feature, phase, "codex")
    summary_path = phase_root / f"{phase}_summary.md"
    write_text(
        summary_path,
        "\n".join(
            [
                f"# {phase.title()} Summary: {feature}",
                "",
                f"- Date: {iso_now()}",
                f"- Phase: {phase}",
                f"- Rounds completed: {rounds}",
                f"- Debate mode: {'groom only' if rounds == 1 else 'full debate'}",
                f"- Final Claude artifact: {claude_final}"
                if claude_final
                else "- Final Claude artifact: (missing)",
                f"- Final Codex artifact: {codex_final}"
                if codex_final
                else "- Final Codex artifact: (missing)",
                f"- Full debate log: {phase_root / 'debate.log.md'}",
                "",
                "## Next Steps",
                "- Review both final artifacts and the debate log",
                f"- Scope decisions: {scope_decision_artifact}"
                if scope_decision_artifact
                else "- Scope decisions: none",
                "- Choose one (or merge) to carry forward",
                "",
            ]
        ),
    )
    if history_summary:
        write_text(phase_root / "history_summary.md", history_summary + "\n")
    return summary_path


def orchestrator_cmd(project_root: Path, *args: str) -> list[str]:
    cmd = [sys.executable, str(ORCHESTRATOR), *args]
    if "--project-dir" not in args:
        cmd.extend(["--project-dir", str(project_root)])
    return cmd


def warn_if_feature_exists(project_root: Path, feature: str, *, force: bool) -> None:
    """Warn (and prompt if interactive) when re-running over an existing feature dir."""
    fdir = feature_dir(project_root, feature)
    if not fdir.is_dir():
        return

    # Look for signs of a previous run: any phase subdir or a run_state.json.
    prior_phases = [
        p.name
        for p in fdir.iterdir()
        if p.is_dir()
        and p.name in {"ideation", "plan", "generic", "implementation", "reviews"}
    ]
    has_state = (fdir / "run_state.json").exists() or (fdir / "sessions.json").exists()
    if not prior_phases and not has_state:
        return

    print()
    print(f"⚠  Feature '{feature}' already exists at {fdir}")
    if prior_phases:
        print(f"   Existing phases: {', '.join(sorted(prior_phases))}")
    if (fdir / "sessions.json").exists():
        print(
            "   Native sessions from a prior run will be reused (unless --session-policy=fresh)"
        )
    print("   Artifacts in the current run will OVERWRITE existing round files.")
    print(
        "   To keep the old results: use a different --feature slug, or move the dir aside:"
    )
    print(f"     mv {fdir} {fdir}.backup")
    print()

    if force or not stdin_is_tty():
        return

    try:
        answer = input("Continue and overwrite? [y/N] ").strip().lower()
    except EOFError:
        answer = ""
    if answer not in {"y", "yes"}:
        raise SystemExit("Aborted by user.")


def resolve_initial_prompt(args: argparse.Namespace) -> str:
    """Load the initial prompt from either --prompt (file) or --prompt-text (inline)."""
    inline = getattr(args, "prompt_text", None)
    if inline is not None:
        if not inline.strip():
            raise SystemExit("--prompt-text must not be empty")
        return inline
    prompt_path = Path(args.prompt).expanduser().resolve()
    if not prompt_path.exists():
        raise SystemExit(f"prompt file not found: {prompt_path}")
    return read_text(prompt_path)


def cmd_plan(args: argparse.Namespace) -> int:
    project_root = find_project_root(args.project_dir)
    validate_feature_slug(args.feature)
    initial_prompt = resolve_initial_prompt(args)
    warn_if_feature_exists(project_root, args.feature, force=args.force)
    if args.no_scope_check:
        args.scope_policy = "off"

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "plan",
            "status": "running",
            "session_mode": "native",
            "session_policy": args.session_policy,
            "scope_policy": args.scope_policy,
            "updated_at": iso_now(),
        },
    )

    ideation_summary = run_debate_phase_native(
        project_root,
        feature=args.feature,
        phase="ideation",
        initial_prompt=initial_prompt,
        rounds=args.rounds,
        session_policy=args.session_policy,
        scope_policy=args.scope_policy,
        read_codebase=args.read_codebase,
        display_mode=args.display_mode,
    )

    plan_input_path = latest_phase_artifact(
        project_root, args.feature, "ideation", "claude"
    )
    if plan_input_path is None:
        plan_input_path = latest_phase_artifact(
            project_root, args.feature, "ideation", "codex"
        )
    if plan_input_path is None:
        raise SystemExit("unable to locate ideation output for plan phase")

    plan_summary = run_debate_phase_native(
        project_root,
        feature=args.feature,
        phase="plan",
        initial_prompt=read_text(plan_input_path),
        rounds=args.rounds,
        session_policy=args.session_policy,
        scope_policy=args.scope_policy,
        read_codebase=args.read_codebase,
        display_mode=args.display_mode,
    )

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "plan",
            "status": "completed",
            "session_mode": "native",
            "session_policy": args.session_policy,
            "scope_policy": args.scope_policy,
            "updated_at": iso_now(),
            "artifacts": {
                "ideation_summary": str(ideation_summary),
                "plan_summary": str(plan_summary),
            },
        },
    )
    return 0


def cmd_generic(args: argparse.Namespace) -> int:
    project_root = find_project_root(args.project_dir)
    validate_feature_slug(args.feature)
    initial_prompt = resolve_initial_prompt(args)
    warn_if_feature_exists(project_root, args.feature, force=args.force)

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "generic",
            "status": "running",
            "session_mode": "native",
            "session_policy": args.session_policy,
            "updated_at": iso_now(),
        },
    )

    summary = run_debate_phase_native(
        project_root,
        feature=args.feature,
        phase="generic",
        initial_prompt=initial_prompt,
        rounds=args.rounds,
        session_policy=args.session_policy,
        scope_policy="off",
        read_codebase=args.read_codebase,
        display_mode=args.display_mode,
    )

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "generic",
            "status": "completed",
            "session_mode": "native",
            "session_policy": args.session_policy,
            "updated_at": iso_now(),
            "artifacts": {
                "generic_summary": str(summary),
            },
        },
    )
    return 0


def cmd_implement(args: argparse.Namespace) -> int:
    project_root = find_project_root(args.project_dir)
    validate_feature_slug(args.feature)
    implementer = ensure_agent(args.implementer, "implementer")
    sessions = load_sessions(project_root, args.feature)
    existing = sessions.get("implement", {}).get(implementer, {})
    existing_session_id = resolved_session_id(
        existing, args.session_policy, f"{args.feature}/implement/{implementer}"
    )

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "implement",
            "status": "running",
            "implementer": implementer,
            "session_mode": "native",
            "session_policy": args.session_policy,
            "updated_at": iso_now(),
        },
    )

    wt_path, plan, principles = prepare_implementation_context(
        project_root, args.feature, implementer
    )
    if existing_session_id:
        prompt = (
            f"You are continuing implementation for feature '{args.feature}'. "
            f"Resume work in this repository state, staying aligned with the approved plan and shared principles.\n\n"
            f"Approved plan:\n{plan}\n\nShared principles:\n{principles}"
        )
    else:
        prompt = assemble_prompt(
            "implement",
            {
                "plan": plan,
                "principles": principles,
                "feature": args.feature,
            },
        )

    result = run_agent_session(
        implementer,
        prompt,
        cwd=wt_path,
        display_mode="inline",
        session_id=existing_session_id,
        review_mode=False,
    )

    sessions.setdefault("implement", {})[implementer] = {
        "branch": branch_name(args.feature, implementer),
        "worktree": str(wt_path),
        "cwd": str(wt_path),
        **native_session_payload(implementer, result["session_id"]),
        "last_used_at": iso_now(),
        "status": "ready",
    }
    save_sessions(project_root, args.feature, sessions)

    impl_artifact = (
        feature_dir(project_root, args.feature)
        / "implementation"
        / f"{implementer}.log.md"
    )
    write_text(impl_artifact, result["text"].strip() + "\n")

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "implement",
            "status": "completed",
            "implementer": implementer,
            "session_mode": "native",
            "session_policy": args.session_policy,
            "updated_at": iso_now(),
            "worktree": str(wt_path),
            "branch": branch_name(args.feature, implementer),
            "native_session": native_session_payload(implementer, result["session_id"]),
            "artifact": str(impl_artifact),
        },
    )
    return 0


def latest_review_session(sessions: dict, reviewer: str, target: str) -> str | None:
    for entry in reversed(sessions.get("review", {}).get("passes", [])):
        if entry.get("reviewer") == reviewer and entry.get("target") == target:
            return native_session_id(entry.get("native_session"))
    return None


def run_review_pass(
    project_root: Path,
    *,
    feature: str,
    reviewer: str,
    target: str,
    pass_number: int,
    display_mode: str,
    session_policy: str,
) -> Path:
    wt_path = worktree_path(project_root, feature, target)
    if not wt_path.exists():
        raise SystemExit(f"target worktree does not exist: {wt_path}")

    prompt = assemble_prompt(
        "review",
        {
            "other_agent": target.capitalize(),
            "diff": get_worktree_diff(wt_path),
            "principles": load_principles(project_root, feature),
            "feature": feature,
        },
    )

    sessions = load_sessions(project_root, feature)
    reviewer_session_id = None
    if session_policy == "resume":
        reviewer_session_id = latest_review_session(sessions, reviewer, target)
        if not reviewer_session_id:
            raise SystemExit(
                f"no saved review session found for {feature}/review/{reviewer}->{target}"
            )
    elif session_policy == "auto":
        reviewer_session_id = latest_review_session(sessions, reviewer, target)

    result = run_agent_session(
        reviewer,
        prompt,
        cwd=wt_path,
        display_mode=display_mode,
        session_id=reviewer_session_id,
        review_mode=True,
    )
    resolved_reviewer_session_id = result["session_id"] or reviewer_session_id
    artifact = (
        feature_dir(project_root, feature)
        / "reviews"
        / f"pass-{pass_number}.{reviewer}.reviews_{target}.md"
    )
    write_text(artifact, result["text"].strip() + "\n")

    sessions.setdefault("review", {}).setdefault("passes", []).append(
        {
            "pass": pass_number,
            "reviewer": reviewer,
            "target": target,
            "artifact": str(artifact),
            "created_at": iso_now(),
            "display_mode": display_mode,
            "native_session": native_session_payload(
                reviewer, resolved_reviewer_session_id
            ),
        }
    )
    save_sessions(project_root, feature, sessions)
    return artifact


def apply_review_feedback(
    project_root: Path,
    *,
    feature: str,
    implementer: str,
    reviewer: str,
    review_artifact: Path,
    pass_number: int,
    display_mode: str,
    session_policy: str,
) -> Path:
    wt_path = worktree_path(project_root, feature, implementer)
    if not wt_path.exists():
        raise SystemExit(f"implementer worktree does not exist: {wt_path}")

    plan_path = latest_plan_file(project_root, feature, implementer)
    if plan_path is None:
        raise SystemExit(f"no {implementer} plan artifact found for feature {feature}")

    prompt = assemble_prompt(
        "apply_review",
        {
            "feature": feature,
            "principles": load_principles(project_root, feature),
            "plan": read_text(plan_path),
            "review": read_text(review_artifact),
            "reviewer": reviewer.capitalize(),
        },
    )

    sessions = load_sessions(project_root, feature)
    existing = sessions.get("implement", {}).get(implementer, {})
    existing_session_id = resolved_session_id(
        existing, session_policy, f"{feature}/implement/{implementer}"
    )
    result = run_agent_session(
        implementer,
        prompt,
        cwd=wt_path,
        display_mode=display_mode,
        session_id=existing_session_id,
        review_mode=False,
    )
    resolved_implementer_session_id = result["session_id"] or existing_session_id
    artifact = (
        feature_dir(project_root, feature)
        / "implementation"
        / f"pass-{pass_number}.{implementer}.applies_review.md"
    )
    write_text(artifact, result["text"].strip() + "\n")

    sessions.setdefault("implement", {})[implementer] = {
        "branch": branch_name(feature, implementer),
        "worktree": str(wt_path),
        "cwd": str(wt_path),
        **native_session_payload(implementer, resolved_implementer_session_id),
        "last_used_at": iso_now(),
        "status": "review-applied",
        "last_review_artifact": str(review_artifact),
    }
    save_sessions(project_root, feature, sessions)
    return artifact


def cmd_review(args: argparse.Namespace) -> int:
    project_root = find_project_root(args.project_dir)
    validate_feature_slug(args.feature)
    reviewer = ensure_agent(args.reviewer, "reviewer")
    target = ensure_agent(args.target, "target")
    if reviewer == target:
        raise SystemExit("reviewer and target must be different agents")

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "review",
            "status": "running",
            "reviewer": reviewer,
            "target": target,
            "current_pass": args.pass_number,
            "session_mode": "native",
            "session_policy": args.session_policy,
            "updated_at": iso_now(),
        },
    )

    artifact = run_review_pass(
        project_root,
        feature=args.feature,
        reviewer=reviewer,
        target=target,
        pass_number=args.pass_number,
        display_mode=args.display_mode,
        session_policy=args.session_policy,
    )

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "review",
            "status": "completed",
            "reviewer": reviewer,
            "target": target,
            "current_pass": args.pass_number,
            "session_mode": "native",
            "session_policy": args.session_policy,
            "updated_at": iso_now(),
            "artifact": str(artifact),
        },
    )
    print(f"Review artifact: {artifact}")
    return 0


def cmd_loop(args: argparse.Namespace) -> int:
    project_root = find_project_root(args.project_dir)
    validate_feature_slug(args.feature)
    implementer = ensure_agent(args.implementer, "implementer")
    reviewer = ensure_agent(args.reviewer, "reviewer")
    if implementer == reviewer:
        raise SystemExit("implementer and reviewer must be different agents")
    if args.passes < 1:
        raise SystemExit("--passes must be >= 1")

    wt_path = worktree_path(project_root, args.feature, implementer)
    if not wt_path.exists():
        cmd_implement(
            argparse.Namespace(
                feature=args.feature,
                implementer=implementer,
                session_policy=args.implementer_session_policy,
                project_dir=str(project_root),
            )
        )
    elif args.implementer_session_policy == "resume":
        sessions = load_sessions(project_root, args.feature)
        existing = sessions.get("implement", {}).get(implementer, {})
        resolved_session_id(
            existing, "resume", f"{args.feature}/implement/{implementer}"
        )

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "loop",
            "status": "running",
            "implementer": implementer,
            "reviewer": reviewer,
            "current_pass": 1,
            "max_passes": args.passes,
            "display_mode": args.display_mode,
            "session_mode": "native",
            "implementer_session_policy": args.implementer_session_policy,
            "reviewer_session_policy": args.reviewer_session_policy,
            "updated_at": iso_now(),
        },
    )

    latest_review = None
    for pass_number in range(1, args.passes + 1):
        print(f"\n=== Review pass {pass_number}/{args.passes} ===")
        latest_review = run_review_pass(
            project_root,
            feature=args.feature,
            reviewer=reviewer,
            target=implementer,
            pass_number=pass_number,
            display_mode=args.display_mode,
            session_policy=args.reviewer_session_policy if pass_number == 1 else "auto",
        )
        save_run_state(
            project_root,
            args.feature,
            {
                "feature": args.feature,
                "phase": "loop",
                "status": "running",
                "implementer": implementer,
                "reviewer": reviewer,
                "current_pass": pass_number,
                "max_passes": args.passes,
                "display_mode": args.display_mode,
                "last_review_artifact": str(latest_review),
                "session_mode": "native",
                "implementer_session_policy": args.implementer_session_policy,
                "reviewer_session_policy": args.reviewer_session_policy,
                "updated_at": iso_now(),
            },
        )

        if pass_number == args.passes:
            break

        print(f"\n=== Applying review feedback before pass {pass_number + 1} ===")
        apply_review_feedback(
            project_root,
            feature=args.feature,
            implementer=implementer,
            reviewer=reviewer,
            review_artifact=latest_review,
            pass_number=pass_number,
            display_mode=args.display_mode,
            session_policy=args.implementer_session_policy
            if pass_number == 1
            else "auto",
        )

    save_run_state(
        project_root,
        args.feature,
        {
            "feature": args.feature,
            "phase": "loop",
            "status": "completed",
            "implementer": implementer,
            "reviewer": reviewer,
            "current_pass": args.passes,
            "max_passes": args.passes,
            "display_mode": args.display_mode,
            "last_review_artifact": str(latest_review) if latest_review else None,
            "updated_at": iso_now(),
            "session_mode": "native",
            "implementer_session_policy": args.implementer_session_policy,
            "reviewer_session_policy": args.reviewer_session_policy,
        },
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    project_root = find_project_root(args.project_dir)
    validate_feature_slug(args.feature)
    feature_root = feature_dir(project_root, args.feature)
    state = load_json(run_state_path(project_root, args.feature), {})
    sessions = load_sessions(project_root, args.feature)

    latest_review = None
    reviews_dir = feature_root / "reviews"
    if reviews_dir.exists():
        review_files = sorted(
            reviews_dir.glob("*.md"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if review_files:
            latest_review = str(review_files[0])

    summary = {
        "feature": args.feature,
        "project_root": str(project_root),
        "feature_dir": str(feature_root),
        "run_state": state,
        "sessions": sessions,
        "worktrees": {
            agent: {
                "path": str(worktree_path(project_root, args.feature, agent)),
                "exists": worktree_path(project_root, args.feature, agent).exists(),
                "branch": branch_name(args.feature, agent),
            }
            for agent in sorted(AGENTS)
        },
        "latest_review_artifact": latest_review,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Claude-native wrapper around CrossAI workflows."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generic = subparsers.add_parser("generic", help="Run standalone cross-verification")
    generic.add_argument("--feature", required=True)
    generic_prompt = generic.add_mutually_exclusive_group(required=True)
    generic_prompt.add_argument("--prompt", help="Path to a prompt file")
    generic_prompt.add_argument(
        "--prompt-text", help="Inline prompt text (alternative to --prompt)"
    )
    generic.add_argument("--rounds", type=int, default=3)
    generic.add_argument("--session-policy", choices=SESSION_POLICIES, default="auto")
    generic.add_argument("--read-codebase", action="store_true")
    generic.add_argument("--display-mode", choices=["inline", "tmux"], default="inline")
    generic.add_argument(
        "--force", "-f", action="store_true", help="Skip overwrite confirmation"
    )
    generic.add_argument("--project-dir")
    generic.set_defaults(func=cmd_generic)

    plan = subparsers.add_parser("plan", help="Run ideation and planning")
    plan.add_argument("--feature", required=True)
    plan_prompt = plan.add_mutually_exclusive_group(required=True)
    plan_prompt.add_argument("--prompt", help="Path to a prompt file")
    plan_prompt.add_argument(
        "--prompt-text", help="Inline prompt text (alternative to --prompt)"
    )
    plan.add_argument("--rounds", type=int, default=3)
    plan.add_argument("--session-policy", choices=SESSION_POLICIES, default="auto")
    plan.add_argument("--scope-policy", choices=SCOPE_POLICIES, default="adjudicate")
    plan.add_argument("--read-codebase", action="store_true")
    plan.add_argument("--no-scope-check", action="store_true")
    plan.add_argument("--display-mode", choices=["inline", "tmux"], default="inline")
    plan.add_argument(
        "--force", "-f", action="store_true", help="Skip overwrite confirmation"
    )
    plan.add_argument("--project-dir")
    plan.set_defaults(func=cmd_plan)

    implement = subparsers.add_parser(
        "implement", help="Run implementation in a worktree"
    )
    implement.add_argument("--feature", required=True)
    implement.add_argument("--implementer", default="claude", choices=sorted(AGENTS))
    implement.add_argument("--session-policy", choices=SESSION_POLICIES, default="auto")
    implement.add_argument("--project-dir")
    implement.set_defaults(func=cmd_implement)

    review = subparsers.add_parser("review", help="Run a single review pass")
    review.add_argument("--feature", required=True)
    review.add_argument("--reviewer", default="codex", choices=sorted(AGENTS))
    review.add_argument("--target", default="claude", choices=sorted(AGENTS))
    review.add_argument("--pass-number", type=int, default=1)
    review.add_argument("--session-policy", choices=SESSION_POLICIES, default="fresh")
    review.add_argument("--display-mode", choices=["inline", "tmux"], default="inline")
    review.add_argument("--project-dir")
    review.set_defaults(func=cmd_review)

    loop = subparsers.add_parser("loop", help="Run implementation-review-fix passes")
    loop.add_argument("--feature", required=True)
    loop.add_argument("--implementer", default="claude", choices=sorted(AGENTS))
    loop.add_argument("--reviewer", default="codex", choices=sorted(AGENTS))
    loop.add_argument("--passes", type=int, default=3)
    loop.add_argument(
        "--implementer-session-policy", choices=SESSION_POLICIES, default="auto"
    )
    loop.add_argument(
        "--reviewer-session-policy", choices=SESSION_POLICIES, default="fresh"
    )
    loop.add_argument("--display-mode", choices=["inline", "tmux"], default="inline")
    loop.add_argument("--project-dir")
    loop.set_defaults(func=cmd_loop)

    status = subparsers.add_parser("status", help="Inspect CrossAI state for a feature")
    status.add_argument("--feature", required=True)
    status.add_argument("--project-dir")
    status.set_defaults(func=cmd_status)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except (CrossAIError, OutputParseError, subprocess.CalledProcessError) as exc:
        if hasattr(args, "feature") and FEATURE_SLUG_RE.fullmatch(args.feature or ""):
            try:
                project_root = find_project_root(getattr(args, "project_dir", None))
                prior_state = load_json(run_state_path(project_root, args.feature), {})
                save_run_state(
                    project_root,
                    args.feature,
                    {
                        **prior_state,
                        "feature": args.feature,
                        "phase": prior_state.get(
                            "phase", getattr(args, "command", "unknown")
                        ),
                        "status": "failed",
                        "error": str(exc),
                        "updated_at": iso_now(),
                    },
                )
            except Exception:
                pass
        if isinstance(exc, subprocess.CalledProcessError):
            details = (exc.output or "").strip()
            message = f"command failed: {quote_cmd(list(exc.cmd))}"
            if details:
                message += f"\n{details}"
            print(message, file=sys.stderr)
            return 1
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
