import numpy as np


def test_build_selection_summary_allows_none_generated_wave():
    from seiswave.core import build_selection_summary

    summary = build_selection_summary([], [None], np.array([0.1]), np.array([0.2]))

    assert summary["artificial_count"] == 1
    assert summary["artificial"][0]["name"] == "artificial_1"
    assert summary["artificial"][0]["pga"] == 0.0
    assert summary["artificial"][0]["duration"] == 0.0
    assert summary["artificial"][0]["dt"] == 0.0
    assert summary["artificial"][0]["n"] == 0
