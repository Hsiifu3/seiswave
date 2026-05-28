import numpy as np


def test_build_selection_summary_handles_none_inputs():
    from seiswave.core import build_selection_summary

    summary = build_selection_summary(None, None)

    assert summary["natural_count"] == 0
    assert summary["artificial_count"] == 0
    assert summary["total_count"] == 0
    assert summary["target_spectrum"]["has_target"] is False
    assert summary["target_spectrum"]["n_points"] == 0


def test_build_selection_summary_target_without_wave_lists():
    from seiswave.core import build_selection_summary

    periods = np.array([0.1, 0.2, 0.3])
    sa = np.array([0.4, 0.5, 0.6])
    summary = build_selection_summary([], [], periods, sa)

    assert summary["target_spectrum"]["has_target"] is True
    assert summary["target_spectrum"]["n_points"] == 3
