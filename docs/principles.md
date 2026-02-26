# Configuring principles.md

`principles.md` is injected into every round's prompt for both agents.
It's your way of encoding team conventions, quality bars, and non-negotiables
so that every plan and every piece of generated code reflects your standards.

## Creating your principles file

**User-level:**
```bash
cp ~/.crossai/principles.example.md ~/.crossai/principles.md
$EDITOR ~/.crossai/principles.md
```

**Repo-level:**
```bash
cp cross_ai/principles.example.md cross_ai/principles.md
$EDITOR cross_ai/principles.md
```

## Scope

CrossAI looks for principles in this order (most specific wins):

1. `.crossai/<feature>/principles.md` — feature-specific overrides
2. `.crossai/principles.md` (repo-level install) or `~/.crossai/principles.md` (user-level) — global

## What to put in principles.md

Good principles are **constraints and standards**, not instructions to the AI
about how to behave. Examples:

```markdown
## Architecture
- All services communicate via REST; no direct DB access from the frontend
- Auth is handled by the existing JWT middleware — do not design a new auth layer

## Code Quality
- No functions longer than 40 lines
- Every public function has a docstring
- Type annotations required on all Python functions

## Testing
- Minimum 80% line coverage for new code
- Integration tests for all API endpoints
- No mocking of the database layer in integration tests

## Security
- No secrets in code or config files — use environment variables
- Validate all inputs at the API boundary
```

## Feature-specific principles

To constrain a single feature's debate without affecting others:

```bash
mkdir -p .crossai/my-feature
echo "## Constraint\n- This feature must not touch the billing module." \
  > .crossai/my-feature/principles.md
```
