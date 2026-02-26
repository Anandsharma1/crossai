# Task: Develop a Design & Implementation Plan

You are one of two independent agents participating in a structured planning workflow.
Take the direction summary (or feature prompt) below and produce a comprehensive plan
that covers both the technical design and the implementation steps.

## Shared Principles (apply throughout)
{{principles}}

## Direction / Input
{{initial_prompt}}

---

## Output Contract (strict)
- Output **Markdown only**.
- Use **exactly** the headings below, in the same order.
- Be specific and actionable; avoid vague guidance.
- Prefer bullets. Avoid long prose.
- Do **not** include tool logs, meta commentary, or references to "the other agent".
- Do **not** use code fences unless absolutely necessary.
- Describe data flows and architecture in words (no diagrams needed).

# Context
- What are we building/changing? What is in/out of scope?
- How this aligns with the direction summary (if provided)

# Goals and Non-Goals
## Goals
## Non-Goals

# Architecture
- System components and their responsibilities
- How components interact (data flow, control flow)
- Where this fits in the existing system

# Key Design Decisions
- Major decisions made and the rationale for each
- For each: what was chosen, what was rejected, and why

# Data Model
- Key entities, schemas, or data structures
- Storage approach (DB, cache, file, etc.)
- Data lifecycle (creation, update, deletion, retention)

# API / Interface Design
- External APIs (endpoints, methods, payloads)
- Internal interfaces between components
- Message formats, protocols, contracts
- Compatibility expectations

# Dependencies
- External services, libraries, or systems required
- Version constraints
- Failure behavior when dependencies are unavailable

# Security Considerations
- Authentication and authorization approach
- Data protection (in transit, at rest)
- Input validation and sanitization

# Scalability and Performance
- Expected load and growth patterns
- Bottlenecks and how to address them
- Caching strategy (if any)

# Observability
- Logging approach
- Metrics to track
- Alerting thresholds
- Tracing / debugging support

# Requirements
## Functional
## Non-Functional

# Assumptions and Constraints
- Assumptions about environment, repo structure, dependencies, permissions
- Constraints: time, risk, backward compatibility, interfaces, SLOs

# Work Plan
## Milestones
## Task Breakdown
- Ordered, granular steps
## Acceptance Criteria
- Concrete checks to say "done"

# Testing Plan
- Unit tests
- Integration tests
- Edge cases / failure modes
- Performance / load (if relevant)

# Rollout Plan
- Migration steps
- Backward compatibility plan
- Feature flags / staged rollout (if relevant)
- Rollback plan

# Risks and Mitigations
- Technical risks with severity and mitigation strategy

# Open Questions
- What must be clarified before implementation?

---

Confidence: <0.0 to 1.0>
Convergence: <HIGH|MEDIUM|LOW>
Notes: <1-3 bullets on what would most improve the plan>
