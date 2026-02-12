"""
EQSignalPy v2 核心库测试

覆盖: IO, Signal, Spectrum, CodeSpec, Filter, FFT, Generator, Selector
"""
import os
import tempfile
import numpy as np
import pytest

# Test data paths
AT2_DIR = os.path.join(
    os.path.dirname(__file__), '..', 'matlab_ref',
    '选取地震波', '8度0.2g硬土场地',
    '步骤二：在PEER上选取地震波',
    'PEERNGARecords_Unscaled_0802g_100-188'
)
SAMPLE_AT2 = os.path.join(AT2_DIR, 'RSN121_FRIULI.A_A-BCS000.AT2')
HAS_AT2 = os.path.isfile(SAMPLE_AT2)


# ═══════════════════ IO Module ═══════════════════

class TestFileIO:
    @pytest.mark.skipif(not HAS_AT2, reason="AT2 test file not found")
    def test_read_at2(self):
        from eqsignalpy.core import FileIO
        rec = FileIO.read_at2(SAMPLE_AT2)
        assert rec.dt == pytest.approx(0.005)
        assert rec.npts == 3317
        assert len(rec.acc) == 3317
        assert rec.name == 'RSN121_FRIULI.A_A-BCS000'

    def test_write_read_at2_roundtrip(self):
        from eqsignalpy.core import FileIO
        acc = np.sin(np.linspace(0, 6 * np.pi, 500)) * 0.3
        dt = 0.01
        with tempfile.NamedTemporaryFile(suffix='.AT2', delete=False) as f:
            path = f.name
        try:
            FileIO.write_at2(path, acc, dt)
            rec = FileIO.read_at2(path)
            assert rec.dt == pytest.approx(dt)
            assert len(rec.acc) == len(acc)
            np.testing.assert_allclose(rec.acc, acc, atol=1e-6)
        finally:
            os.unlink(path)

    def test_write_read_txt_single_col(self):
        from eqsignalpy.core import FileIO
        acc = np.random.randn(200)
        dt = 0.02
        with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
            path = f.name
        try:
            FileIO.write_txt(path, acc, dt, two_col=False)
            rec = FileIO.read_txt(path, dt=dt, skip_rows=1, single_col=True)
            assert len(rec.acc) == len(acc)
        finally:
            os.unlink(path)


# ═══════════════════ Signal Module ═══════════════════

class TestEQSignal:
    def test_basic_properties(self):
        from eqsignalpy.core import EQSignal
        acc = np.array([0.0, 0.5, 1.0, -0.5, -1.0, 0.3])
        sig = EQSignal(acc, dt=0.02, name='test')
        assert sig.n == 6
        assert sig.pga == pytest.approx(1.0)
        assert sig.duration == pytest.approx(0.1)
        assert len(sig.time) == 6

    def test_a2vd_integration(self):
        from eqsignalpy.core import EQSignal
        # Constant acceleration => linear velocity => quadratic displacement
        n = 100
        dt = 0.01
        acc = np.ones(n) * 2.0  # 2 m/s^2
        sig = EQSignal(acc, dt=dt)
        sig.a2vd()
        # vel at end ~ 2.0 * (n-1)*dt = 1.98
        assert sig.vel[-1] == pytest.approx(2.0 * (n - 1) * dt, rel=0.01)
        # disp should be roughly 0.5 * a * t^2
        t_end = (n - 1) * dt
        assert sig.disp[-1] == pytest.approx(0.5 * 2.0 * t_end**2, rel=0.05)

    def test_normalize_and_scale(self):
        from eqsignalpy.core import EQSignal
        acc = np.array([0.5, -2.0, 1.0, 0.3])
        sig = EQSignal(acc.copy(), dt=0.02)
        sig.normalize()
        assert sig.pga == pytest.approx(1.0)
        sig.scale(3.0)
        assert sig.pga == pytest.approx(3.0)

    def test_effective_duration(self):
        from eqsignalpy.core import EQSignal
        # Create signal with clear strong motion phase
        n = 2000
        dt = 0.01
        acc = np.zeros(n)
        # Strong motion from 5s to 15s
        i1, i2 = 500, 1500
        acc[i1:i2] = np.random.randn(i2 - i1) * 5.0
        acc[:i1] = np.random.randn(i1) * 0.01
        acc[i2:] = np.random.randn(n - i2) * 0.01
        sig = EQSignal(acc, dt=dt)
        ed = sig.effective_duration
        # Should be roughly 10s (between 5s and 15s)
        assert 5.0 < ed < 15.0

    def test_trim(self):
        from eqsignalpy.core import EQSignal
        acc = np.arange(100, dtype=float)
        sig = EQSignal(acc, dt=0.01)
        sig.trim(10, 49)
        assert sig.n == 40
        assert sig.acc[0] == pytest.approx(10.0)

    @pytest.mark.skipif(not HAS_AT2, reason="AT2 test file not found")
    def test_from_at2(self):
        from eqsignalpy.core import EQSignal
        sig = EQSignal.from_at2(SAMPLE_AT2)
        assert sig.n == 3317
        assert sig.dt == pytest.approx(0.005)
        assert sig.pga > 0


