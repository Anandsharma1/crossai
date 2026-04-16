# Scope Decision Merge

You are merging two scope adjudications from Claude and Codex into one final scope decision artifact.

## Original Prompt
{{initial_prompt}}

## Candidate Scope Drift Items
{{candidate_items}}

## Claude Adjudication
{{claude_scope}}

## Codex Adjudication
{{codex_scope}}

---

## Output Contract

Return Markdown only using exactly these headings:

# Scope Drift Considered
- Enumerate the candidate items in clear language

# Accepted into Scope
- Items accepted into the approach
- Label each as [Required] or [Optional]

# Rejected from V1 Scope
- Items explicitly rejected from v1
- Explain why in one sentence each

# Assumptions / Design Choices
- Items that were reviewed and determined not to be real scope drift

# Constraints for Subsequent Rounds
- Concrete instructions to apply in later rounds
- Include explicit "Do not..." bullets for rejected items
- Include explicit "Include..." bullets for accepted required items if needed

# Notes
- Briefly summarize the overall drift posture of the approach

Rules:
- Be conservative about expanding v1 scope.
- If the two adjudications disagree, prefer the narrower v1 unless excluding the item would make the solution invalid.
- Make the "Constraints for Subsequent Rounds" section directly usable as injected guidance.
