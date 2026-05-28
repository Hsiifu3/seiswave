import numpy as np
import pytest

from seiswave.core import EQSignal, Filter, correct_baseline


class TestCorrectBaselineMore:
    def test_array_requires_dt(self):
        with pytest.raises(ValueError, match="必须提供 dt"):
            correct_baseline(np.array([1.0, 2.0]), method="poly")

    def test_array_bilinear_path(self):
        acc = np.array([0.0, 0.5, 1.0, 0.2, -0.3], dtype=float)
        corrected = correct_baseline(acc, dt=0.02, method="bilinear")
        assert isinstance(corrected, np.ndarray)
        assert corrected.shape == acc.shape

    def test_signal_copy_false_modifies_in_place(self):
        t = np.arange(400) * 0.02
        sig = EQSignal(0.1 * t + 0.01 * np.sin(t), dt=0.02, name="s")
        out = correct_baseline(sig, method="poly", order=1, copy=False)
        assert out is sig
        assert len(sig.vel) == sig.n
        assert abs(np.mean(sig.acc)) < 0.05

    def test_unknown_method_raises_for_array_and_signal(self):
        with pytest.raises(ValueError, match="未知的基线校正方法"):
            correct_baseline(np.array([1.0, 2.0]), dt=0.01, method="weird")

        sig = EQSignal(np.array([0.0, 0.1, 0.2]), dt=0.01)
        with pytest.raises(ValueError, match="未知的基线校正方法"):
            correct_baseline(sig, method="weird")


class TestButterworthMore:
    def test_lowpass_and_highpass_scalar_and_tuple_freqs(self):
        dt = 0.01
        t = np.arange(2000) * dt
        sig = np.sin(2 * np.pi * 2 * t) + 0.8 * np.sin(2 * np.pi * 20 * t)

        low_scalar = Filter.butterworth(sig, dt, "lowpass", 4, 5.0)
        low_tuple = Filter.butterworth(sig, dt, "lowpass", 4, (1.0, 5.0))
        high_scalar = Filter.butterworth(sig, dt, "highpass", 4, 5.0)
        high_tuple = Filter.butterworth(sig, dt, "highpass", 4, (5.0, 20.0))

        assert low_scalar.shape == sig.shape
        assert low_tuple.shape == sig.shape
        assert high_scalar.shape == sig.shape
        assert high_tuple.shape == sig.shape
        assert not np.allclose(low_scalar, high_scalar)

    def test_default_freqs_work_for_all_types(self):
        dt = 0.01
        sig = np.sin(np.linspace(0, 10, 1000))

        bp = Filter.butterworth(sig, dt, "bandpass", 2, None)
        lp = Filter.butterworth(sig, dt, "lowpass", 2, None)
        hp = Filter.butterworth(sig, dt, "highpass", 2, None)

        assert bp.shape == sig.shape
        assert lp.shape == sig.shape
        assert hp.shape == sig.shape

    def test_unknown_filter_type_raises(self):
        with pytest.raises(ValueError, match="未知的滤波类型"):
            Filter.butterworth(np.array([0.0, 1.0, 0.0]), 0.01, "nope", 2, 1.0)


class TestFFTFilter:
    def test_fft_filter_removes_out_of_band_content(self):
        dt = 0.01
        n = 2000
        t = np.arange(n) * dt
        sig = np.sin(2 * np.pi * 2 * t) + np.sin(2 * np.pi * 20 * t)

        filtered = Filter.fft_filter(sig, dt, cutoff_low=1.0, cutoff_high=5.0)

        fft_orig = np.abs(np.fft.rfft(sig))
        fft_filt = np.abs(np.fft.rfft(filtered))
        freqs = np.fft.rfftfreq(n, dt)
        idx_2 = np.argmin(np.abs(freqs - 2))
        idx_20 = np.argmin(np.abs(freqs - 20))

        assert fft_filt[idx_2] > fft_filt[idx_20] * 5
        assert fft_filt[idx_20] < fft_orig[idx_20] * 0.2
