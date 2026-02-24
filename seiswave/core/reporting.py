"""选波汇总与报告字段构建。"""

from __future__ import annotations

import numpy as np


def build_selection_summary(natural_results, generated_waves, code_periods=None, code_sa=None):
    """构建可导出的汇总字典（天然波+人工波）。"""
    natural = []
    for i, r in enumerate(natural_results or [], 1):
        rec = r.record
        natural.append({
            "index": i,
            "type": "natural",
            "rsn": int(rec.rsn),
            "event": rec.event,
            "station": rec.station,
            "component": rec.component,
            "scale_factor": float(r.scale_factor),
            "match_rmse": float(r.match_error),
            "deviations": {str(k): float(v) for k, v in (r.deviations or {}).items()},
            "pga": float(rec.pga),
            "duration": float(rec.duration),
            "eff_duration": float(rec.eff_duration),
        })

    artificial = []
    for i, sig in enumerate(generated_waves or [], 1):
        artificial.append({
            "index": i,
            "type": "artificial",
            "name": sig.name or f"artificial_{i}",
            "pga": float(np.max(np.abs(sig.acc))) if sig is not None else 0.0,
            "duration": float(sig.n * sig.dt) if sig is not None else 0.0,
            "dt": float(sig.dt) if sig is not None else 0.0,
            "n": int(sig.n) if sig is not None else 0,
        })

    summary = {
        "target_spectrum": {
            "has_target": code_periods is not None and code_sa is not None,
            "n_points": int(len(code_periods)) if code_periods is not None else 0,
        },
        "natural_count": len(natural),
        "artificial_count": len(artificial),
        "total_count": len(natural) + len(artificial),
        "natural": natural,
        "artificial": artificial,
    }
    return summary
