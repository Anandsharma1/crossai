# Shared Principles

These principles apply to ALL planning, implementation, and review.

## Architecture
- Follow existing patterns in the codebase
- Prefer composition over inheritance
- Keep functions small and focused

## Code Quality
- Write self-documenting code; comments explain WHY, not WHAT
- Handle errors explicitly — no silent failures
- All public interfaces need input validation

## Testing
- Every feature needs unit tests at minimum
- Test edge cases and error paths, not just happy paths
- Tests should be readable and serve as documentation

## Security
- Never trust user input
- Use parameterized queries, no string concatenation for SQL
- Follow principle of least privilege

## Performance
- Don't optimize prematurely, but don't be obviously wasteful
- Consider database query count and payload sizes
- Cache where it makes sense, invalidate correctly

---

*Edit this file to reflect YOUR team's actual principles.*
