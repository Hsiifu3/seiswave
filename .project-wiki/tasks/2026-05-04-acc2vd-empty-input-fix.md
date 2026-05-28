# acc2vd empty input fix

- Date: 2026-05-04
- Scope: `seiswave/core/fortran_bridge.py`, `tests/test_acc2vd_edge.py`
- Type: boundary-condition fix

## Problem

`acc2vd()` accepted an empty acceleration array and returned inconsistent behavior instead of failing fast with a clear error.

## Change

- Added explicit guard in `acc2vd()`:
  - raise `ValueError("Input acceleration array is empty")` when `acc.size == 0`
- Added regression tests for:
  - empty input raises stable `ValueError`
  - single-element input still works

## Verification

- `python3 -m pytest tests/test_acc2vd_edge.py -q` → 2 passed
- `python3 -m pytest tests/test_fortran.py -q` → 8 passed

## Notes

This was used as the first real AutoResearch validation run for SeisWave. The code change landed correctly; the AutoResearch wrapper session itself did not exit cleanly, so final verification was completed manually.
