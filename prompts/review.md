# Task: Review Another Agent's Implementation (v1)

You are reviewing the other agent's implementation for feature: {{feature}}

## Shared Principles (apply throughout)
{{principles}}

## The Other Agent
{{other_agent}}

## Diff / Status Snapshot (to review)
{{diff}}

---

## Output Contract (strict)
- Output **Markdown only**.
- Use **exactly** the headings below, in the same order.
- Be concrete: cite specific files/areas when possible (based on the diff).
- Include actionable fix suggestions.

# Summary Verdict
- Approve? (Yes/No/Conditional)
- 3–6 bullets: main strengths/concerns

# Correctness and Completeness
- Does it meet functional requirements?
- Missing parts?

# Code Quality and Maintainability
- Structure, readability, modularity
- Naming, duplication, complexity

# Safety, Security, and Reliability
- Error handling
- Validation
- Secrets / unsafe defaults
- Failure modes

# Tests and Observability
- Missing tests or weak coverage
- Logs/metrics/tracing gaps

# Performance and Scalability (if relevant)
- Hot paths, inefficiencies

# Concrete Fix List
- 5–20 bullets: prioritized fixes
- Mark each as [Must] / [Should] / [Nice]

# Questions to Clarify
- 3–10 questions

---

Confidence: <0.0 to 1.0>
Convergence: <HIGH|MEDIUM|LOW>
Notes: <1-3 bullets on whether the other agent is close to shippable>
