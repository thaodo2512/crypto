# Implement Sub-Spec

Implement the module defined in `docs/sub-specs/$ARGUMENTS.md`.

## Pre-checks
1. Read `docs/plan.md` — verify all dependencies for this sub-spec are marked ✅ (done). If not, stop and tell the user which dependencies are missing.
2. Read `docs/sub-specs/$ARGUMENTS.md` — load the full sub-spec.
3. Read `CLAUDE.md` — refresh coding standards.
4. Read `config/settings.yaml` — check for thresholds this module needs.

## Implementation rules
- Follow coding standards from CLAUDE.md strictly
- Every function must have type hints on all parameters and return values
- Docstrings reference sub-spec sections: `"""See docs/sub-specs/$ARGUMENTS.md §X.X"""`
- All thresholds and magic numbers come from `config/settings.yaml` — never hardcode
- Use `logging` module, never `print()`
- Async for all HTTP/API calls
- Signal scores always `float` in `[-1.0, +1.0]`, use `numpy.clip()`
- On data source failure: log error, return neutral score (0.0), never crash

## Steps
1. Create/modify source files as defined in the sub-spec deliverables
2. Write unit tests — one test function per acceptance criterion: `test_[criterion_description]()`
3. Mock all external dependencies (APIs, DB, network)
4. Run tests with `pytest tests/ -v`
5. If all tests pass, update `docs/plan.md`:
   - Change status from 🔲 or 🟡 to ✅
   - Add completion note

If tests fail, fix the code and re-run. Do not mark as done until all tests pass.
