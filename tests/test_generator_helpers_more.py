import numpy as np
import pytest
from types import SimpleNamespace

import seiswave.core.generator as gen_mod


def test_ramixed_dispatches_to_freq_and_newmark(monkeypatch):
    WaveGenerator = gen_mod.WaveGenerator
    calls = []
    monkeypatch.setattr(WaveGenerator, "_rafreq", staticmethod(lambda acc, n, dt, zeta, P: calls.append(("freq", P)) or np.ones(n)))
    monkeypatch.setattr(WaveGenerator, "_ranmk", staticmethod(lambda acc, n, dt, zeta, P: calls.append(("time", P)) or np.zeros(n)))

    acc = np.array([0.1, 0.2, 0.3])
    out1 = WaveGenerator._ramixed(acc, 3, 0.02, 0.05, 0.1)
    out2 = WaveGenerator._ramixed(acc, 3, 0.02, 0.05, 1.0)

    assert np.all(out1 == 1.0)
    assert np.all(out2 == 0.0)
    assert calls == [("freq", 0.1), ("time", 1.0)]


def test_ramixed_batch_covers_freq_and_time(monkeypatch):
    WaveGenerator = gen_mod.WaveGenerator
    monkeypatch.setattr(WaveGenerator, "_nextpow2", staticmethod(lambda n: 4))
    monkeypatch.setattr(WaveGenerator, "_ranmk", staticmethod(lambda acc, n, dt, zeta, P: np.full(n, P)))

    acc = np.array([0.1, 0.2, 0.3, 0.4])
    periods = np.array([0.1, 1.0])
    out = WaveGenerator._ramixed_batch(acc, 4, 0.02, 0.05, periods, 2)

    assert out.shape == (2, 4)
    assert np.allclose(out[1], 1.0)


def test_error_handles_short_n_and_zero_targets():
    WaveGenerator = gen_mod.WaveGenerator
    aerr, merr = WaveGenerator._error(np.array([1.0, 2.0]), np.array([0.0, 0.0]), 2)
    assert aerr == 0.0
    assert merr == 0.0


def test_errora_and_adjust_peak():
    WaveGenerator = gen_mod.WaveGenerator
    aerr, merr = WaveGenerator._errora(np.array([2.0, 1.0]), np.array([1.0, 1.0]), 2)
    assert aerr > 0.0
    assert merr == pytest.approx(1.0)

    out = WaveGenerator._adjust_peak(np.array([0.2, -0.4, 0.1]), 0.5)
    assert np.max(np.abs(out)) == pytest.approx(0.5)

    out2 = WaveGenerator._adjust_peak(np.array([0.2, -0.8, 0.1]), 0.5)
    assert np.max(np.abs(out2)) <= 0.5 + 1e-12


def test_generate_python_fm0_single_control_point(monkeypatch):
    WaveGenerator = gen_mod.WaveGenerator
    monkeypatch.setattr(WaveGenerator, "_init_art_wave", staticmethod(lambda n, dt, zeta, P, SPAT, nP, seed=0: np.ones(n)))
    monkeypatch.setattr(WaveGenerator, "_envelope", staticmethod(lambda n, dt: np.ones(n)))
    monkeypatch.setattr(WaveGenerator, "_fitspectra", staticmethod(lambda acc, n, dt, zeta, P, nP, SPAT, tol, max_iter, peak0, progress_callback=None: (acc.copy(), 0.01)))

    sig = WaveGenerator._generate_python(
        np.array([0.5]), np.array([0.2]), 1,
        n=32, dt=0.02, zeta=0.05, peak0=0.3,
        tol=0.05, max_iter=2, fm=0, progress_callback=None,
    )

    assert sig.name == "artificial"
    assert len(sig.acc) == 32
    assert np.max(np.abs(sig.acc)) == pytest.approx(0.3)


def test_generate_python_fm1_uses_adjustspectra(monkeypatch):
    WaveGenerator = gen_mod.WaveGenerator
    monkeypatch.setattr(WaveGenerator, "_init_art_wave", staticmethod(lambda n, dt, zeta, P, SPAT, nP, seed=0: np.ones(n)))
    monkeypatch.setattr(WaveGenerator, "_envelope", staticmethod(lambda n, dt: np.ones(n)))
    monkeypatch.setattr(WaveGenerator, "_adjustspectra", staticmethod(lambda acc, n, dt, zeta, P, nP, SPAT, tol, max_iter, progress_callback=None: (acc.copy() * 0.5, 0.02)))

    sig = WaveGenerator._generate_python(
        np.array([0.5, 1.0]), np.array([0.2, 0.3]), 2,
        n=16, dt=0.02, zeta=0.05, peak0=0.4,
        tol=0.05, max_iter=2, fm=1, progress_callback=None,
    )

    assert sig.name == "artificial"
    assert len(sig.acc) == 16


def test_validate_uses_embedded_target_and_raises_without_it(monkeypatch):
    from seiswave.core.generator import NearFieldPulseGenerator

    sig = SimpleNamespace(
        acc=np.array([0.1, 0.2, 0.3]),
        dt=0.02,
        total_spectrum=np.array([0.2, 0.3]),
        spectrum_periods=np.array([0.1, 0.5]),
    )
    monkeypatch.setattr("seiswave.core.spectrum.Spectra.compute", lambda *a, **k: SimpleNamespace(sa=np.array([0.21, 0.29])))
    out = NearFieldPulseGenerator.validate(sig)
    assert "mean_error" in out

    with pytest.raises(ValueError, match="validate 需要 target_spectrum 和 periods"):
        NearFieldPulseGenerator.validate(SimpleNamespace(acc=np.array([0.1]), dt=0.02))