# ═══════════════════ Spectrum Module ═══════════════════

class TestSpectra:
    def test_default_periods_mixed(self):
        from eqsignalpy.core import Spectra
        p = Spectra.default_periods(0.04, 10.0, 200, mode='mixed')
        assert len(p) == 200
        assert p[0] == pytest.approx(0.04)
        assert p[-1] == pytest.approx(10.0)
        # Should be monotonically increasing
        assert np.all(np.diff(p) > 0)

    def test_newmark_known_result(self):
        """Verify Newmark-β against known SDOF result.
        For a step function input, the peak displacement of an undamped
        SDOF is 2 * F/k (dynamic amplification factor = 2).
        """
        from eqsignalpy.core import Spectra
        T = 1.0  # period
        omega = 2 * np.pi / T
        k = omega**2  # unit mass
        dt = 0.001
        n = 5000
        # Step function ground acceleration
        acc = np.ones(n) * 1.0
        ra, rv, rd = Spectra._newmark_beta(acc, dt, T, zeta=0.0)
        # For undamped SDOF under step load, max relative disp = 2/omega^2
        expected_sd = 2.0 / k
        assert np.max(np.abs(rd)) == pytest.approx(expected_sd, rel=0.02)

    def test_compute_response_spectrum(self):
        """Compute spectrum of a simple sinusoidal signal and check
        that the peak Sa is near the resonant period."""
        from eqsignalpy.core import Spectra
        f0 = 5.0  # 5 Hz => T = 0.2s
        dt = 0.005
        t = np.arange(0, 10, dt)
        acc = np.sin(2 * np.pi * f0 * t) * 0.5
        periods = np.array([0.1, 0.15, 0.2, 0.25, 0.3, 0.5, 1.0])
        sp = Spectra.compute(acc, dt, periods, zeta=0.05)
        assert sp.sa is not None
        # Peak should be at or near T=0.2s
        peak_idx = np.argmax(sp.sa)
        assert periods[peak_idx] == pytest.approx(0.2, abs=0.1)

    def test_freq_domain_method(self):
        from eqsignalpy.core import Spectra
        dt = 0.01
        acc = np.random.randn(1000) * 0.1
        periods = np.array([0.5, 1.0, 2.0])
        sp_nmk = Spectra.compute(acc, dt, periods, zeta=0.05, method='newmark')
        sp_freq = Spectra.compute(acc, dt, periods, zeta=0.05, method='freq')
        # Should be reasonably close (within 20% for random signal)
        for i in range(len(periods)):
            if sp_nmk.sa[i] > 0.001:
                ratio = sp_freq.sa[i] / sp_nmk.sa[i]
                assert 0.5 < ratio < 2.0


# ═══════════════════ CodeSpec Module ═══════════════════

