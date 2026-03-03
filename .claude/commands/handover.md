# Session Handover

Summarize the current session for continuity with the next session.

## Steps

1. Review what was worked on this session:
   - Which sub-spec(s) were touched?
   - What files were created or modified?
   - What decisions were made and why?
   - What issues were encountered?

2. Check current state:
   - Read `docs/plan.md` for overall progress
   - Run `git status` to see uncommitted changes
   - Run `pytest tests/ -q 2>&1 | tail -5` for test status

3. Write a handover entry and append it to `docs/plan.md` under the **Session Log** section:

```markdown
### Session — [YYYY-MM-DD]
**Sub-spec:** SS-XX [Name]
**Status:** [Completed / In Progress / Blocked]
**What was done:**
- [Specific accomplishments with file names]
**Decisions made:**
- [Any design decisions or trade-offs]
**Issues/Notes:**
- [Problems encountered, workarounds, open questions]
**Next session should:**
- [Specific next steps with file names and function names]
- [Where exactly to pick up]
```

4. If there are uncommitted changes, remind the user to commit.

Keep the handover concise but specific — mention exact file names, function names, and line numbers so the next session can pick up immediately without re-reading everything.
