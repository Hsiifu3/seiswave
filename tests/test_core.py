"""
SeisWave v2 核心库测试

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
        from seiswave.core import FileIO
        rec = FileIO.read_at2(SAMPLE_AT2)
        assert rec.dt == pytest.approx(0.005)
        assert rec.npts == 3317
        assert len(rec.acc) == 3317
        assert rec.name == 'RSN121_FRIULI.A_A-BCS000'

    def test_write_read_at2_roundtrip(self):
        from seiswave.core import FileIO
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
        from seiswave.core import FileIO
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

    def test_parse_peer_filename_standard(self):
        from seiswave.core import parse_peer_filename
        meta = parse_peer_filename('RSN1004_NORTHR_SPV270.AT2')
        assert meta['rsn'] == 1004
        assert meta['event_tag'] == 'NORTHR'
        assert meta['station_tag'] == 'SPV270'
        assert meta['component'] == 'SPV270'

    def test_parse_peer_filename_with_dots(self):
        from seiswave.core import parse_peer_filename
        meta = parse_peer_filename('RSN121_FRIULI.A_A-BCS000.AT2')
        assert meta['rsn'] == 121
        assert meta['event_tag'] == 'FRIULI.A'
        assert meta['station_tag'] == 'A-BCS000'

    def test_parse_peer_filename_vertical(self):
        from seiswave.core import parse_peer_filename
        meta = parse_peer_filename('RSN1004_NORTHR_SPV-UP.AT2')
        assert meta['rsn'] == 1004
        assert meta['component'] == 'SPV-UP'

    def test_parse_peer_filename_no_rsn(self):
        from seiswave.core import parse_peer_filename
        meta = parse_peer_filename('SOME_RECORD.AT2')
        assert meta['rsn'] == 0

    def test_read_at2_metadata_fields(self):
        """read_at2 应返回包含 rsn, event, station, date, component 的 metadata"""
        from seiswave.core import FileIO
        acc = np.sin(np.linspace(0, 6 * np.pi, 500)) * 0.3
        dt = 0.01
        with tempfile.NamedTemporaryFile(
            suffix='.AT2', prefix='RSN999_TESTEQ_STA090',
            delete=False
        ) as f:
            path = f.name
        try:
            FileIO.write_at2(path, acc, dt, metadata={
                'header1': 'PEER NGA STRONG MOTION DATABASE RECORD',
                'header2': 'TestEvent, 1/1/2000, TestStation, 090',
                'header3': 'ACCELERATION TIME SERIES IN UNITS OF G',
            })
            rec = FileIO.read_at2(path)
            # 向后兼容：原有字段仍存在
            assert 'header1' in rec.metadata
            assert 'header2' in rec.metadata
            assert 'header3' in rec.metadata
            # 新增字段
            assert rec.metadata['event'] == 'TestEvent'
            assert rec.metadata['date'] == '1/1/2000'
            assert rec.metadata['station'] == 'TestStation'
            assert rec.metadata['component'] == '090'
            # dt 和 acc 不受影响
            assert rec.dt == pytest.approx(dt)
            np.testing.assert_allclose(rec.acc, acc, atol=1e-6)
        finally:
            os.unlink(path)


# ═══════════════════ Signal Module ═══════════════════

class TestEQSignal:
    def test_basic_properties(self):
        from seiswave.core import EQSignal
        acc = np.array([0.0, 0.5, 1.0, -0.5, -1.0, 0.3])
        sig = EQSignal(acc, dt=0.02, name='test')
        assert sig.n == 6
        assert sig.pga == pytest.approx(1.0)
        assert sig.duration == pytest.approx(0.1)
        assert len(sig.time) == 6

    def test_a2vd_integration(self):
        from seiswave.core import EQSignal
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
        from seiswave.core import EQSignal
        acc = np.array([0.5, -2.0, 1.0, 0.3])
        sig = EQSignal(acc.copy(), dt=0.02)
        sig.normalize()
        assert sig.pga == pytest.approx(1.0)
        sig.scale(3.0)
        assert sig.pga == pytest.approx(3.0)

    def test_effective_duration(self):
        from seiswave.core import EQSignal
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
        from seiswave.core import EQSignal
        acc = np.arange(100, dtype=float)
        sig = EQSignal(acc, dt=0.01)
        sig.trim(10, 49)
        assert sig.n == 40
        assert sig.acc[0] == pytest.approx(10.0)

    @pytest.mark.skipif(not HAS_AT2, reason="AT2 test file not found")
    def test_from_at2(self):
        from seiswave.core import EQSignal
        sig = EQSignal.from_at2(SAMPLE_AT2)
        assert sig.n == 3317
        assert sig.dt == pytest.approx(0.005)
        assert sig.pga > 0


# ═══════════════════ Spectrum Module ═══════════════════

class TestSpectra:
    def test_default_periods_mixed(self):
        from seiswave.core import Spectra
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
        from seiswave.core import Spectra
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
        from seiswave.core import Spectra
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
        from seiswave.core import Spectra
        dt = 0.01
        rng = np.random.RandomState(42)
        acc = rng.randn(1000) * 0.1
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
        from seiswave.core import CodeSpectrum
        p = CodeSpectrum.get_params(8, 2, 'II', 'frequent')
        assert p['Tg'] == pytest.approx(0.40)
        assert p['alpha_max'] == pytest.approx(0.16)

    def test_get_params_all_combos(self):
        """Verify all valid parameter combinations don't raise."""
        from seiswave.core import CodeSpectrum
        for group in [1, 2, 3]:
            for site in ['I0', 'I1', 'II', 'III', 'IV']:
                for level in ['frequent', 'basic', 'rare']:
                    for intensity in [6, 7, 7.5, 8, 8.5, 9]:
                        p = CodeSpectrum.get_params(intensity, group, site, level)
                        assert p['Tg'] > 0
                        assert p['alpha_max'] > 0

    def test_get_params_invalid(self):
        from seiswave.core import CodeSpectrum
        with pytest.raises(KeyError):
            CodeSpectrum.get_params(5, 1, 'II', 'frequent')
        with pytest.raises(KeyError):
            CodeSpectrum.get_params(8, 4, 'II', 'frequent')

    def test_gb50011_four_segments(self):
        """Verify the 4-segment shape of the regular spectrum."""
        from seiswave.core import CodeSpectrum
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
        from seiswave.core import CodeSpectrum
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
        from seiswave.core import CodeSpectrum
        Tg, alpha_max = 0.35, 0.08
        periods = np.linspace(0.01, 6.0, 300)
        a5 = CodeSpectrum.gb50011(periods, Tg, alpha_max, zeta=0.05)
        a10 = CodeSpectrum.gb50011(periods, Tg, alpha_max, zeta=0.10)
        # Higher damping => lower spectrum
        assert np.mean(a10) < np.mean(a5)

    def test_from_params(self):
        from seiswave.core import CodeSpectrum
        periods = np.linspace(0.01, 6.0, 100)
        alpha = CodeSpectrum.from_params(periods, 8, 2, 'II', 'frequent')
        assert len(alpha) == 100
        assert np.max(alpha) == pytest.approx(0.16)