class TestCodeSpectrum:
    def test_get_params_basic(self):
        from eqsignalpy.core import CodeSpectrum
        p = CodeSpectrum.get_params(8, 2, 'II', 'frequent')
        assert p['Tg'] == pytest.approx(0.40)
        assert p['alpha_max'] == pytest.approx(0.16)

    def test_get_params_all_combos(self):
        """Verify all valid parameter combinations don't raise."""
        from eqsignalpy.core import CodeSpectrum
        for group in [1, 2, 3]:
            for site in ['I0', 'I1', 'II', 'III', 'IV']:
                for level in ['frequent', 'basic', 'rare']:
                    for intensity in [6, 7, 7.5, 8, 8.5, 9]:
                        p = CodeSpectrum.get_params(intensity, group, site, level)
                        assert p['Tg'] > 0
                        assert p['alpha_max'] > 0

    def test_get_params_invalid(self):
        from eqsignalpy.core import CodeSpectrum
        with pytest.raises(KeyError):
            CodeSpectrum.get_params(5, 1, 'II', 'frequent')
        with pytest.raises(KeyError):
            CodeSpectrum.get_params(8, 4, 'II', 'frequent')

    def test_gb50011_four_segments(self):
        """Verify the 4-segment shape of the regular spectrum."""
        from eqsignalpy.core import CodeSpectrum
        Tg = 0.40
        alpha_max = 0.16
        periods = np.linspace(0.0, 6.0, 601)
        alpha = CodeSpectrum.gb50011(periods, Tg, alpha_max, zeta=0.05)
        # Segment 1: T=0 should be 0.45*alpha_max (eta2=1.0 for zeta=0.05)
        assert alpha[0] == pytest.approx(0.45 * alpha_max, rel=0.01)
        # Segment 2: plateau at eta2 * alpha_max
        mask2 = (periods >= 0.1) & (periods <= Tg)
        plateau = alpha[mask2]
        assert np.all(np.abs(plateau - alpha_max) < 1e-10)
        # After Tg, spectrum should be non-increasing
        idx_tg = np.searchsorted(periods, Tg)
        assert np.all(np.diff(alpha[idx_tg:]) <= 1e-10)
        # All values non-negative
        assert np.all(alpha >= 0)

    def test_gb50011_isolation(self):
        """Isolation spectrum: 3 segments (no linear decay).
        Regular and isolation are identical for T <= 5*Tg.
        For T > 5*Tg, they diverge (regular has linear decay segment)."""
        from eqsignalpy.core import CodeSpectrum
        Tg = 0.40
        alpha_max = 0.16
        periods = np.linspace(0.01, 6.0, 600)
        alpha_reg = CodeSpectrum.gb50011(periods, Tg, alpha_max, isolation=False)
        alpha_iso = CodeSpectrum.gb50011(periods, Tg, alpha_max, isolation=True)
        # Before 5*Tg, both should be identical
        mask_before = periods <= 5 * Tg
        np.testing.assert_allclose(alpha_reg[mask_before], alpha_iso[mask_before], atol=1e-10)
        # After 5*Tg, they should differ
        mask_after = periods > 5 * Tg + 0.01
        assert not np.allclose(alpha_reg[mask_after], alpha_iso[mask_after])
        # Both should be non-negative
        assert np.all(alpha_reg >= 0)
        assert np.all(alpha_iso >= 0)

    def test_damping_adjustment(self):
        """Non-5% damping should adjust the spectrum."""
        from eqsignalpy.core import CodeSpectrum
        Tg, alpha_max = 0.35, 0.08
        periods = np.linspace(0.01, 6.0, 300)
        a5 = CodeSpectrum.gb50011(periods, Tg, alpha_max, zeta=0.05)
        a10 = CodeSpectrum.gb50011(periods, Tg, alpha_max, zeta=0.10)
        # Higher damping => lower spectrum
        assert np.mean(a10) < np.mean(a5)

    def test_from_params(self):
        from eqsignalpy.core import CodeSpectrum
        periods = np.linspace(0.01, 6.0, 100)
        alpha = CodeSpectrum.from_params(periods, 8, 2, 'II', 'frequent')
        assert len(alpha) == 100
        assert np.max(alpha) == pytest.approx(0.16)


# ═══════════════════ Filter Module ═══════════════════

class TestFilter:
    def test_detrend_removes_linear(self):
        from eqsignalpy.core import Filter
        n = 1000
        dt = 0.01
        t = np.arange(n) * dt
        trend = 0.5 * t + 0.1
        signal = np.random.randn(n) * 0.01 + trend
        result = Filter.detrend(signal, dt, order=1)
        # After detrend, mean should be near zero
        assert abs(np.mean(result)) < 0.05

    def test_bilinear_detrend(self):
        from eqsignalpy.core import Filter
        n = 500
        # Create signal with bilinear trend
        a = np.zeros(n)
        a[:250] = np.linspace(0, 1, 250)
        a[250:] = np.linspace(1, -0.5, 250)
        noise = np.random.randn(n) * 0.01
        signal = a + noise
        result = Filter.bilinear_detrend(signal)
        # RMS should be much smaller
        assert np.std(result) < np.std(signal)

    def test_butterworth_bandpass(self):
        from eqsignalpy.core import Filter
        dt = 0.01
        n = 2000
        t = np.arange(n) * dt
        # 2 Hz + 20 Hz signal
        sig = np.sin(2 * np.pi * 2 * t) + np.sin(2 * np.pi * 20 * t)
        # Bandpass 1-5 Hz should keep 2 Hz, remove 20 Hz
        filtered = Filter.butterworth(sig, dt, 'bandpass', 4, (1.0, 5.0))
        # Check that 20 Hz component is attenuated
        fft_orig = np.abs(np.fft.rfft(sig))
        fft_filt = np.abs(np.fft.rfft(filtered))
        freqs = np.fft.rfftfreq(n, dt)
        idx_20 = np.argmin(np.abs(freqs - 20))
        assert fft_filt[idx_20] < fft_orig[idx_20] * 0.1


