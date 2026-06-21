"""TargetSpectrumService 单元测试。"""

from pathlib import Path

import numpy as np
import pytest

from seiswave.core.code_spec import CodeSpectrum
from seiswave.core.signal_pool import SignalRecord
from seiswave.core.spectrum import Spectra
from seiswave.core.target_spectrum import TargetSpectrumService


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtCore import QCoreApplication

    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication([])
    yield app


class TestTargetSpectrumService:
    def test_set_code_gb50011_matches_code_spectrum(self, qapp):
        periods = np.array([0.1, 0.5, 1.0], dtype=np.float64)
        service = TargetSpectrumService(periods=periods)
        hits = {"count": 0}
        service.target_changed.connect(
            lambda: hits.__setitem__("count", hits["count"] + 1)
        )

        service.set_code(
            "GB50011",
            intensity=8,
            group=2,
            site_class="II",
            level="basic",
            zeta=0.05,
        )

        expected = CodeSpectrum.from_params(
            periods,
            8,
            2,
            "II",
            "basic",
            zeta=0.05,
        )

        np.testing.assert_allclose(service.periods(), periods)
        np.testing.assert_allclose(service.sa(), expected)
        assert "GB50011" in service.describe()
        assert hits["count"] == 1

    def test_three_sources_all_emit_target_changed(self, qapp):
        periods = np.array([0.1, 0.5, 1.0], dtype=np.float64)
        service = TargetSpectrumService(periods=periods)
        hits = {"count": 0}
        service.target_changed.connect(
            lambda: hits.__setitem__("count", hits["count"] + 1)
        )

        service.set_code(
            "GB/T51408",
            intensity=8,
            group=2,
            site_class="II",
            level="rare",
        )

        rec = SignalRecord(
            acc=np.array([0.0, 0.1, -0.05, 0.0, 0.02], dtype=np.float64),
            dt=0.02,
            name="RSN42",
            kind="natural",
        )
        expected = rec.spectrum(periods).sa.copy()
        service.set_from_record(rec)

        np.testing.assert_allclose(service.sa(), expected)
        assert "RSN42" in service.describe()

        service.set_custom(np.array([1.0, 0.1, 0.5]), np.array([0.3, 0.1, 0.2]))
        np.testing.assert_allclose(service.periods(), [0.1, 0.5, 1.0])
        np.testing.assert_allclose(service.sa(), [0.1, 0.2, 0.3])
        assert "自定义目标谱" in service.describe()
        assert hits["count"] == 3

    def test_set_custom_from_file_round_trip(self, qapp, tmp_path):
        path = tmp_path / "target.csv"
        path.write_text("0.10,0.30\n0.50,0.20\n1.00,0.10\n", encoding="utf-8")

        service = TargetSpectrumService()
        service.set_custom(path)

        np.testing.assert_allclose(service.periods(), [0.1, 0.5, 1.0])
        np.testing.assert_allclose(service.sa(), [0.3, 0.2, 0.1])
        assert Path(path).name in service.describe()

    def test_set_from_record_uses_current_period_grid(self, qapp, monkeypatch):
        periods = np.array([0.2, 0.8], dtype=np.float64)
        service = TargetSpectrumService(periods=periods)
        record = SignalRecord(
            acc=np.array([0.0, 0.1, -0.1], dtype=np.float64),
            dt=0.02,
            name="mock_record",
            kind="natural",
        )

        def fake_spectrum(periods_arg, zeta=0.05):
            sp = Spectra(periods_arg, zeta)
            sp.sa = np.array([1.2, 0.8])
            sp.sv = np.zeros(2)
            sp.sd = np.zeros(2)
            sp.se = np.zeros(2)
            return sp

        monkeypatch.setattr(record, "spectrum", fake_spectrum)
        service.set_from_record(record)

        np.testing.assert_allclose(service.periods(), periods)
        np.testing.assert_allclose(service.sa(), [1.2, 0.8])