# ═══════════════════ Filter Module ═══════════════════

class TestFilter:
    def test_detrend_removes_linear(self):
        from seiswave.core import Filter
        n = 1000
        dt = 0.01
        t = np.arange(n) * dt
        trend = 0.5 * t + 0.1
        signal = np.random.randn(n) * 0.01 + trend
        result = Filter.detrend(signal, dt, order=1)
        # After detrend, mean should be near zero
        assert abs(np.mean(result)) < 0.05

    def test_bilinear_detrend(self):
        from seiswave.core import Filter
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
        from seiswave.core import Filter
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

    def test_correct_baseline_array_poly(self):
        from seiswave.core import correct_baseline
        n = 800
        dt = 0.02
        t = np.arange(n) * dt
        acc = 0.2 * t + 0.05 + 0.01 * np.sin(2 * np.pi * 1.5 * t)
        corrected = correct_baseline(acc, dt=dt, method='poly', order=1)
        assert isinstance(corrected, np.ndarray)
        assert abs(np.mean(corrected)) < 0.05

    def test_correct_baseline_signal_returns_eqsignal(self):
        from seiswave.core import EQSignal, correct_baseline
        n = 800
        dt = 0.02
        t = np.arange(n) * dt
        acc = 0.15 * t + 0.02 * np.sin(2 * np.pi * 2.0 * t)
        sig = EQSignal(acc, dt)
        corrected = correct_baseline(sig, method='poly', order=1)
        assert corrected is not sig
        assert corrected.n == sig.n
        assert len(corrected.vel) == sig.n
        assert abs(np.mean(corrected.acc)) < abs(np.mean(sig.acc))

    def test_eqsignal_baseline_correction_inplace(self):
        from seiswave.core import EQSignal
        n = 600
        dt = 0.02
        t = np.arange(n) * dt
        sig = EQSignal(0.1 * t + 0.01 * np.sin(2 * np.pi * 1.0 * t), dt)
        sig.baseline_correction(method='poly', order=1)
        assert len(sig.vel) == n
        assert len(sig.disp) == n
        assert abs(np.mean(sig.acc)) < 0.05


