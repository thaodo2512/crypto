# Create New Sub-Spec

Create a detailed sub-spec file for module `$ARGUMENTS`.

## Steps

1. Read `docs/crypto-signal-bot-spec.md` — but ONLY the sections relevant to this sub-spec. Do NOT read the entire spec unless necessary.
2. Read `docs/plan.md` — identify which spec sections map to this sub-spec and what dependencies exist.
3. Create the sub-spec file at `docs/sub-specs/$ARGUMENTS.md` with this format:

```markdown
# $ARGUMENTS: [Descriptive Name]

**Master Spec Sections:** §X, §Y
**Dependencies:** [List of SS-XX that must be complete first, or "None"]
**Estimated LOC:** ~NNN

## Scope
[2-3 sentences: what this sub-spec covers, what it does NOT cover]

## Deliverables
[File tree of all files this sub-spec will create or modify]

## Key Requirements
[Numbered list — each requirement is specific, testable, extracted from the spec.
Include formulas, thresholds, data types, ranges where applicable.]

1. Requirement 1
2. Requirement 2
...

## Acceptance Criteria
[Checklist — each item is a single testable statement]
- [ ] Criterion 1
- [ ] Criterion 2
...

## Test Strategy
[Types of tests needed, what to mock, key edge cases to cover]

## Integration Points
[What this module provides to others (outputs, APIs, data)]
[What this module depends on from others (inputs, APIs, data)]
```

4. Update `docs/plan.md` — ensure the sub-spec is listed in the progress tracker.

Keep requirements concrete and testable. Avoid vague language like "should handle errors properly" — instead: "Returns score 0.0 when API returns HTTP 500."
