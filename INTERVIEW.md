# Practice session

This mirrors an applied coding interview: **90 minutes of independent work**
on the problems below, followed by a walkthrough where you explain what you
did and why.

| # | File | Difficulty | Suggested time |
|---|------|------------|----------------|
| 1 | [problems/01-expiry-bugs.md](problems/01-expiry-bugs.md) | Easy | 15 min |
| 2 | [problems/02-transactions.md](problems/02-transactions.md) | Medium | 30 to 35 min |
| 3 | [problems/03-crash-recovery-and-compaction.md](problems/03-crash-recovery-and-compaction.md) | Hard | 40 min |

## Ground rules (same as the real thing)

- Use any tools you like: editor, debugger, docs, AI assistants.
- Read the existing code before changing it. Skim all of `tinykv/` and
  `tests/` first (budget ~10 minutes); every problem depends on it.
- Keep the existing tests passing and add tests for what you change.
- Commit as you go (`git commit` after each problem) so the walkthrough has a
  clean story.
- It is fine not to finish. A correct, tested partial solution with a clear
  explanation of what is left beats a sprawling untested one.

## For the walkthrough, be ready to explain

- How you found your way around the code, and what you ran first.
- The root cause of each bug, not just the fix.
- Design choices and the alternatives you rejected.
- How you know it works (which tests, which edge cases).
- What you would do with another hour.

## Checking your work

There is a `solutions` branch with reference solutions, extra acceptance tests
and walkthrough notes. **Don't look until you're done.**

To grade yourself without seeing the solution code, pull in only the
acceptance tests:

```sh
git checkout solutions -- tests/acceptance
pytest -q tests/acceptance
```

Then, if you want to compare approaches: `git diff main solutions -- tinykv/`
and read `SOLUTIONS.md` on that branch.
