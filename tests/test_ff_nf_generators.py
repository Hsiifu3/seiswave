"""
FarFieldGenerator / NearFieldNoPulseGenerator 单元测试

覆盖:
- FF 生成器：GMPE 远场目标谱 + 频域谱匹配 (fm=0)
- NF 生成器：GMPE 近场目标谱 + 频域谱匹配 (fm=0)
- 反应谱误差在频域法可实现范围内
- Baker 识别为 false
- 持时特征符合预期范围

注：频域法 (fm=0) 在典型参数下
- n=1024, iter=15: 均方根约 7-10%
- n=2000, iter=80: 均方根约 4-5%（任务验收标准 < 5%）
"""

import numpy as np
import pytest

from seiswave.core.gmpe import FaultType, GMPEAdapter, MotionType
from seiswave.core.pulse import BakerPulseDetector
from seiswave.core.spectrum import Spectra

# 测试用小参数，加速谱匹配
TEST_N = 1024
TEST_DT = 0.02
TEST_TOL = 0.10
TEST_MAX_ITER = 15


def _fit_against_target(sig, *, Mw, R, motion_type, Vs30=760.0):
    from seiswave.core.generator import WaveGenerator

    periods, target_sa = GMPEAdapter.compute_spectrum(
        Mw=Mw,
        R=R,
        Vs30=Vs30,
        fault_type=FaultType.STRIKE_SLIP,
        motion_type=motion_type,
    )
    spec = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method="mixed")
    return WaveGenerator.fit_error(spec.sa, target_sa)


# ═══════════════════ FarFieldGenerator ═══════════════════