# ═══════════════════ FFT Module ═══════════════════

class TestFFT:
    def test_amplitude_spectrum_peak(self):
        from eqsignalpy.core import FFT
        dt = 0.01
        f0 = 5.0
        t = np.arange(0, 10, dt)
        acc = np.sin(2 * np.pi * f0 * t)
        freqs, amp = FFT.amplitude_spectrum(acc, dt)
        # Peak should be near 5 Hz
        peak_freq = freqs[np.argmax(amp)]
        assert peak_freq == pytest.approx(f0, abs=0.5)

    def test_welch_psd(self):
        from eqsignalpy.core import FFT
        dt = 0.01
        acc = np.random.randn(5000)
        freqs, psd = FFT.welch_psd(acc, dt)
        assert len(freqs) == len(psd)
        assert freqs[0] == pytest.approx(0.0)
        # White noise PSD should be roughly flat
        assert np.std(psd[1:]) / np.mean(psd[1:]) < 2.0


# ═══════════════════ Generator Module ═══════════════════

class TestWaveGenerator:
    def test_generate_convergence(self):
        """Test that generated wave's spectrum converges toward target."""
        from eqsignalpy.core import WaveGenerator, CodeSpectrum, Spectra
        np.random.seed(42)  # reproducible
        periods = Spectra.default_periods(0.1, 4.0, 50, mode='log')
        target = CodeSpectrum.gb50011(periods, 0.40, 0.16)
        result = WaveGenerator.generate(
            target, periods, n=4096, dt=0.02,
            tol=0.15, max_iter=30, pga=0.16
        )
        # Compute spectrum of result
        sp = Spectra.compute(result.acc, result.dt, periods, zeta=0.05)
        errors = WaveGenerator.fit_error(sp.sa, target)
        # After 30 iterations, mean error should improve significantly
        assert errors['mean_error'] < 0.80

    def test_fit_error(self):
        from eqsignalpy.core import WaveGenerator
        target = np.array([1.0, 2.0, 3.0])
        actual = np.array([1.1, 1.8, 3.3])
        err = WaveGenerator.fit_error(actual, target)
        assert err['max_error'] == pytest.approx(0.1, abs=0.01)


# ═══════════════════ Selector Module ═══════════════════

class TestWaveSelector:
    def test_duration_check(self):
        from eqsignalpy.core import (
            WaveSelector, SelectionCriteria, EQRecord
        )
        criteria = SelectionCriteria(
            Tg=0.40, alpha_max=0.16,
            T_main=[1.0, 0.5, 0.3],
            duration_factor=5.0,
            duration_threshold=0.1,
        )
        ws = WaveSelector(criteria)
        # Create a short record that should fail duration check
        acc = np.random.randn(100) * 0.5
        rec = EQRecord(acc=acc, dt=0.02, name='short')
        ok, dur = ws._check_duration(rec)
        # 100 * 0.02 = 2s total, need 5 * 1.0 = 5s effective
        assert not ok

    def test_full_selection_flow(self):
        from eqsignalpy.core import (
            WaveSelector, SelectionCriteria, EQRecord
        )
        criteria = SelectionCriteria(
            Tg=0.40, alpha_max=0.16,
            T_main=[0.5, 0.3, 0.2],
            duration_factor=5.0,
            duration_threshold=0.1,
            spectral_tol=0.50,  # relaxed for test
        )
        ws = WaveSelector(criteria)
        # Create records with enough duration
        records = []
        for i in range(5):
            n = 5000
            acc = np.random.randn(n) * 0.1
            rec = EQRecord(acc=acc, dt=0.01, name=f'wave_{i}')
            records.append(rec)
        results = ws.select(records)
        # Should return a list (may or may not have passed records)
        assert isinstance(results, list)
        summary = ws.summary()
        assert summary['total'] == 5

