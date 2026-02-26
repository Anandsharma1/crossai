#!/usr/bin/env python3
"""
CrossAI v2
Automates the "ideation → plan → implement → review" pipeline
between Claude Code CLI and Codex CLI.

Usage:
    python orchestrate.py --feature "feat" --prompt idea.md --phase ideation
    python orchestrate.py --feature "feat" --phase plan --rounds 3
    python orchestrate.py --feature "feat" --phase implement --both
    python orchestrate.py --feature "feat" --phase review
"""

import argparse
import re
import subprocess
import sys
import textwrap
import time
from datetime import datetime
from pathlib import Path
from enum import Enum

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_CROSSAI_DIRNAME = ".crossai"
CROSSAI_DIR: Path = Path(_CROSSAI_DIRNAME)  # Resolved to absolute path in main()
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# Project root markers (checked in order; first match wins)
_PROJECT_MARKERS = [".git", ".vscode", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"]

CLAUDE_CMD = "claude"
CODEX_CMD = "codex"

CLAUDE_TIMEOUT = 300
CODEX_TIMEOUT = 300
MAX_RETRIES = 2
HISTORY_CHAR_LIMIT = 80_000  # Summarize older rounds when history exceeds this

# Phase chain: each phase knows which previous phase to read from
PHASE_CHAIN = {
    "ideation": {"prev": None,       "prefix": "direction", "groom": "ideation",  "critique": "ideation_critique",  "revise": "ideation_revise",  "revise_final": "ideation_revise_final"},
    "plan":     {"prev": "ideation",  "prefix": "plan",      "groom": "groom",     "critique": "critique",           "revise": "revise",           "revise_final": "revise_final"},
}


class Agent(str, Enum):
    CLAUDE = "claude"
    CODEX = "codex"


class CLITimeoutError(Exception):
    """Raised when a CLI call fails after all retries are exhausted."""
    pass


# ---------------------------------------------------------------------------
# Conversation History
# ---------------------------------------------------------------------------

class ConversationHistory:
    """Accumulates debate entries and formats them for prompt injection.

    Always preserves the initial prompt. Older rounds get summarized when
    the total character count exceeds HISTORY_CHAR_LIMIT.
    """

    def __init__(self, initial_prompt: str):
        self.initial_prompt = initial_prompt
        self.entries: list[dict] = []  # {round, step, agent, content}
        self._summary: str | None = None  # Cached summary of older rounds
        self._summarized_up_to: int = -1  # Last round included in summary

    def add(self, round_num: int, step: str, agent: str, content: str):
        self.entries.append({
            "round": round_num, "step": step, "agent": agent, "content": content,
        })

    def format(self) -> str:
        """Return the full conversation history formatted for prompt injection."""
        parts = [f"### Initial Prompt\n{self.initial_prompt}"]

        if self._summary:
            parts.append(f"### Summary of Earlier Rounds (up to round {self._summarized_up_to})\n{self._summary}")

        for entry in self._unsummarized_entries():
            header = f"### Round {entry['round']} — {entry['step']} ({entry['agent']})"
            parts.append(f"{header}\n{entry['content']}")

        return "\n\n---\n\n".join(parts)

    def char_count(self) -> int:
        return len(self.format())

    def needs_summarization(self) -> bool:
        return self.char_count() > HISTORY_CHAR_LIMIT and len(self.entries) > 2

    def summarize_older_rounds(self):
        """Summarize all but the latest round's entries using Claude."""
        if not self.entries:
            return
        latest_round = max(e["round"] for e in self.entries)
        older = [e for e in self.entries if e["round"] < latest_round]
        if not older:
            return

        to_summarize_parts = []
        if self._summary:
            to_summarize_parts.append(f"Previous summary:\n{self._summary}")
        for entry in older:
            if entry["round"] > self._summarized_up_to:
                to_summarize_parts.append(
                    f"Round {entry['round']} — {entry['step']} ({entry['agent']}):\n{entry['content']}"
                )

        if not to_summarize_parts:
            return

        to_summarize = "\n\n---\n\n".join(to_summarize_parts)
        prompt = (
            "Summarize the following debate history concisely. Preserve key decisions, "
            "agreements, disagreements, and open questions. Keep it under 2000 words.\n\n"
            f"{to_summarize}"
        )
        print("  📝 Summarizing conversation history (exceeds size limit)...")
        try:
            self._summary = run_claude(prompt, timeout=120)
            self._summarized_up_to = max(e["round"] for e in older)
            # Remove summarized entries from the list
            self.entries = [e for e in self.entries if e["round"] >= latest_round]
        except (CLITimeoutError, KeyboardInterrupt):
            print("  ⚠ History summarization failed, sending full history.")

    def _unsummarized_entries(self) -> list[dict]:
        return [e for e in self.entries if e["round"] > self._summarized_up_to]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def feature_dir(feature: str) -> Path:
    return CROSSAI_DIR / feature

def phase_dir(feature: str, phase: str) -> Path:
    return feature_dir(feature) / phase

def round_dir(feature: str, phase: str, round_num: int) -> Path:
    return phase_dir(feature, phase) / f"r{round_num}"

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")

def write_file(path: Path, content: str):
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")
    print(f"  ✓ Written: {path}")

def write_artifact(path: Path, content: str, *, phase: str, round_num: int, step: str, agent: str):
    """Write an artifact file with a metadata header."""
    header = (
        f"<!-- CrossAI | phase: {phase} | round: {round_num} | step: {step} "
        f"| agent: {agent} | timestamp: {timestamp()} -->\n\n"
    )
    write_file(path, header + content)

def load_prompt_template(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        print(f"  ⚠ Prompt template not found: {path}")
        sys.exit(1)
    return read_file(path)

def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Debate Log
# ---------------------------------------------------------------------------

class DebateLog:
    """Records all interactions chronologically for a phase."""

    def __init__(self, feature: str, phase: str):
        self.entries = []
        self.feature = feature
        self.phase = phase
        self.start_time = timestamp()

    def record(self, round_num: int, step: str, agent: str, content: str):
        self.entries.append({
            "timestamp": timestamp(),
            "round": round_num,
            "step": step,
            "agent": agent,
            "content": content,
        })

    def save(self):
        pdir = phase_dir(self.feature, self.phase)
        lines = [
            f"# CrossAI Debate Log: {self.feature} ({self.phase})",
            f"",
            f"- Started: {self.start_time}",
            f"- Finished: {timestamp()}",
            f"- Rounds: {max((e['round'] for e in self.entries), default=0) + 1}",
            f"- Total interactions: {len(self.entries)}",
            f"",
            f"---",
            f"",
        ]
        for entry in self.entries:
            lines.append(f"## Round {entry['round']} — {entry['step']} ({entry['agent']})")
            lines.append(f"*{entry['timestamp']}*")
            lines.append(f"")
            lines.append(entry["content"])
            lines.append(f"")
            lines.append(f"---")
            lines.append(f"")
        write_file(pdir / "debate.log.md", "\n".join(lines))


# ---------------------------------------------------------------------------
# CLI Runners
# ---------------------------------------------------------------------------

def run_claude(prompt: str, timeout: int = CLAUDE_TIMEOUT) -> str:
    cmd = [CLAUDE_CMD, "-p", "--output-format", "text", "--max-turns", "6", prompt]
    return _run_cli(cmd, "Claude", timeout)

def run_claude_with_edits(prompt: str, cwd: str = None, timeout: int = CLAUDE_TIMEOUT) -> str:
    cmd = [CLAUDE_CMD, "-p", "--output-format", "text", "--max-turns", "20", prompt]
    return _run_cli(cmd, "Claude (edits)", timeout, cwd=cwd)

def run_codex(prompt: str, timeout: int = CODEX_TIMEOUT) -> str:
    cmd = [CODEX_CMD, "exec", prompt]
    return _run_cli(cmd, "Codex", timeout)

def run_codex_with_edits(prompt: str, cwd: str = None, timeout: int = CODEX_TIMEOUT) -> str:
    cmd = [CODEX_CMD, "exec", "--full-auto", prompt]
    return _run_cli(cmd, "Codex (edits)", timeout, cwd=cwd)

def _run_cli(cmd: list, label: str, timeout: int, cwd: str = None, retries: int = MAX_RETRIES) -> str:
    for attempt in range(1, retries + 1):
        print(f"  ⏳ Running {label}..." + (f" (attempt {attempt}/{retries})" if attempt > 1 else ""))
        start = time.time()
        proc = None
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd)
            stdout, stderr = proc.communicate(timeout=timeout)
            elapsed = time.time() - start
            print(f"  ✓ {label} completed in {elapsed:.1f}s")
            if proc.returncode != 0:
                print(f"  ⚠ {label} stderr: {stderr[:500]}")
            output = stdout.strip()
            if not output:
                output = f"[{label} produced no output. stderr: {stderr[:300]}]"
            return output
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
                proc.wait()
            if attempt < retries:
                print(f"  ✗ {label} timed out after {timeout}s. Retrying...")
            else:
                print(f"  ✗ {label} timed out after {timeout}s. All {retries} attempts exhausted.")
                raise CLITimeoutError(f"{label} timed out after {retries} attempts ({timeout}s each)")
        except KeyboardInterrupt:
            if proc:
                proc.kill()
                proc.wait()
            print(f"\n  ✗ {label} interrupted by user.")
            raise
        except FileNotFoundError:
            print(f"  ✗ {label} CLI not found. Is '{cmd[0]}' installed and on PATH?")
            sys.exit(1)


# ---------------------------------------------------------------------------
# Prompt Assembly
# ---------------------------------------------------------------------------

def assemble_prompt(template_name: str, variables: dict) -> str:
    template = load_prompt_template(template_name)
    for key, value in variables.items():
        template = template.replace(f"{{{{{key}}}}}", str(value))
    return template

def get_principles(feature: str) -> str:
    # Feature-specific override (inside artifact dir)
    feature_principles = feature_dir(feature) / "principles.md"
    if feature_principles.exists():
        return read_file(feature_principles)
    # Project-level principles (in artifact dir root)
    project_principles = CROSSAI_DIR / "principles.md"
    if project_principles.exists():
        return read_file(project_principles)
    # Installation-level principles (where orchestrate.py lives: ~/.crossai/ or cross_ai/)
    install_principles = Path(__file__).resolve().parent / "principles.md"
    if install_principles.exists():
        return read_file(install_principles)
    return "(No shared principles defined.)"


# ---------------------------------------------------------------------------
# Scope Check
# ---------------------------------------------------------------------------

def _scope_check(initial_prompt: str, claude_output: str, codex_output: str) -> str | None:
    """Analyze both agents' outputs for scope creep, ask user to confirm.

    Returns a string of exclusions to inject into principles, or None.
    The user can enter numbers (e.g. "1,3"), "all", or mix numbers with
    free text (e.g. "1, 3 and also exclude stored procedure scanning").
    """
    print(f"\n{'='*60}")
    print("SCOPE CHECK: Analyzing outputs for scope deviations...")
    print(f"{'='*60}")

    prompt = assemble_prompt("scope_check", {
        "initial_prompt": initial_prompt,
        "claude_output": claude_output,
        "codex_output": codex_output,
    })

    try:
        result = run_claude(prompt, timeout=120)
    except (CLITimeoutError, KeyboardInterrupt):
        print("  ⚠ Scope check failed. Continuing without scope guard.")
        return None

    if "NO_SCOPE_ISSUES" in result:
        print("\n  ✓ No significant scope deviations detected.\n")
        return None

    print(f"\n{result}\n")
    print(f"{'='*60}")
    print("Which items (if any) should be EXCLUDED from scope?")
    print("  - Enter numbers: 1,3")
    print("  - Or numbers + free text: 1, 3 and also exclude stored procedures")
    print("  - Or 'all' to exclude everything listed")
    print("  - Or just free text: exclude runtime log analysis")
    print("  - Press Enter to accept all (nothing excluded)")
    print(f"{'='*60}")

    try:
        answer = input("\nExclude: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  Skipping scope check.")
        return None

    if not answer:
        print("  ✓ All scope items accepted. Proceeding.")
        return None

    # Parse the scope check output to extract numbered items
    items = _parse_numbered_items(result)

    # Parse user input: extract numbers and any remaining free text
    excluded_items = []
    free_text = None

    if answer.lower() == "all":
        excluded_items = [items[n] for n in sorted(items.keys())]
    else:
        # Extract all numbers from the input
        numbers_found = set()
        remaining_parts = []
        # Split on commas first, then process each part
        for part in answer.split(","):
            part = part.strip()
            if not part:
                continue
            # Check if this part starts with a number
            match = re.match(r'^(\d+)\s*(.*)', part)
            if match:
                numbers_found.add(int(match.group(1)))
                leftover = match.group(2).strip()
                if leftover:
                    remaining_parts.append(leftover)
            else:
                remaining_parts.append(part)

        # Collect excluded items by number
        for n in sorted(numbers_found):
            if n in items:
                excluded_items.append(items[n])

        # Join remaining text, clean up connectors
        if remaining_parts:
            free_text = " ".join(remaining_parts)
            # Strip leading connectors like "and", "also", "and also"
            free_text = re.sub(r'^(and\s+also|and|also|plus)\s+', '', free_text, flags=re.IGNORECASE).strip()

    if not excluded_items and not free_text:
        print("  ✓ No valid items selected. Proceeding.")
        return None

    # Build exclusion text
    exclusion_lines = []
    for item in excluded_items:
        exclusion_lines.append(f"- {item}")
    if free_text:
        exclusion_lines.append(f"- {free_text}")

    exclusions = "\n".join(exclusion_lines)
    count = len(excluded_items) + (1 if free_text else 0)

    print(f"\n  ✓ Excluding {count} scope item(s):")
    for line in exclusion_lines:
        print(f"    {line}")
    print("  These will be injected as constraints for subsequent rounds.")
    return exclusions


def _parse_numbered_items(text: str) -> dict[int, str]:
    """Extract numbered items (e.g. '1. **Foo** — bar') from scope check output."""
    items = {}
    current_num = None
    current_text = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and stripped[0].isdigit() and "." in stripped.split()[0]:
            if current_num is not None:
                items[current_num] = " ".join(current_text)
            try:
                current_num = int(stripped.split(".")[0])
            except ValueError:
                continue
            current_text = [stripped.split(".", 1)[1].strip() if "." in stripped else stripped]
        elif current_num is not None and stripped:
            current_text.append(stripped)
    if current_num is not None:
        items[current_num] = " ".join(current_text)
    return items


# ---------------------------------------------------------------------------
# Generic Debate Loop (used by ideation, plan)
# ---------------------------------------------------------------------------

def run_debate(feature: str, phase_name: str, initial_prompt: str,
               groom_template: str, critique_template: str, revise_template: str,
               max_rounds: int = 3, artifact_prefix: str = "plan",
               scope_check: bool = True, revise_final_template: str | None = None,
               read_codebase: bool = False):
    pdir = phase_dir(feature, phase_name)
    ensure_dir(pdir)

    principles = get_principles(feature)

    if not read_codebase:
        principles += (
            "\n\n## Codebase Access — RESTRICTED\n"
            "Do NOT read, browse, or analyze any project source code files or directories. "
            "This includes application code, tests, configs, scripts, and similar — "
            "but does NOT restrict reading .crossai/ artifacts or prompt files. "
            "Work exclusively from the information provided in this prompt and the shared principles. "
            "If you need information about the existing codebase, state it as an assumption or open question."
        )

    log = DebateLog(feature, phase_name)
    history = ConversationHistory(initial_prompt)
    rounds_completed = 0

    write_file(pdir / "initial_prompt.md", initial_prompt)

    print(f"\n{'='*60}")
    print(f"{phase_name.upper()}: {feature}")
    print(f"Rounds: {max_rounds} (groom + {max_rounds - 1} critique/revise)")
    print(f"{'='*60}")

    try:
        # --- Round 0: Groom ---
        print(f"\n--- Round 0: Groom [{timestamp()}] ---")
        rdir = round_dir(feature, phase_name, 0)

        groom_prompt = assemble_prompt(groom_template, {
            "initial_prompt": initial_prompt,
            "principles": principles,
        })

        claude_output = run_claude(groom_prompt)
        write_artifact(rdir / f"claude.{artifact_prefix}.md", claude_output,
                       phase=phase_name, round_num=0, step="groom", agent="Claude")
        log.record(0, "groom", "Claude", claude_output)
        history.add(0, "groom", "Claude", claude_output)

        codex_output = run_codex(groom_prompt)
        write_artifact(rdir / f"codex.{artifact_prefix}.md", codex_output,
                       phase=phase_name, round_num=0, step="groom", agent="Codex")
        log.record(0, "groom", "Codex", codex_output)
        history.add(0, "groom", "Codex", codex_output)

        rounds_completed = 1

        # --- Scope check after round 0 ---
        if scope_check:
            exclusions = _scope_check(initial_prompt, claude_output, codex_output)
            if exclusions:
                principles = principles + "\n\n## Scope Exclusions (confirmed by user)\n" + exclusions

        # --- Rounds 1..N: Critique + Revise ---
        for r in range(1, max_rounds):
            # Summarize history if it's getting too large
            if history.needs_summarization():
                history.summarize_older_rounds()

            print(f"\n--- Round {r}: Cross-Critique [{timestamp()}] ---")
            rdir = round_dir(feature, phase_name, r)

            prev_rdir = round_dir(feature, phase_name, r - 1)
            if r == 1:
                latest_claude = read_file(prev_rdir / f"claude.{artifact_prefix}.md")
                latest_codex = read_file(prev_rdir / f"codex.{artifact_prefix}.md")
            else:
                latest_claude = read_file(prev_rdir / f"claude.revised_{artifact_prefix}.md")
                latest_codex = read_file(prev_rdir / f"codex.revised_{artifact_prefix}.md")

            conversation_history = history.format()

            critique_prompt_claude = assemble_prompt(critique_template, {
                "other_agent": "Codex", "other_plan": latest_codex,
                "own_plan": latest_claude, "principles": principles,
                "conversation_history": conversation_history,
            })
            claude_critique = run_claude(critique_prompt_claude)
            write_artifact(rdir / "claude.critiques_codex.md", claude_critique,
                           phase=phase_name, round_num=r, step="critique", agent="Claude")
            log.record(r, "critique", "Claude (critiquing Codex)", claude_critique)
            history.add(r, "critique", "Claude", claude_critique)

            critique_prompt_codex = assemble_prompt(critique_template, {
                "other_agent": "Claude", "other_plan": latest_claude,
                "own_plan": latest_codex, "principles": principles,
                "conversation_history": conversation_history,
            })
            codex_critique = run_codex(critique_prompt_codex)
            write_artifact(rdir / "codex.critiques_claude.md", codex_critique,
                           phase=phase_name, round_num=r, step="critique", agent="Codex")
            log.record(r, "critique", "Codex (critiquing Claude)", codex_critique)
            history.add(r, "critique", "Codex", codex_critique)

            is_final_round = (r == max_rounds - 1)
            active_revise = revise_final_template if (is_final_round and revise_final_template) else revise_template
            label = "Final Revise" if is_final_round else "Revise"
            print(f"\n--- Round {r}: {label} [{timestamp()}] ---")

            # Re-format history after critiques were added
            conversation_history = history.format()

            revise_prompt_claude = assemble_prompt(active_revise, {
                "own_plan": latest_claude, "feedback": codex_critique,
                "feedback_source": "Codex", "principles": principles,
                "conversation_history": conversation_history,
            })
            claude_revised = run_claude(revise_prompt_claude)
            write_artifact(rdir / f"claude.revised_{artifact_prefix}.md", claude_revised,
                           phase=phase_name, round_num=r, step="revise", agent="Claude")
            log.record(r, "revise", "Claude", claude_revised)
            history.add(r, "revise", "Claude", claude_revised)

            revise_prompt_codex = assemble_prompt(active_revise, {
                "own_plan": latest_codex, "feedback": claude_critique,
                "feedback_source": "Claude", "principles": principles,
                "conversation_history": conversation_history,
            })
            codex_revised = run_codex(revise_prompt_codex)
            write_artifact(rdir / f"codex.revised_{artifact_prefix}.md", codex_revised,
                           phase=phase_name, round_num=r, step="revise", agent="Codex")
            log.record(r, "revise", "Codex", codex_revised)
            history.add(r, "revise", "Codex", codex_revised)

            rounds_completed = r + 1

    except CLITimeoutError as e:
        log.save()
        print(f"\n{'='*60}")
        print(f"✗ {phase_name.title()} ABORTED: {e}")
        print(f"  Rounds completed before failure: {rounds_completed}/{max_rounds}")
        print(f"  Partial artifacts saved in: {pdir}/")
        print(f"  Debate log: {pdir}/debate.log.md")
        print(f"{'='*60}")
        sys.exit(1)

    log.save()

    final_round = max_rounds - 1
    final_rdir = round_dir(feature, phase_name, final_round)
    summary = f"""# {phase_name.title()} Summary: {feature}

- Date: {timestamp()}
- Phase: {phase_name}
- Rounds completed: {max_rounds}
- Final Claude {artifact_prefix}: {final_rdir}/claude.revised_{artifact_prefix}.md
- Final Codex {artifact_prefix}: {final_rdir}/codex.revised_{artifact_prefix}.md
- Full debate log: {pdir}/debate.log.md

## Next Steps
- Review both final artifacts and the debate log
- Choose one (or merge) to carry forward
"""
    write_file(pdir / f"{phase_name}_summary.md", summary)

    print(f"\n{'='*60}")
    print(f"✓ {phase_name.title()} complete. Artifacts in: {pdir}/")
    print(f"  Debate log: {pdir}/debate.log.md")
    print(f"{'='*60}")


# ---------------------------------------------------------------------------
# Phase runners: ideation, plan
# ---------------------------------------------------------------------------

def run_debate_phase(feature: str, phase_name: str, explicit_prompt: str = None,
                     max_rounds: int = 3, scope_check: bool = True,
                     read_codebase: bool = False):
    """Run any debate phase, auto-chaining from previous phase if no prompt given."""
    config = PHASE_CHAIN[phase_name]
    initial_prompt = explicit_prompt

    if initial_prompt is None and config["prev"] is not None:
        # Auto-chain: read output from previous phase
        prev_phase = config["prev"]
        prev_prefix = PHASE_CHAIN[prev_phase]["prefix"]
        latest_round = _find_latest_round_in_phase(feature, prev_phase)

        if latest_round is not None:
            rdir = round_dir(feature, prev_phase, latest_round)
            for candidate in [
                rdir / f"claude.revised_{prev_prefix}.md",
                rdir / f"codex.revised_{prev_prefix}.md",
                round_dir(feature, prev_phase, 0) / f"claude.{prev_prefix}.md",
            ]:
                if candidate.exists():
                    initial_prompt = read_file(candidate)
                    print(f"  Auto-chaining from {prev_phase}: {candidate}")
                    break

    if initial_prompt is None:
        prev = config["prev"]
        if prev:
            print(f"✗ No prompt provided and no output found from --phase {prev}.")
            print(f"  Run --phase {prev} first, or provide --prompt.")
        else:
            print(f"✗ --prompt is required for --phase {phase_name}.")
        sys.exit(1)

    run_debate(
        feature=feature,
        phase_name=phase_name,
        initial_prompt=initial_prompt,
        groom_template=config["groom"],
        critique_template=config["critique"],
        revise_template=config["revise"],
        max_rounds=max_rounds,
        artifact_prefix=config["prefix"],
        scope_check=scope_check,
        revise_final_template=config.get("revise_final"),
        read_codebase=read_codebase,
    )


# ---------------------------------------------------------------------------
# Phase: Implement
# ---------------------------------------------------------------------------

def phase_implement(feature: str, agent: str = None, both: bool = False):
    fdir = feature_dir(feature)
    principles = get_principles(feature)

    latest_round = _find_latest_round_in_phase(feature, "plan")
    if latest_round is None:
        print("✗ No planning artifacts found. Run --phase plan first.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"IMPLEMENTATION: {feature}")
    print(f"{'='*60}")

    agents_to_run = []
    if both:
        agents_to_run = [Agent.CLAUDE, Agent.CODEX]
    elif agent:
        agents_to_run = [Agent(agent)]
    else:
        print("Specify --agent claude|codex or --both")
        sys.exit(1)

    log = DebateLog(feature, "implement")

    for ag in agents_to_run:
        plan_file = _find_latest_artifact(feature, "plan", latest_round, ag, "plan")
        if not plan_file.exists():
            print(f"  ⚠ No plan found for {ag.value} at {plan_file}")
            continue

        plan = read_file(plan_file)
        branch_name = f"feat/{feature}-{ag.value}"
        worktree_path = f"wt-{feature}-{ag.value}"

        print(f"\n  Setting up worktree: {worktree_path} (branch: {branch_name})")
        _setup_worktree(worktree_path, branch_name)

        wt_crossai = Path(worktree_path) / CROSSAI_DIR / feature
        ensure_dir(wt_crossai)
        write_file(wt_crossai / "plan.md", plan)
        write_file(wt_crossai / "principles.md", principles)

        impl_prompt = assemble_prompt("implement", {
            "plan": plan, "principles": principles, "feature": feature,
        })

        print(f"\n  Running {ag.value} implementation...")
        try:
            if ag == Agent.CLAUDE:
                output = run_claude_with_edits(impl_prompt, cwd=worktree_path)
            else:
                output = run_codex_with_edits(impl_prompt, cwd=worktree_path)
        except CLITimeoutError as e:
            log.save()
            print(f"\n  ✗ {ag.value} implementation ABORTED: {e}")
            print(f"    Worktree preserved at: {worktree_path}/")
            sys.exit(1)

        impl_dir = fdir / "implementation"
        write_file(impl_dir / f"{ag.value}.log.md", output)
        log.record(0, "implement", ag.value, output)
        print(f"  ✓ {ag.value} implementation complete in {worktree_path}/")

    log.save()

    print(f"\n{'='*60}")
    print(f"✓ Implementation complete.")
    if both:
        print(f"  Compare: wt-{feature}-claude/ vs wt-{feature}-codex/")
        print(f"  Next: python orchestrate.py --feature \"{feature}\" --phase review")
    print(f"{'='*60}")


def _setup_worktree(path: str, branch: str):
    if Path(path).exists():
        print(f"    Worktree {path} already exists, reusing.")
        return
    subprocess.run(["git", "branch", branch], capture_output=True)
    result = subprocess.run(
        ["git", "worktree", "add", path, branch],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"    ⚠ Worktree creation failed: {result.stderr}")


# ---------------------------------------------------------------------------
# Phase: Review
# ---------------------------------------------------------------------------

def phase_review(feature: str):
    fdir = feature_dir(feature)
    principles = get_principles(feature)

    print(f"\n{'='*60}")
    print(f"CROSS-REVIEW: {feature}")
    print(f"{'='*60}")

    review_dir = fdir / "reviews"
    wt_claude = Path(f"wt-{feature}-claude")
    wt_codex = Path(f"wt-{feature}-codex")

    if not wt_claude.exists() or not wt_codex.exists():
        print("✗ Both worktrees must exist. Run --phase implement --both first.")
        sys.exit(1)

    log = DebateLog(feature, "review")

    claude_diff = _get_worktree_diff(wt_claude)
    codex_diff = _get_worktree_diff(wt_codex)

    try:
        review_prompt_claude = assemble_prompt("review", {
            "other_agent": "Codex", "diff": codex_diff,
            "principles": principles, "feature": feature,
        })
        claude_review = run_claude(review_prompt_claude)
        write_file(review_dir / "claude.reviews_codex.md", claude_review)
        log.record(0, "review", "Claude (reviewing Codex)", claude_review)

        review_prompt_codex = assemble_prompt("review", {
            "other_agent": "Claude", "diff": claude_diff,
            "principles": principles, "feature": feature,
        })
        codex_review = run_codex(review_prompt_codex)
        write_file(review_dir / "codex.reviews_claude.md", codex_review)
        log.record(0, "review", "Codex (reviewing Claude)", codex_review)
    except CLITimeoutError as e:
        log.save()
        print(f"\n  ✗ Review ABORTED: {e}")
        print(f"    Partial reviews (if any) saved in: {review_dir}/")
        sys.exit(1)

    log.save()

    print(f"\n  Reviews written to {review_dir}/")
    print(f"{'='*60}")


def _get_worktree_diff(wt_path: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "HEAD"], capture_output=True, text=True, cwd=str(wt_path),
    )
    diff = result.stdout.strip()
    if not diff:
        result = subprocess.run(
            ["git", "diff", "--cached"], capture_output=True, text=True, cwd=str(wt_path),
        )
        diff = result.stdout.strip()
    if not diff:
        result = subprocess.run(
            ["git", "status", "--short"], capture_output=True, text=True, cwd=str(wt_path),
        )
        diff = f"[No diff available. Git status:\n{result.stdout}]"
    return diff


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _find_latest_round_in_phase(feature: str, phase_name: str) -> int | None:
    pdir = phase_dir(feature, phase_name)
    if not pdir.exists():
        return None
    rounds = [
        int(d.name[1:])
        for d in pdir.iterdir()
        if d.is_dir() and d.name.startswith("r") and d.name[1:].isdigit()
    ]
    return max(rounds) if rounds else None

def _find_latest_artifact(feature: str, phase_name: str, round_num: int, agent: Agent, prefix: str) -> Path:
    rdir = round_dir(feature, phase_name, round_num)
    revised = rdir / f"{agent.value}.revised_{prefix}.md"
    if revised.exists():
        return revised
    return round_dir(feature, phase_name, 0) / f"{agent.value}.{prefix}.md"


# ---------------------------------------------------------------------------
# Project Root Detection
# ---------------------------------------------------------------------------

def _find_project_root(explicit_dir: str | None) -> Path:
    """Resolve the project root for artifact placement.

    Resolution order:
      1. --project-dir flag (explicit override)
      2. Nearest ancestor containing a .git/ directory
      3. Nearest ancestor containing a common project marker
         (.vscode/, pyproject.toml, package.json, Cargo.toml, go.mod)
      4. Current working directory (fallback, with info message)
    """
    if explicit_dir:
        p = Path(explicit_dir).expanduser().resolve()
        if not p.is_dir():
            print(f"✗ --project-dir not found: {p}")
            sys.exit(1)
        print(f"  ℹ Project root: {p}  (from --project-dir)")
        return p

    current = Path.cwd()
    for candidate in [current, *current.parents]:
        for marker in _PROJECT_MARKERS:
            if (candidate / marker).exists():
                via = f".{marker}" if marker.startswith(".") else marker
                print(f"  ℹ Project root: {candidate}  (via {via})")
                return candidate

    print(f"  ℹ No project root detected — artifacts will be written to {current / _CROSSAI_DIRNAME}/")
    print(f"    Use --project-dir /path/to/project to specify explicitly.")
    return current


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CrossAI: Automate Claude ↔ Codex ideation, planning, and review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Phases (run in order):
              ideation   Rough idea → Direction Summary via debate
              plan       Direction → Design & Implementation Plan via debate (auto-reads ideation)
              implement  Plan → code in worktrees
              review     Cross-review implementations

            Examples:
              # Ideation: debate the idea into a direction summary
              python orchestrate.py --feature auth --prompt idea.md --phase ideation

              # Plan: debate the direction into a design & implementation plan
              python orchestrate.py --feature auth --phase plan

              # Plan with explicit input and custom rounds
              python orchestrate.py --feature auth --prompt direction.md --phase plan --rounds 4

              # Implement with both agents
              python orchestrate.py --feature auth --phase implement --both

              # Cross-review
              python orchestrate.py --feature auth --phase review

            Project context note:
              By default, agents are instructed not to browse your source code.
              However, Claude Code reads CLAUDE.md automatically from the working
              directory — if you run CrossAI from inside an existing project, its
              CLAUDE.md will be loaded into Claude's system prompt.

              To avoid any project context leaking into the debate:
                - Run CrossAI from an empty directory:
                    mkdir /tmp/my-idea && cd /tmp/my-idea
                    python /path/to/orchestrate.py --feature ...
                - Or open VS Code/Cursor with just the prompt file (no project folder).

              Use --read-codebase to explicitly allow agents to browse source files.
        """),
    )
    parser.add_argument("--feature", required=True, help="Feature name (used as directory name)")
    parser.add_argument("--prompt", help="Path to initial prompt file")
    parser.add_argument("--phase", choices=["ideation", "plan", "implement", "review"], default="ideation")
    parser.add_argument("--rounds", type=int, default=3, help="Number of debate rounds (default: 3)")
    parser.add_argument("--agent", choices=["claude", "codex"], help="Which agent for implementation")
    parser.add_argument("--both", action="store_true", help="Run both agents for implementation")
    parser.add_argument("--no-scope-check", action="store_true",
                        help="Skip the interactive scope check after round 0")
    parser.add_argument("--read-codebase", action="store_true",
                        help="Allow agents to read project source files (default: off — "
                             "agents are instructed not to browse the codebase)")
    parser.add_argument("--project-dir", metavar="DIR",
                        help="Project root for artifact placement (default: auto-detected)")

    args = parser.parse_args()

    global CROSSAI_DIR
    project_root = _find_project_root(args.project_dir)
    CROSSAI_DIR = project_root / _CROSSAI_DIRNAME

    if args.phase in ("ideation", "plan"):
        explicit_prompt = None
        if args.prompt:
            prompt_path = Path(args.prompt)
            if not prompt_path.exists():
                parser.error(f"Prompt file not found: {prompt_path}")
            explicit_prompt = read_file(prompt_path)
        run_debate_phase(args.feature, args.phase, explicit_prompt,
                         max_rounds=args.rounds, scope_check=not args.no_scope_check,
                         read_codebase=args.read_codebase)

    elif args.phase == "implement":
        phase_implement(args.feature, agent=args.agent, both=args.both)

    elif args.phase == "review":
        phase_review(args.feature)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nAborted by user.")
        sys.exit(130)
