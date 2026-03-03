# Analyze Sub-Spec

Read the sub-spec file at `docs/sub-specs/$ARGUMENTS.md`.

If the file doesn't exist, tell the user and suggest running `/new-subspec $ARGUMENTS` first.

If the file exists, analyze it thoroughly:

1. **Extract all acceptance criteria** — list them numbered
2. **Identify dependencies** — which other sub-specs must be complete first? Check `docs/plan.md` to verify their status
3. **Map integration points** — what does this module consume? What does it produce? Which other modules call it?
4. **Generate implementation spec:**
   - File structure: list every file that will be created/modified
   - Function signatures: name, parameters with types, return type
   - Data flow: input → processing → output
   - Error handling: what can fail, how to handle each failure
   - Test plan: one test per acceptance criterion, plus edge cases

5. **Estimate complexity** — lines of code, number of functions, number of tests

Present the implementation spec clearly formatted. Then **STOP and wait for user approval** before writing any code.

Do NOT start implementing. The user must explicitly approve the plan.
