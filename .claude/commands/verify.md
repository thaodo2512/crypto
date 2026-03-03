# Verify Sub-Spec Implementation

Verify the implementation of `docs/sub-specs/$ARGUMENTS.md` against its acceptance criteria.

## Verification Checklist

### 1. Acceptance Criteria Coverage
Read the sub-spec and check EVERY acceptance criterion:
- Does matching code exist? (cite file:line)
- Does a matching test exist? (cite test function name)
- Mark each: PASS / FAIL / MISSING

### 2. Code Quality
- [ ] All functions have type hints
- [ ] All functions have docstrings referencing sub-spec sections
- [ ] No magic numbers (all thresholds from config/settings.yaml)
- [ ] Error handling: data source failures return neutral, never crash
- [ ] Logging used (no print statements)
- [ ] Async used for HTTP calls

### 3. Test Suite
Run: `pytest tests/ -v --tb=short`
- Report: total / passed / failed
- Check: at least one test per acceptance criterion

### 4. Integration
- [ ] Module imports work from other modules that depend on it
- [ ] Output format matches what downstream modules expect
- [ ] Config values are loaded correctly

## Output

Generate a verification report:

```
VERIFICATION REPORT — $ARGUMENTS
═══════════════════════════════════

Acceptance Criteria: X/Y met
Code Quality: PASS/FAIL (issues listed)
Test Suite: X passed, Y failed, Z total
Integration: PASS/FAIL

Overall: PASS / FAIL

Issues Found:
1. [issue description]
2. [issue description]
```

If PASS → update `docs/plan.md` status to ✅
If FAIL → list specific issues that need fixing
