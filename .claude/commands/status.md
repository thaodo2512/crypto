# Project Status

Show the current state of the project.

## Steps

1. Read `docs/plan.md` — parse the progress tracker table
2. Count statuses:
   - 🔲 TODO
   - 🟡 IN PROGRESS
   - ✅ DONE
   - ⏸️ PAUSED/BLOCKED
3. Identify:
   - Current milestone (which milestone are we in?)
   - Next actionable sub-spec (first 🔲 with all dependencies ✅)
   - Blockers (any ⏸️ items, or 🟡 items stuck)
4. Count source files and test files:
   ```
   find custom/ -name "*.py" -not -name "__init__.py" | wc -l
   find tests/ -name "test_*.py" | wc -l
   ```
5. Run test suite with summary:
   ```
   pytest tests/ -v --tb=line -q 2>&1 | tail -20
   ```

## Output Format

```
PROJECT STATUS
═════════════════════════════════

Progress: X/Y sub-specs complete
  🔲 TODO:        N
  🟡 IN PROGRESS: N
  ✅ DONE:        N
  ⏸️ BLOCKED:     N

Current Milestone: [name]
Next Action: /spec [SS-XX] — [description]
Blockers: [none or list]

Code: N source files | N test files
Tests: N passed, N failed, N total
```
