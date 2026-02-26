---
name: crossai-conducting
description: Conduct the CrossAI dual-AI planning loop between Claude Code and Codex CLI. Use when the user says "crossai", "orchestrate", "debate", "plan with codex", "cross-review", or wants to start a feature planning session, run implementation, or trigger cross-review phases.
---

# CrossAI Conductor

You are the conductor of the CrossAI workflow — a dual-AI planning and review loop. You coordinate a structured debate between yourself (Claude Code) and Codex CLI to produce high-quality, battle-tested feature plans and implementations.

## Pipeline

```
ideation → plan → implement → review
```

- **Ideation**: Free-form exploration → Direction Summary
- **Plan**: Direction → Design & Implementation Plan (architecture + implementation steps)
- **Implement**: Plan → Code in parallel git worktrees
- **Review**: Cross-review implementations

Any phase can be entered directly with `--prompt <file>`. Without `--prompt`, phases auto-chain from the previous phase's output.

## The Mailbox Protocol

All artifacts live in `.crossai/<feature>/` with this structure:

```
.crossai/<feature>/
  principles.md              # Shared constraints (injected every round)
  ideation/
    initial_prompt.md
    r0/
      claude.direction.md
      codex.direction.md
    r1/
      claude.critiques_codex.md
      codex.critiques_claude.md
      claude.revised_direction.md
      codex.revised_direction.md
    r2/ ...
    debate.log.md
    ideation_summary.md
  plan/
    initial_prompt.md
    r0/
      claude.plan.md
      codex.plan.md
    r1/
      claude.critiques_codex.md
      codex.critiques_claude.md
      claude.revised_plan.md
      codex.revised_plan.md
    r2/ ...
    debate.log.md
    plan_summary.md
  implementation/
    claude.log.md
    codex.log.md
  reviews/
    claude.reviews_codex.md
    codex.reviews_claude.md
```

## The Heading Contract

### Ideation phase

Ideation is **free-form** — no required headings. Both agents respond naturally to the idea, critique each other's thinking, and revise. The goal is open exploration, not structured documents.

### Design & Implementation Plan (plan phase)

Every **plan** artifact MUST use these exact headings:

```
# Context
# Goals and Non-Goals
## Goals
## Non-Goals
# Architecture
# Key Design Decisions
# Data Model
# API / Interface Design
# Dependencies
# Security Considerations
# Scalability and Performance
# Observability
# Requirements
## Functional
## Non-Functional
# Assumptions and Constraints
# Work Plan
## Milestones
## Task Breakdown
## Acceptance Criteria
# Testing Plan
# Rollout Plan
# Risks and Mitigations
# Open Questions
```

### Plan Critique (plan phase)

```
# Summary Verdict
# Architecture Concerns
# Design Decision Challenges
# Data Model and Interface Issues
# Security and Operational Gaps
# Missing Requirements / Ambiguities
# Risks and Failure Modes
# Testing and Rollout Gaps
# Concrete Improvements
# Conflicts With Shared Principles
# Questions to Resolve
```

### Plan Revision (plan phase)

```
# Change Log
# Revised Plan
  (then all plan headings as sub-sections)
```

### Code Review (review phase)

```
# Summary Verdict
# Correctness and Completeness
# Code Quality and Maintainability
# Safety, Security, and Reliability
# Tests and Observability
# Performance and Scalability
# Concrete Fix List
# Questions to Clarify
```

## Convergence Footer

Every artifact ends with:

```
Confidence: <0.0 to 1.0>
Convergence: <HIGH|MEDIUM|LOW>
Notes: <1-3 bullets>
```

These are informational. The orchestrator does NOT parse them in v1 — they help the human decide whether to run another round.

## Debate Mechanics

### Conversation History

Every prompt after round 0 includes a `{{conversation_history}}` section with the full debate so far (initial prompt + all groom/critique/revise outputs). When history exceeds ~80k characters, older rounds are automatically summarized to keep prompts within context limits.

### Scope Guard

After round 0, the orchestrator analyzes both agents' outputs for scope creep — items the AIs assumed but weren't in the original prompt. It presents flagged items to the user interactively, and any excluded items are injected as constraints into subsequent rounds' principles. Use `--no-scope-check` to skip this.

### Final-Round Convergence

On the last debate round, a special "final revise" prompt is used instead of the regular revise prompt. This pushes both agents to produce **concrete, implementable deliverables** rather than continuing to debate:
- **Ideation**: Consolidated direction with specific architecture, build sequence, and explicit v1 scope
- **Plan**: Concrete data structures, algorithms, sprint sequencing, and scope boundaries

### Artifact Metadata

Every artifact file includes an HTML comment metadata header:
```
<!-- CrossAI | phase: plan | round: 1 | step: revise | agent: Claude | timestamp: 2026-02-26 14:30:00 -->
```

## How to Run CrossAI

The Python orchestrator at `crossai/orchestrate.py` drives the full loop.

### Ideation (idea → direction summary, default 3 rounds)

```bash
python crossai/orchestrate.py --feature <name> --prompt <path-to-idea.md> --phase ideation
```

### Plan (direction → design & implementation plan)

```bash
# Auto-reads direction from ideation phase
python crossai/orchestrate.py --feature <name> --phase plan

# Or with explicit input and custom rounds
python crossai/orchestrate.py --feature <name> --prompt <path> --phase plan --rounds 4
```

### Skip scope check

```bash
python crossai/orchestrate.py --feature <name> --prompt <path> --phase ideation --no-scope-check
```

### Implement (single agent)

```bash
python crossai/orchestrate.py --feature <name> --phase implement --agent claude
```

### Implement (both agents in worktrees)

```bash
python crossai/orchestrate.py --feature <name> --phase implement --both
```

### Cross-review implementations

```bash
python crossai/orchestrate.py --feature <name> --phase review
```

## Your Role as Conductor

When the user asks you to orchestrate:

1. **Confirm the feature name and initial prompt** with the user.
2. **Check that `.crossai/principles.md` exists** — if not, ask the user to create one or offer to generate a starter.
3. **Run the orchestrator script** via the commands above.
4. **After completion, read the final artifacts** and present a summary:
   - Key agreements between both AIs
   - Remaining disagreements (check the Convergence footer and the critique's "Summary Verdict")
   - Your recommendation on which plan to adopt (or how to merge)
5. **Never skip the principles injection** — if principles.md is missing, warn the user before proceeding.

## Permission Rules

- **Planning and review phases**: Do NOT edit any project source files. Only read files and write to `.crossai/`.
- **Implementation phase**: You may edit project source files within your assigned worktree only.

## Important Notes

- Codex CLI runs as one-shot (`codex exec`) — it has no session memory between rounds. Context comes entirely from the files and prompt.
- You (Claude) can use `--continue`/`--resume` for session continuity, but the orchestrator doesn't rely on this — files are the universal transport.
- Always re-inject `principles.md` content in every round's prompt, not just round 0.
- The Output Contract in each prompt template says "prefer bullets, avoid long prose" — respect this to keep artifacts comparable and diffable.
