import numpy as np
import pytest

from seiswave.core import FFT


class TestFFTMore:
    def test_welch_psd_uses_boxcar_window(self, monkeypatch):
        dt = 0.02
        acc = np.sin(np.linspace(0, 2, 12))
        captured = {}

        def fake_welch(acc_arg, fs, window, nperseg, noverlap, nfft):
            captured["args"] = (fs, window, nperseg, noverlap, nfft)
            return np.array([0.0]), np.array([1.0])

        monkeypatch.setattr("seiswave.core.fft.signal.welch", fake_welch)
        freqs, psd = FFT.welch_psd(acc, dt, overlap=0.25, window=False)

        assert len(freqs) == len(psd)
        assert freqs[0] == 0.0
        assert np.all(psd >= 0)
        assert captured["args"] == (1.0 / dt, "boxcar", 8, 2, 8)

    def test_phase_spectrum_returns_matching_lengths_and_expected_phase(self):
        dt = 0.01
        f0 = 3.0
        t = np.arange(0, 4, dt)
        acc = np.sin(2 * np.pi * f0 * t)

        freqs, phase = FFT.phase_spectrum(acc, dt)
        _, amp = FFT.amplitude_spectrum(acc, dt)
        peak_freq = freqs[np.argmax(amp)]

        assert len(freqs) == len(phase)
        assert peak_freq == pytest.approx(f0, abs=0.5)
        assert np.all(phase <= np.pi)
        assert np.all(phase >= -np.pi)

    def test_phase_spectrum_peak_frequency_matches_input(self):
        dt = 0.01
        f0 = 7.0
        t = np.arange(0, 2, dt)
        acc = np.cos(2 * np.pi * f0 * t)

        freqs, phase = FFT.phase_spectrum(acc, dt)
        _, amp = FFT.amplitude_spectrum(acc, dt)
        peak_freq = freqs[np.argmax(amp)]

        assert len(freqs) == len(phase)
        assert peak_freq == pytest.approx(f0, abs=0.5)
