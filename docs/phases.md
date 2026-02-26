# The Four Phases

CrossAI runs a structured pipeline between Claude Code (conductor) and Codex CLI (challenger).
Each phase builds on the previous one via artifact chaining.

---

## Phase 1: Ideation

**Input:** A feature description (plain text file)
**Output:** `.crossai/<feature>/ideation/ideation_summary.md` — a concrete, agreed direction

**What happens:**
- Both agents independently explore the idea (Round 0)
- They critique each other's direction (Rounds 1+)
- The final round converges on a specific architecture, v1 scope, and build sequence
- Tone is collaborative — exploring possibilities, not gatekeeping

**Command:**
```bash
python orchestrate.py --feature <name> --prompt idea.md --phase ideation [--rounds 3]
```

---

## Phase 2: Plan

**Input:** The ideation summary (auto-read from Phase 1 output), or an explicit `--prompt`
**Output:** `.crossai/<feature>/plan/plan_summary.md` — a detailed technical design plan

**What happens:**
- Round 0: Both agents produce a full plan with 21 mandatory sections
- **Scope Guard:** After Round 0, the orchestrator analyzes both plans for scope creep. You confirm which new items to exclude; exclusions become injected constraints.
- Rounds 1+: Agents critique each other's plans rigorously (tone is critical, not collaborative)
- Final round converges on concrete data structures, algorithms, and sprint sequencing

**Mandatory plan sections:** Context, Goals/Non-Goals, Architecture, Key Design Decisions, Data Model, API/Interface Design, Dependencies, Security, Scalability, Observability, Requirements, Assumptions, Work Plan, Testing Plan, Rollout Plan, Risks/Mitigations, Open Questions.

**Command:**
```bash
python orchestrate.py --feature <name> --phase plan [--rounds 3]
```

---

## Phase 3: Implement

**Input:** The latest plan artifact
**Output:** Two git worktrees: `wt-<feature>-claude/` and `wt-<feature>-codex/`

**What happens:**
- Each agent works independently in its own git worktree (isolated branch)
- Both receive the same plan; implementations may differ in approach
- You cherry-pick the best parts, or pick one whole implementation

**Command:**
```bash
# Both agents in parallel (recommended)
python orchestrate.py --feature <name> --phase implement --both

# Single agent
python orchestrate.py --feature <name> --phase implement --agent claude
python orchestrate.py --feature <name> --phase implement --agent codex
```

---

## Phase 4: Review

**Input:** Git diffs from both worktrees
**Output:** `.crossai/<feature>/reviews/` — each agent reviews the other's code

**What happens:**
- Claude reviews Codex's implementation
- Codex reviews Claude's implementation
- Each review covers: summary verdict, correctness, code quality, safety/security, tests/observability, performance, and a concrete fix list

**Command:**
```bash
python orchestrate.py --feature <name> --phase review
```

---

## Artifact Chaining

Phases automatically read the previous phase's output. You can override with `--prompt`:

```
ideation → plan → implement → review
            ↑ auto-reads ideation_summary.md
                       ↑ auto-reads plan_summary.md
```

## Conversation History

Every round includes the full debate history so far. When history exceeds ~80k characters, older rounds are auto-summarized via Claude to keep context manageable.

## Convergence Footer

Every artifact ends with:
```
Confidence: <0.0–1.0>
Convergence: HIGH | MEDIUM | LOW
Notes: <1–3 bullets>
```
This is informational — use it to decide whether to run additional rounds.
