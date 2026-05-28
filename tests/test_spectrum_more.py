import numpy as np
import pytest

from seiswave.core import Spectra
import seiswave.core.fortran_bridge as fortran_bridge


class TestSpectraMore:
    def test_default_periods_mixed_short_p1_ge_1(self):
        p = Spectra.default_periods(1.5, 3.0, 10, mode="mixed")
        assert len(p) == 10
        assert p[0] == pytest.approx(1.5)
        assert p[-1] == pytest.approx(3.0)
        # When p1 >= 1.0, should be linear
        diffs = np.diff(p)
        assert np.allclose(diffs, diffs[0], rtol=1e-3)

    def test_default_periods_mixed_long_p2_le_1(self):
        p = Spectra.default_periods(0.01, 0.5, 10, mode="mixed")
        assert len(p) == 10
        assert p[0] == pytest.approx(0.01)
        assert p[-1] == pytest.approx(0.5)
        # Should be log spaced
        log_diffs = np.diff(np.log10(p))
        assert np.allclose(log_diffs, log_diffs[0], rtol=1e-3)

    def test_default_periods_mixed_crossover(self):
        p = Spectra.default_periods(0.01, 3.0, 11, mode="mixed")
        assert len(p) == 11
        assert p[0] == pytest.approx(0.01)
        assert p[-1] == pytest.approx(3.0)
        # There should be a 1.0 crossover point
        assert any(np.isclose(p, 1.0, atol=0.05))

    def test_compute_newmark_and_freq_methods(self):
        dt = 0.01
        n = 512
        t = np.arange(n) * dt
        acc = 0.3 * np.sin(2 * np.pi * 2 * t)
        periods = np.array([0.1, 0.5, 1.0, 2.0])

        sp_newmark = Spectra.compute(acc, dt, periods, method="newmark")
        sp_freq = Spectra.compute(acc, dt, periods, method="freq")

        assert sp_newmark.sa.shape == (4,)
        assert sp_freq.sa.shape == (4,)
        # Results should be different methods but both valid
        assert np.all(sp_newmark.sa > 0)
        assert np.all(sp_freq.sa > 0)

    def test_compute_mixed_python_path(self, monkeypatch):
        dt = 0.01
        n = 512
        t = np.arange(n) * dt
        acc = 0.3 * np.sin(2 * np.pi * 2 * t)
        periods = np.array([0.05, 0.5, 2.0])

        calls = []
        monkeypatch.setattr(Spectra, "_freq_domain", staticmethod(lambda a, d, T, z: (calls.append(("freq", T)) or np.zeros_like(a), np.ones_like(a) * 0.1, np.ones_like(a) * 0.01)))
        monkeypatch.setattr(Spectra, "_newmark_beta", staticmethod(lambda a, d, T, z, *args, **kw: (calls.append(("newmark", T)) or np.zeros_like(a), np.ones_like(a) * 0.2, np.ones_like(a) * 0.02)))
        # Patch the module attribute so the local import inside compute() sees False
        monkeypatch.setattr(fortran_bridge, "HAS_FORTRAN", False)

        sp = Spectra.compute(acc, dt, periods, method="mixed")

        assert sp.sa.shape == (3,)
        assert any(tag == "freq" for tag, _ in calls)
        assert any(tag == "newmark" for tag, _ in calls)

    def test_save_csv_writes_expected_columns(self, tmp_path):
        periods = np.array([0.1, 0.5])
        sp = Spectra(periods, zeta=0.05)
        sp.sa = np.array([0.2, 0.3])
        sp.sv = np.array([0.1, 0.15])
        sp.sd = np.array([0.05, 0.08])
        sp.se = np.array([0.01, 0.02])

        path = str(tmp_path / "spec.csv")
        sp.save_csv(path)
        text = open(path).read()
        assert "period,sa,sv,sd,se" in text
        assert "1.0000000E-01" in text

    def test_str_and_repr(self):
        sp = Spectra(np.array([0.1, 0.5]), 0.05)
        assert "Spectra(n_periods=2" in str(sp)
        assert repr(sp) == str(sp)
