# autoresearch stability validation

- Date: 2026-05-04
- Scope: `autoresearch-codex.sh`, `tests/test_acc2vd_edge.py`, `tests/test_reporting_edge.py`, `tests/test_reporting_more.py`, `tests/test_combiner_edge.py`
- Type: workflow validation

## Goal

Validate whether the SeisWave `agent-wiki + autoresearch + codex` workflow is stable enough for repeated day-to-day use on small fixes.

## Real runs completed

1. `acc2vd` empty-input fix
   - Added explicit `ValueError` for empty acceleration arrays.
   - Regression tests passed.
   - AutoResearch wrapper needed manual final verification.

2. `build_selection_summary(None)` generated-wave fix
   - Accepted `None` placeholders in `generated_waves`.
   - Regression tests passed.
   - AutoResearch completed cleanly in one iteration.

## Extra stability tests added

- `tests/test_combiner_edge.py`
  - export with no groups still writes empty summary
  - HTML report generation without valid `h1` still succeeds
- `tests/test_reporting_more.py`
  - `build_selection_summary(None, None)` returns empty summary
  - target spectrum metadata is preserved without wave lists

## Verification

- `python3 -m pytest tests/test_acc2vd_edge.py -q` → pass
- `python3 -m pytest tests/test_fortran.py -q` → pass
- `python3 -m pytest tests/test_reporting_edge.py tests/test_reporting.py -q` → pass
- `python3 -m pytest tests/test_combiner_edge.py tests/test_reporting_more.py -q` → pass
- `python3 -m pytest tests/ -q` → 113 passed

## Conclusion

The workflow is now stable for small/targeted SeisWave fixes. It is ready for normal use on selector/combiner/reporting/core edge-case tasks, with a preference for small scoped prompts and explicit test commands.
