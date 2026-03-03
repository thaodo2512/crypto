# Write Tests for Sub-Spec

Write comprehensive tests for the module defined in `docs/sub-specs/$ARGUMENTS.md`.

## Steps

1. Read `docs/sub-specs/$ARGUMENTS.md` — extract ALL acceptance criteria
2. Read the implementation source files for this sub-spec
3. For each acceptance criterion, write a test function:
   - Name: `test_[criterion_description]()` — descriptive, maps to the criterion
   - Each test is independent — no test depends on another
4. Mock all external dependencies:
   - API calls → mock responses with realistic data
   - Database → use in-memory SQLite or mock
   - Network → never make real HTTP calls in tests
5. Include edge cases:
   - Empty/null inputs
   - Boundary values (scores at -1.0, 0, +1.0)
   - Data source failures (mock API errors)
   - Extreme market conditions
6. Include golden tests where applicable:
   - Known input → expected output (from spec formulas)
   - Calculate expected values by hand, verify code produces them
7. Run the test suite: `pytest tests/ -v --tb=short`
8. Report results: total tests, passed, failed, coverage summary

Place test files in `tests/` directory with naming convention `test_[module_name].py`.
