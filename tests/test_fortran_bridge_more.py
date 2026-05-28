import numpy as np


class TestFortranBridgeFallback:
    def test_spectrum_mixed_fallback(self, monkeypatch):
        import seiswave.core.fortran_bridge as fb
        from seiswave.core.generator import WaveGenerator

        called = {}

        def fake_spamixed(acc, dt, zeta, periods, n):
            called["args"] = (acc.copy(), dt, zeta, periods.copy(), n)
            return np.full(n, 0.5), np.arange(n, dtype=np.int32)

        monkeypatch.setattr(fb, "HAS_FORTRAN", False)
        monkeypatch.setattr(WaveGenerator, "_spamixed", staticmethod(fake_spamixed))

        acc = [0, 1, 2]
        periods = [0.1, 0.5]
        sa, spi = fb.spectrum_mixed(acc, 0.02, 0.05, periods)

        assert np.allclose(sa, 0.5)
        assert np.array_equal(spi, np.array([0, 1], dtype=np.int32))
        assert called["args"][1] == 0.02
        assert called["args"][2] == 0.05
        assert np.array_equal(called["args"][3], np.array([0.1, 0.5]))
        assert called["args"][4] == 2

    def test_spectrum_avd_fallback(self, monkeypatch):
        import seiswave.core.fortran_bridge as fb
        from seiswave.core.spectrum import Spectra

        class FakeSp:
            def __init__(self):
                self.sa = np.array([1.0, 2.0])
                self.sv = np.array([3.0, 4.0])
                self.sd = np.array([5.0, 6.0])
                self.se = np.array([7.0, 8.0])

        called = {}

        def fake_compute(acc, dt, periods, zeta, method="mixed"):
            called["args"] = (np.asarray(acc), dt, np.asarray(periods), zeta, method)
            return FakeSp()

        monkeypatch.setattr(fb, "HAS_FORTRAN", False)
        monkeypatch.setattr(Spectra, "compute", staticmethod(fake_compute))

        sa, spi, sv, sd, se = fb.spectrum_avd([1, 2], 0.02, 0.05, [0.1, 0.5])
        assert np.array_equal(sa, np.array([1.0, 2.0]))
        assert np.array_equal(spi, np.ones(2, dtype=np.int32))
        assert np.array_equal(sv, np.array([3.0, 4.0]))
        assert np.array_equal(sd, np.array([5.0, 6.0]))
        assert np.array_equal(se, np.array([7.0, 8.0]))
        assert called["args"][4] == "mixed"

    def test_fit_spectra_fallback(self, monkeypatch):
        import seiswave.core.fortran_bridge as fb
        from seiswave.core.generator import WaveGenerator

        def fake_fit(acc, nacc, dt, zeta, periods, nper, target, tol, max_iter, peak, _):
            assert nacc == 3
            assert nper == 2
            assert peak == 3.0
            return np.array([9.0, 8.0, 7.0]), {"ok": True}

        monkeypatch.setattr(fb, "HAS_FORTRAN", False)
        monkeypatch.setattr(WaveGenerator, "_fitspectra", staticmethod(fake_fit))

        out = fb.fit_spectra(np.array([1.0, -2.0, 3.0]), 0.01, 0.05, [0.1, 0.5], [1.0, 2.0])
        assert np.array_equal(out, np.array([9.0, 8.0, 7.0]))

    def test_adjust_spectra_fallback(self, monkeypatch):
        import seiswave.core.fortran_bridge as fb
        from seiswave.core.generator import WaveGenerator

        def fake_adjust(acc, nacc, dt, zeta, periods, nper, target, tol, max_iter, _):
            assert nacc == 2
            assert nper == 2
            return np.array([4.0, 5.0]), {"ok": True}

        monkeypatch.setattr(fb, "HAS_FORTRAN", False)
        monkeypatch.setattr(WaveGenerator, "_adjustspectra", staticmethod(fake_adjust))

        out = fb.adjust_spectra(np.array([1.0, 2.0]), 0.01, 0.05, [0.1, 0.5], [1.0, 2.0])
        assert np.array_equal(out, np.array([4.0, 5.0]))

    def test_init_art_wave_fallback(self, monkeypatch):
        import seiswave.core.fortran_bridge as fb
        from seiswave.core.generator import WaveGenerator

        def fake_init(n, dt, zeta, periods, target, nper):
            assert n == 6
            assert nper == 2
            return np.arange(n, dtype=float)

        monkeypatch.setattr(fb, "HAS_FORTRAN", False)
        monkeypatch.setattr(WaveGenerator, "_init_art_wave", staticmethod(fake_init))

        out = fb.init_art_wave(6, 0.01, 0.05, [0.1, 0.5], [1.0, 2.0])
        assert np.array_equal(out, np.arange(6, dtype=float))

    def test_newmark_response_fallback(self, monkeypatch):
        import seiswave.core.fortran_bridge as fb
        from seiswave.core.spectrum import Spectra

        def fake_newmark(acc, dt, period, zeta):
            return np.array([1.0]), np.array([2.0]), np.array([3.0])

        monkeypatch.setattr(fb, "HAS_FORTRAN", False)
        monkeypatch.setattr(Spectra, "_newmark_beta", staticmethod(fake_newmark))

        ra, rv, rd = fb.newmark_response([1.0, 2.0], 0.01, 0.05, 1.0)
        assert np.array_equal(ra, np.array([1.0]))
        assert np.array_equal(rv, np.array([2.0]))
        assert np.array_equal(rd, np.array([3.0]))

    def test_acc2vd_python_path(self, monkeypatch):
        import seiswave.core.fortran_bridge as fb

        monkeypatch.setattr(fb, "HAS_FORTRAN", False)
        acc = np.array([1.0, 1.0, 1.0])
        v, d = fb.acc2vd(acc, 1.0, v0=2.0, d0=3.0)

        assert np.allclose(v, np.array([2.0, 3.0, 4.0]))
        assert np.allclose(d, np.array([3.0, 5.5, 9.0]))