class TestFarFieldGenerator:
    def test_generate_returns_eqsignal(self):
        from seiswave.core.generator import FarFieldGenerator
        sig = FarFieldGenerator.generate(
            Mw=7.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig.n > 0
        assert sig.dt > 0
        assert sig.duration > 0
        assert hasattr(sig, 'acc')
        assert hasattr(sig, 'vel')
        assert hasattr(sig, 'disp')

    def test_spectrum_error_reasonable(self):
        """反应谱误差在频域法可实现范围内（fm=0，n=1024, iter=15 时 mean≈7%）"""
        from seiswave.core.generator import FarFieldGenerator, WaveGenerator
        from seiswave.core.gmpe import GMPEAdapter, FaultType, MotionType
        from seiswave.core.spectrum import Spectra

        Mw, R, Vs30 = 7.0, 50.0, 760.0
        periods, target_sa = GMPEAdapter.compute_spectrum(
            Mw=Mw, R=R, Vs30=Vs30,
            fault_type=FaultType.STRIKE_SLIP,
            motion_type=MotionType.FAR_FIELD,
        )

        sig = FarFieldGenerator.generate(
            Mw=Mw, R=R, Vs30=Vs30,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        spec = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method="mixed")

        fit = WaveGenerator.fit_error(spec.sa, target_sa)
        # 频域法 fm=0 实测：n=1024, iter=15 时 mean≈7%, max≈31%
        # n=2000, iter=80 时 mean≈4.3%, max≈14%
        assert fit['mean_error'] < 0.15, f"均方根误差 {fit['mean_error']:.1%} 超出合理范围"
        assert fit['max_error'] < 0.50, f"最大误差 {fit['max_error']:.1%} 超出合理范围"

    def test_baker_identifies_no_pulse(self):
        """FF 速度时程 Baker 识别为 false"""
        from seiswave.core.generator import FarFieldGenerator
        from seiswave.core.pulse import BakerPulseDetector

        sig = FarFieldGenerator.generate(
            Mw=7.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        vel_cm_s = sig.vel * 100.0
        has_pulse = BakerPulseDetector.has_pulse(vel_cm_s, sig.dt)
        assert has_pulse == False, f"FF 被误判为含脉冲: {has_pulse}"

    def test_duration_in_expected_range(self):
        """远场持时特征：有效持时应存在且合理"""
        from seiswave.core.generator import FarFieldGenerator

        sig = FarFieldGenerator.generate(
            Mw=7.0, R=50.0, Vs30=760.0,
            n=2048, dt=0.02, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        eff_dur = sig.effective_duration
        # 远场有效持时应存在且为正值
        assert eff_dur > 0, f"远场持时应 > 0，实际 {eff_dur:.1f}s"
        assert eff_dur < sig.duration, f"有效持时不能超过总持时"

    def test_pga_positive(self):
        from seiswave.core.generator import FarFieldGenerator
        sig = FarFieldGenerator.generate(
            Mw=7.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig.pga > 0

    def test_name_contains_ff(self):
        from seiswave.core.generator import FarFieldGenerator
        sig = FarFieldGenerator.generate(
            Mw=7.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert "FF" in sig.name

    def test_different_magnitude(self):
        """不同震级应生成不同 PGA"""
        from seiswave.core.generator import FarFieldGenerator
        sig_m6 = FarFieldGenerator.generate(
            Mw=6.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        sig_m8 = FarFieldGenerator.generate(
            Mw=8.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig_m8.pga > sig_m6.pga, "大震 PGA 应大于小震"

    def test_different_distance(self):
        """不同距离应生成不同 PGA"""
        from seiswave.core.generator import FarFieldGenerator
        sig_near = FarFieldGenerator.generate(
            Mw=7.0, R=30.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        sig_far = FarFieldGenerator.generate(
            Mw=7.0, R=100.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig_near.pga > sig_far.pga, "近距 PGA 应大于远距"


# ═══════════════════ NearFieldNoPulseGenerator ═══════════════════

class TestNearFieldNoPulseGenerator:
    def test_generate_returns_eqsignal(self):
        from seiswave.core.generator import NearFieldNoPulseGenerator
        sig = NearFieldNoPulseGenerator.generate(
            Mw=7.0, R=5.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig.n > 0
        assert sig.dt > 0
        assert sig.duration > 0

    def test_spectrum_error_reasonable(self):
        """反应谱误差在频域法可实现范围内（fm=0，n=1024, iter=15 时 mean≈10%）"""
        from seiswave.core.generator import NearFieldNoPulseGenerator, WaveGenerator
        from seiswave.core.gmpe import GMPEAdapter, FaultType, MotionType
        from seiswave.core.spectrum import Spectra

        Mw, R, Vs30 = 7.0, 5.0, 760.0
        periods, target_sa = GMPEAdapter.compute_spectrum(
            Mw=Mw, R=R, Vs30=Vs30,
            fault_type=FaultType.STRIKE_SLIP,
            motion_type=MotionType.NEAR_FIELD,
        )

        sig = NearFieldNoPulseGenerator.generate(
            Mw=Mw, R=R, Vs30=Vs30,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        spec = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method="mixed")

        fit = WaveGenerator.fit_error(spec.sa, target_sa)
        # 频域法 fm=0 实测：n=1024, iter=15 时 mean≈10%, max≈38%
        assert fit['mean_error'] < 0.20, f"均方根误差 {fit['mean_error']:.1%} 超出合理范围"
        assert fit['max_error'] < 0.60, f"最大误差 {fit['max_error']:.1%} 超出合理范围"

    def test_baker_identifies_no_pulse(self):
        """NF 速度时程 Baker 识别为 false"""
        from seiswave.core.generator import NearFieldNoPulseGenerator
        from seiswave.core.pulse import BakerPulseDetector

        sig = NearFieldNoPulseGenerator.generate(
            Mw=7.0, R=5.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        vel_cm_s = sig.vel * 100.0
        has_pulse = BakerPulseDetector.has_pulse(vel_cm_s, sig.dt)
        assert has_pulse == False, f"NF 被误判为含脉冲: {has_pulse}"

    def test_duration_in_expected_range(self):
        """近场无脉冲持时特征"""
        from seiswave.core.generator import NearFieldNoPulseGenerator

        sig = NearFieldNoPulseGenerator.generate(
            Mw=7.0, R=5.0, Vs30=760.0,
            n=2048, dt=0.01, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        eff_dur = sig.effective_duration
        assert eff_dur > 0, f"NF 持时应 > 0，实际 {eff_dur:.1f}s"
        assert eff_dur < sig.duration, f"有效持时不能超过总持时"

    def test_pga_positive(self):
        from seiswave.core.generator import NearFieldNoPulseGenerator
        sig = NearFieldNoPulseGenerator.generate(
            Mw=7.0, R=5.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig.pga > 0

    def test_name_contains_nf(self):
        from seiswave.core.generator import NearFieldNoPulseGenerator
        sig = NearFieldNoPulseGenerator.generate(
            Mw=7.0, R=5.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert "NF" in sig.name

    def test_nearfield_higher_pga_than_farfield_same_magnitude(self):
        """同震级下，近场 PGA 应显著高于远场"""
        from seiswave.core.generator import FarFieldGenerator, NearFieldNoPulseGenerator
        sig_ff = FarFieldGenerator.generate(
            Mw=7.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        sig_nf = NearFieldNoPulseGenerator.generate(
            Mw=7.0, R=5.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        assert sig_nf.pga > sig_ff.pga, "近场 PGA 应大于远场"


# ═══════════════════ BakerPulseDetector ═══════════════════

class TestGeneratorStabilityMatrix:
    @pytest.mark.parametrize(
        ("generator_cls_name", "motion_type", "params", "mean_limit", "max_limit", "expect_pulse", "velocity_scale"),
        [
            (
                "FarFieldGenerator",
                MotionType.FAR_FIELD,
                {"Mw": 6.5, "R": 30.0, "dt": 0.02, "n": 1024, "max_iter": 15, "tol": 0.10},
                0.09,
                0.32,
                False,
                100.0,
            ),
            (
                "FarFieldGenerator",
                MotionType.FAR_FIELD,
                {"Mw": 7.0, "R": 50.0, "dt": 0.02, "n": 1024, "max_iter": 15, "tol": 0.10},
                0.08,
                0.25,
                False,
                100.0,
            ),
            (
                "FarFieldGenerator",
                MotionType.FAR_FIELD,
                {"Mw": 7.5, "R": 80.0, "dt": 0.01, "n": 2048, "max_iter": 20, "tol": 0.08},
                0.07,
                0.23,
                False,
                100.0,
            ),
            (
                "NearFieldNoPulseGenerator",
                MotionType.NEAR_FIELD,
                {"Mw": 6.5, "R": 8.0, "dt": 0.02, "n": 1024, "max_iter": 15, "tol": 0.10},
                0.07,
                0.27,
                False,
                100.0,
            ),
            (
                "NearFieldNoPulseGenerator",
                MotionType.NEAR_FIELD,
                {"Mw": 7.0, "R": 5.0, "dt": 0.02, "n": 1024, "max_iter": 15, "tol": 0.10},
                0.08,
                0.30,
                False,
                100.0,
            ),
            (
                "NearFieldNoPulseGenerator",
                MotionType.NEAR_FIELD,
                {"Mw": 7.5, "R": 3.0, "dt": 0.01, "n": 2048, "max_iter": 20, "tol": 0.08},
                0.06,
                0.22,
                False,
                100.0,
            ),
            (
                "NearFieldPulseGenerator",
                MotionType.NEAR_FIELD_PULSE,
                {"Mw": 7.0, "R": 4.0, "dt": 0.01, "n": 1024, "max_iter": 15, "tol": 0.10},
                0.06,
                0.17,
                True,
                980.0,
            ),
            (
                "NearFieldPulseGenerator",
                MotionType.NEAR_FIELD_PULSE,
                {"Mw": 7.2, "R": 4.0, "dt": 0.01, "n": 1024, "max_iter": 15, "tol": 0.10},
                0.06,
                0.18,
                True,
                980.0,
            ),
            (
                "NearFieldPulseGenerator",
                MotionType.NEAR_FIELD_PULSE,
                {"Mw": 7.5, "R": 5.0, "dt": 0.01, "n": 1024, "max_iter": 15, "tol": 0.10},
                0.06,
                0.19,
                True,
                980.0,
            ),
        ],
        ids=[
            "ff-m6.5-r30-dt0.02-n1024",
            "ff-m7.0-r50-dt0.02-n1024",
            "ff-m7.5-r80-dt0.01-n2048",
            "nf-m6.5-r8-dt0.02-n1024",
            "nf-m7.0-r5-dt0.02-n1024",
            "nf-m7.5-r3-dt0.01-n2048",
            "nfp-m7.0-r4-dt0.01-n1024",
            "nfp-m7.2-r4-dt0.01-n1024",
            "nfp-m7.5-r5-dt0.01-n1024",
        ],
    )
    def test_multi_condition_stability(
        self,
        generator_cls_name,
        motion_type,
        params,
        mean_limit,
        max_limit,
        expect_pulse,
        velocity_scale,
    ):
        from seiswave.core import generator as generator_module

        generator_cls = getattr(generator_module, generator_cls_name)
        sig = generator_cls.generate(Vs30=760.0, **params)
        fit = _fit_against_target(
            sig,
            Mw=params["Mw"],
            R=params["R"],
            motion_type=motion_type,
        )

        assert fit["mean_error"] <= mean_limit, (
            f"{generator_cls_name} mean_error={fit['mean_error']:.3f} exceeds {mean_limit:.3f}"
        )
        assert fit["max_error"] <= max_limit, (
            f"{generator_cls_name} max_error={fit['max_error']:.3f} exceeds {max_limit:.3f}"
        )

        metrics = BakerPulseDetector.analyze(sig.vel * velocity_scale, sig.dt)
        assert metrics["has_pulse"] is expect_pulse

        if expect_pulse:
            assert metrics["confidence"] >= 0.99


class TestBakerPulseDetector:
    def test_no_pulse_on_random_noise(self):
        from seiswave.core.pulse import BakerPulseDetector
        np.random.seed(42)
        dt = 0.02
        n = 2000
        vel = np.random.randn(n) * 5.0
        has_pulse = BakerPulseDetector.has_pulse(vel, dt)
        assert has_pulse == False

    def test_detects_symmetric_pulse(self):
        from seiswave.core.pulse import BakerPulseDetector, PulseWavelet, PulseParams
        dt = 0.02
        n = 2000
        params = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=10.0)
        v, _ = PulseWavelet.generate(params, dt, n)
        has_pulse = BakerPulseDetector.has_pulse(v, dt)
        assert has_pulse == True, "对称脉冲应被识别为含脉冲"

    def test_detects_one_sided_pulse(self):
        from seiswave.core.pulse import BakerPulseDetector, PulseWavelet
        dt = 0.02
        n = 2000
        v, _ = PulseWavelet.generate_one_sided(Tp=5.0, A=150.0, t0=10.0, dt=dt, n=n)
        has_pulse = BakerPulseDetector.has_pulse(v, dt)
        assert has_pulse == True, "单向脉冲应被识别为含脉冲"

    def test_analyze_returns_dict(self):
        from seiswave.core.pulse import BakerPulseDetector
        vel = np.sin(np.linspace(0, 4 * np.pi, 500)) * 10.0
        metrics = BakerPulseDetector.analyze(vel, 0.02)
        assert "has_pulse" in metrics
        assert "pulse_period" in metrics
        assert "energy_ratio" in metrics
        assert "confidence" in metrics

    def test_confidence_range(self):
        from seiswave.core.pulse import BakerPulseDetector, PulseWavelet, PulseParams
        dt = 0.02
        n = 2000
        params = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=10.0)
        v, _ = PulseWavelet.generate(params, dt, n)
        metrics = BakerPulseDetector.analyze(v, dt)
        assert 0.0 <= metrics["confidence"] <= 1.0

    def test_empty_signal(self):
        from seiswave.core.pulse import BakerPulseDetector
        metrics = BakerPulseDetector.analyze(np.zeros(100), 0.02)
        assert metrics["has_pulse"] == False
        assert metrics["confidence"] == 0.0

    def test_short_signal(self):
        from seiswave.core.pulse import BakerPulseDetector
        metrics = BakerPulseDetector.analyze(np.array([1.0, 2.0]), 0.02)
        assert metrics["has_pulse"] == False

    def test_ff_signal_no_pulse(self):
        """用 FarField 生成信号验证 Baker 识别为 false"""
        from seiswave.core.generator import FarFieldGenerator
        from seiswave.core.pulse import BakerPulseDetector
        sig = FarFieldGenerator.generate(
            Mw=7.0, R=50.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        metrics = BakerPulseDetector.analyze(sig.vel * 100.0, sig.dt)
        assert metrics["has_pulse"] == False
        assert metrics["confidence"] < 0.5, f"FF 脉冲置信度应低，实际 {metrics['confidence']:.3f}"

    def test_nf_signal_no_pulse(self):
        """用 NearFieldNoPulse 生成信号验证 Baker 识别为 false"""
        from seiswave.core.generator import NearFieldNoPulseGenerator
        from seiswave.core.pulse import BakerPulseDetector
        sig = NearFieldNoPulseGenerator.generate(
            Mw=7.0, R=5.0, Vs30=760.0,
            n=TEST_N, dt=TEST_DT, max_iter=TEST_MAX_ITER, tol=TEST_TOL,
        )
        metrics = BakerPulseDetector.analyze(sig.vel * 100.0, sig.dt)
        assert metrics["has_pulse"] == False
        assert metrics["confidence"] < 0.5, f"NF 脉冲置信度应低，实际 {metrics['confidence']:.3f}"
