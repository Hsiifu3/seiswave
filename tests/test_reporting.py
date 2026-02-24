import numpy as np


def test_build_selection_summary_counts():
    from seiswave.core import build_selection_summary
    from seiswave.core.peer_db import PeerRecord
    from seiswave.core.selector import SelectionResult
    from seiswave.core.signal import EQSignal

    rec = PeerRecord(rsn=1, event="E", station="S", component="H1", pga=0.2, duration=20.0, eff_duration=12.0)
    rec.sa = np.array([0.1, 0.2])
    result = SelectionResult(record=rec, scale_factor=1.5, match_error=0.12, deviations={1.0: 0.1})
    sig = EQSignal(np.array([0.0, 0.1, -0.2]), 0.02, name="A1")

    s = build_selection_summary([result], [sig], np.array([0.1, 0.2]), np.array([0.3, 0.4]))
    assert s["natural_count"] == 1
    assert s["artificial_count"] == 1
    assert s["total_count"] == 2
    assert s["natural"][0]["rsn"] == 1
