# Task: Critique Another Agent's Design & Implementation Plan

You are participating in a cross-review workflow.
Your job is to critique the other agent's plan **constructively but rigorously**, using shared principles and your own plan as reference. Cover both design quality and implementation readiness.

## Shared Principles (apply throughout)
{{principles}}

## The Other Agent
{{other_agent}}

## The Other Agent's Plan (to critique)
{{other_plan}}

## Your Current Plan (for comparison)
{{own_plan}}

## Conversation So Far
{{conversation_history}}

---

## Output Contract (strict)
- Output **Markdown only**.
- Use **exactly** the headings below, in the same order.
- Be direct; list concrete gaps, risks, and better alternatives.
- Prefer bullets. Avoid long prose.
- Do **not** rewrite the full plan — critique and propose improvements.

# Summary Verdict
- 3-6 bullets: what is strong vs weak
- Should we adopt this plan as-is? (Yes/No/With changes)

# Architecture Concerns
- Coupling, cohesion, separation of concerns
- Missing components or unnecessary complexity
- Scalability or extensibility issues

# Design Decision Challenges
- Which decisions do you disagree with and why?
- Are alternatives adequately considered?
- Missing tradeoff analysis

# Data Model and Interface Issues
- Schema gaps, normalization concerns, lifecycle issues
- API contract clarity, backward compatibility
- Missing error cases or edge cases

# Security and Operational Gaps
- Unaddressed threat vectors
- Missing validation or authorization checks
- Observability gaps, deployment complexity, failure mode handling

# Missing Requirements / Ambiguities
- What requirements are not stated or unclear?

# Risks and Failure Modes
- What could go wrong in implementation/ops?
- What are the hardest parts?

# Testing and Rollout Gaps
- Missing tests, missing rollback, missing observability

# Concrete Improvements
- 5-15 bullets: specific changes to make the plan implementable and safer
- If you suggest alternatives, include trade-offs

# Conflicts With Shared Principles
- If any, cite which principle and how it's violated

# Questions to Resolve
- 3-10 focused questions

---

Confidence: <0.0 to 1.0>
Convergence: <HIGH|MEDIUM|LOW>
Notes: <1-3 bullets on what would make both plans converge faster>
