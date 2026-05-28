# reporting None generated-wave fix

- Date: 2026-05-04
- Scope: `seiswave/core/reporting.py`, `tests/test_reporting_edge.py`
- Type: boundary-condition fix

## Problem

`build_selection_summary()` claimed to tolerate missing/generated placeholder waves, but when `generated_waves` contained `None` it accessed `sig.name` before checking for null, causing `AttributeError`.

## Change

- Updated artificial-wave summary building so `None` placeholders are accepted.
- Preserved stable fallback fields:
  - `name = artificial_<index>`
  - `pga = 0.0`
  - `duration = 0.0`
  - `dt = 0.0`
  - `n = 0`
- Added regression test for this edge case.

## Verification

- `python3 -m pytest tests/test_reporting_edge.py -q` → pass
- `python3 -m pytest tests/test_reporting.py -q` → pass

## Notes

This was the second real AutoResearch validation run for SeisWave. Unlike the first run, the AutoResearch wrapper completed cleanly in one iteration.