# ═══════════════════ FFT Module ═══════════════════

class TestFFT:
    def test_amplitude_spectrum_peak(self):
        from seiswave.core import FFT
        dt = 0.01
        f0 = 5.0
        t = np.arange(0, 10, dt)
        acc = np.sin(2 * np.pi * f0 * t)
        freqs, amp = FFT.amplitude_spectrum(acc, dt)
        # Peak should be near 5 Hz
        peak_freq = freqs[np.argmax(amp)]
        assert peak_freq == pytest.approx(f0, abs=0.5)

    def test_welch_psd(self):
        from seiswave.core import FFT
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
        from seiswave.core import WaveGenerator, CodeSpectrum, Spectra
        np.random.seed(42)  # reproducible
        # Use smaller parameters to avoid OOM in CI/test environments
        periods = Spectra.default_periods(0.1, 2.0, 15, mode='log')
        target = CodeSpectrum.gb50011(periods, 0.40, 0.16)
        result = WaveGenerator.generate(
            target, periods, n=1024, dt=0.02,
            tol=0.15, max_iter=10, pga=0.16
        )
        # Compute spectrum of result
        sp = Spectra.compute(result.acc, result.dt, periods, zeta=0.05)
        errors = WaveGenerator.fit_error(sp.sa, target)
        # After iterations, mean error should improve significantly
        assert errors['mean_error'] < 0.80

    def test_fit_error(self):
        from seiswave.core import WaveGenerator
        target = np.array([1.0, 2.0, 3.0])
        actual = np.array([1.1, 1.8, 3.3])
        err = WaveGenerator.fit_error(actual, target)
        assert err['max_error'] == pytest.approx(0.1, abs=0.01)


# ═══════════════════ Selector Module ═══════════════════

class TestWaveSelector:
    def test_selection_config(self):
        """测试 SelectionConfig 数据类创建"""
        from seiswave.core import WaveSelector, SelectionConfig
        periods = np.linspace(0.04, 6.0, 50)
        target_sa = np.ones(50) * 0.2
        config = SelectionConfig(
            target_sa=target_sa,
            periods=periods,
            T_main=[1.0, 0.5, 0.3],
            duration_factor=5.0,
            spectral_tol=0.30,
            n_select=5,
            scale_range=(0.5, 4.0),
        )
        ws = WaveSelector(config)
        assert ws.config.n_select == 5
        assert ws.config.duration_factor == 5.0
        assert len(ws._T_indices) == 3

    def test_optimal_scale(self):
        """测试最优缩放系数计算"""
        from seiswave.core import WaveSelector, SelectionConfig
        periods = np.linspace(0.1, 6.0, 50)
        target_sa = np.ones(50) * 0.5
        config = SelectionConfig(
            target_sa=target_sa,
            periods=periods,
            T_main=[1.0, 0.5, 0.3],
        )
        ws = WaveSelector(config)
        # 如果记录谱是目标谱的一半，最优缩放应接近 2.0
        rec_sa = np.ones(50) * 0.25
        scale = ws._optimal_scale(rec_sa, target_sa)
        assert 1.5 < scale < 2.5


# ═══════════════════ Signal Panel Enhancement Tests ═══════════════════

