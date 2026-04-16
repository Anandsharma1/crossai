# Scope Adjudication

You are reviewing possible scope drift introduced during round 0 of a CrossAI debate.
Your job is to decide whether each candidate item is actually required, high-value optional,
not needed for v1, or merely an assumption/design choice.

## Original Prompt
{{initial_prompt}}

## Candidate Scope Drift Items
{{candidate_items}}

## Your Round 0 Output
{{own_output}}

## Other Agent's Round 0 Output
{{other_output}}

---

## Output Contract

Return Markdown only using exactly these headings:

# Required for Correctness
- Items that must be in scope to solve the requested problem correctly

# High-Value Optional
- Items that improve the solution materially but are not required for v1

# Not Needed for V1
- Items that add meaningful scope and should be excluded from the v1 approach

# Assumptions or Design Choices
- Items that are not real scope drift and should not be treated as separate scope

# Notes
- 1-5 bullets on the tradeoffs or consequences of excluding the non-v1 items

Rules:
- Refer to each candidate item explicitly.
- Be decisive. Do not say "it depends" without still classifying the item.
- Treat "required for correctness" as a high bar.
- Prefer keeping v1 focused unless the original prompt clearly implies the item.