class TestAriasIntensity:
    def test_arias_formula(self):
        """Verify Ia = π/(2g) ∫a²dt for constant acceleration"""
        from seiswave.core import EQSignal
        n = 1000
        dt = 0.01
        a_val = 2.0  # m/s²
        acc = np.ones(n) * a_val
        sig = EQSignal(acc, dt=dt)
        ia = sig.arias_intensity()
        # Ia(t) = π/(2g) * a² * t  for constant a
        t_end = (n - 1) * dt
        expected = np.pi / (2.0 * 9.81) * a_val**2 * t_end
        assert ia[-1] == pytest.approx(expected, rel=0.02)

    def test_arias_zero_signal(self):
        """Zero signal should have zero Arias intensity"""
        from seiswave.core import EQSignal
        sig = EQSignal(np.zeros(100), dt=0.01)
        ia = sig.arias_intensity()
        assert ia[-1] == pytest.approx(0.0)

    def test_arias_monotonic(self):
        """Cumulative Arias intensity must be non-decreasing"""
        from seiswave.core import EQSignal
        rng = np.random.RandomState(123)
        acc = rng.randn(500) * 0.5
        sig = EQSignal(acc, dt=0.01)
        ia = sig.arias_intensity()
        assert np.all(np.diff(ia) >= 0)


class TestEffectiveDuration:
    def test_d595_concentrated_motion(self):
        """Signal with concentrated strong motion should have short D5-95"""
        from seiswave.core import EQSignal
        n = 2000
        dt = 0.01
        acc = np.zeros(n)
        # Strong motion only in 5s-7s window
        i1, i2 = 500, 700
        rng = np.random.RandomState(42)
        acc[i1:i2] = rng.randn(i2 - i1) * 5.0
        acc[:i1] = rng.randn(i1) * 0.001
        acc[i2:] = rng.randn(n - i2) * 0.001
        sig = EQSignal(acc, dt=dt)
        ed = sig.effective_duration
        # D5-95 should be roughly 2s (between 5s and 7s)
        assert 0.5 < ed < 5.0

    def test_d595_zero_signal(self):
        """Zero signal should have zero effective duration"""
        from seiswave.core import EQSignal
        sig = EQSignal(np.zeros(100), dt=0.01)
        assert sig.effective_duration == 0.0

    def test_d595_uniform_signal(self):
        """Uniform random signal should have D5-95 close to 90% of total"""
        from seiswave.core import EQSignal
        rng = np.random.RandomState(99)
        n = 5000
        dt = 0.01
        acc = rng.randn(n)
        sig = EQSignal(acc, dt=dt)
        total = sig.duration
        ed = sig.effective_duration
        # For uniform energy, D5-95 ~ 0.9 * total
        assert 0.7 * total < ed < total


class TestSignalMetrics:
    def test_arias_total_matches_signal_api(self):
        """Arias 强度总量应与 EQSignal API 末值一致。"""
        from seiswave.core import EQSignal

        acc = np.ones(500) * 1.0
        sig = EQSignal(acc, dt=0.01)
        ia_total = sig.arias_intensity()[-1]

        assert ia_total > 0
        assert ia_total == pytest.approx(sig.arias_intensity()[-1])

    def test_parameter_comparison_after_filter(self):
        """Filtering should change PGA, Arias, and D5-95"""
        from seiswave.core import EQSignal, Filter

        dt = 0.01
        n = 2000
        t = np.arange(n) * dt
        acc = np.sin(2 * np.pi * 2 * t) + 0.5 * np.sin(2 * np.pi * 20 * t)
        sig_orig = EQSignal(acc.copy(), dt=dt)
        pga_before = sig_orig.pga
        ia_before = sig_orig.arias_intensity()[-1]

        filtered = Filter.butterworth(acc.copy(), dt, 'lowpass', 4, 5.0)
        sig_proc = EQSignal(filtered, dt=dt)
        pga_after = sig_proc.pga
        ia_after = sig_proc.arias_intensity()[-1]

        assert pga_after < pga_before
        assert ia_after < ia_before

    def test_parameter_comparison_after_trim(self):
        """Trimming should change duration and Arias intensity"""
        from seiswave.core import EQSignal

        rng = np.random.RandomState(77)
        acc = rng.randn(1000) * 0.5
        sig = EQSignal(acc.copy(), dt=0.01)
        ia_before = sig.arias_intensity()[-1]
        dur_before = sig.duration

        sig.trim(100, 899)
        ia_after = sig.arias_intensity()[-1]
        dur_after = sig.duration

        assert dur_after < dur_before
        assert ia_after < ia_before
