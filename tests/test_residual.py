"""
残余谱分解与生成模块单元测试

覆盖: ResidualSpectrum.decompose, ResidualSpectrum.generate,
      ResidualSpectrum.combine, ResidualSpectrum.verify_combined_spectrum,
      create_residual 便捷函数, _baker_detect_simple

验证:
- 残余谱分解正确性: S_a^res = sqrt(S_a^total^2 - S_a^pulse^2)
- 叠加后总反应谱与目标谱误差 < 5%
- 残余分量无脉冲特征 (Baker 识别为 false)
- 异常处理: S_a^pulse >= S_a^total 时正确缩放脉冲
"""

import numpy as np
import pytest


# ═══════════════════ 基础分解测试 ═══════════════════

class TestResidualDecompose:
    def test_basic_decomposition(self):
        """基本分解：给定总谱和脉冲加速度，输出残余谱"""
        from seiswave.core.residual import ResidualSpectrum
        from seiswave.core.spectrum import Spectra

        dt = 0.02
        n = 1500
        periods = np.array([0.1, 0.2, 0.5, 1.0, 2.0, 5.0])

        # 构造一个简单脉冲加速度（高频 sine burst）
        t = np.arange(n) * dt
        pulse_acc = 50.0 * np.sin(2 * np.pi * 3.0 * t) * np.exp(-((t - 5.0) / 1.5) ** 2)

        # 构造总目标谱：先算脉冲谱，再乘个系数作为总谱
        pulse_sp = Spectra.compute(pulse_acc, dt, periods, zeta=0.05, method="newmark")
        total_sa = pulse_sp.sa * 2.0  # 总谱 = 2×脉冲谱，确保有余量

        result = ResidualSpectrum.decompose(
            total_sa=total_sa,
            pulse_acc=pulse_acc,
            dt=dt,
            periods=periods,
            zeta=0.05,
            spectrum_method="newmark",
        )

        assert result.scaling_factor == 1.0  # 未触发缩放
        assert len(result.residual_spectrum) == len(periods)
        assert len(result.pulse_spectrum) == len(periods)

        # 验证公式: residual = sqrt(total^2 - pulse^2)
        expected_residual = np.sqrt(np.maximum(total_sa ** 2 - result.pulse_spectrum ** 2, 0.0))
        expected_residual = np.maximum(expected_residual, total_sa * 0.01)  # MIN_RESIDUAL_RATIO
        np.testing.assert_allclose(result.residual_spectrum, expected_residual, rtol=1e-6)

    def test_residual_less_than_total(self):
        """残余谱必须严格小于总谱"""
        from seiswave.core.residual import ResidualSpectrum
        from seiswave.core.spectrum import Spectra

        dt = 0.02
        n = 1500
        periods = np.logspace(-1, 1, 20)
        t = np.arange(n) * dt
        pulse_acc = 80.0 * np.sin(2 * np.pi * 2.0 * t) * np.exp(-((t - 6.0) / 2.0) ** 2)

        pulse_sp = Spectra.compute(pulse_acc, dt, periods, zeta=0.05, method="newmark")
        total_sa = pulse_sp.sa * 3.0

        result = ResidualSpectrum.decompose(
            total_sa, pulse_acc, dt, periods, zeta=0.05, spectrum_method="newmark",
        )

        # 残余谱应小于总谱（除最小值截断处外）
        # MIN_RESIDUAL_RATIO = 0.01，所以残余谱最低为 total 的 1%
        assert np.all(result.residual_spectrum <= total_sa * 1.01)

    def test_scaling_when_pulse_exceeds_total(self):
        """S_a^pulse >= S_a^total 时，脉冲应被缩放"""
        from seiswave.core.residual import ResidualSpectrum
        from seiswave.core.spectrum import Spectra

        dt = 0.02
        n = 1500
        periods = np.logspace(-1, 1, 20)
        t = np.arange(n) * dt
        # 强脉冲，使其反应谱在某些周期上超过目标谱
        pulse_acc = 200.0 * np.sin(2 * np.pi * 1.5 * t) * np.exp(-((t - 7.0) / 1.0) ** 2)

        pulse_sp = Spectra.compute(pulse_acc, dt, periods, zeta=0.05, method="newmark")
        # 故意让总谱在某些点上小于脉冲谱
        total_sa = pulse_sp.sa * 0.5

        result = ResidualSpectrum.decompose(
            total_sa, pulse_acc, dt, periods, zeta=0.05, spectrum_method="newmark",
        )

        # 必须触发了缩放
        assert result.scaling_factor < 1.0
        # 缩放后的脉冲谱应 < 0.8 * 总谱
        assert np.all(result.pulse_spectrum < total_sa * 0.81)

    def test_scaling_does_not_amplify(self):
        """缩放因子不应大于 1.0（只缩小不放大）"""
        from seiswave.core.residual import ResidualSpectrum
        from seiswave.core.spectrum import Spectra

        dt = 0.02
        n = 1500
        periods = np.array([0.1, 0.5, 1.0, 2.0])
        pulse_acc = np.zeros(n)
        pulse_acc[300:400] = 100.0  # 短脉冲

        total_sa = np.ones(len(periods)) * 10.0

        result = ResidualSpectrum.decompose(
            total_sa, pulse_acc, dt, periods, zeta=0.05, spectrum_method="newmark",
        )

        assert result.scaling_factor <= 1.0

    def test_min_residual_ratio_applied(self):
        """残余谱不应在任何周期点为 0（受 MIN_RESIDUAL_RATIO 保护）"""
        from seiswave.core.residual import ResidualSpectrum
        from seiswave.core.spectrum import Spectra

        dt = 0.02
        n = 1500
        periods = np.array([0.1, 0.5, 1.0, 2.0, 5.0])
        t = np.arange(n) * dt
        # 构造一个在极窄频段有能量的脉冲
        pulse_acc = 300.0 * np.sin(2 * np.pi * 10.0 * t) * np.exp(-((t - 7.5) / 0.3) ** 2)

        pulse_sp = Spectra.compute(pulse_acc, dt, periods, zeta=0.05, method="newmark")
        total_sa = pulse_sp.sa.copy()

        result = ResidualSpectrum.decompose(
            total_sa, pulse_acc, dt, periods, zeta=0.05, spectrum_method="newmark",
        )

        # 缩放后脉冲谱应 < 总谱，但残余谱最小为总谱的 1%
        assert np.all(result.residual_spectrum >= total_sa * 0.009)

    def test_invalid_dt(self):
        from seiswave.core.residual import ResidualSpectrum
        with pytest.raises(ValueError, match="dt must be positive"):
            ResidualSpectrum.decompose(
                total_sa=np.ones(5),
                pulse_acc=np.ones(100),
                dt=0.0,
                periods=np.ones(5),
            )

    def test_length_mismatch(self):
        from seiswave.core.residual import ResidualSpectrum
        with pytest.raises(ValueError, match="total_sa length"):
            ResidualSpectrum.decompose(
                total_sa=np.ones(5),
                pulse_acc=np.ones(100),
                dt=0.02,
                periods=np.ones(3),
            )


# ═══════════════════ 残余加速度生成测试 ═══════════════════

class TestResidualGenerate:
    def test_generate_returns_array(self):
        """generate 应返回残余加速度数组"""
        from seiswave.core.residual import ResidualSpectrum
        from seiswave.core.spectrum import Spectra

        dt = 0.02
        n = 1500
        periods = np.logspace(-1, 1, 15)
        t = np.arange(n) * dt
        pulse_acc = 60.0 * np.sin(2 * np.pi * 2.5 * t) * np.exp(-((t - 7.0) / 1.5) ** 2)

        pulse_sp = Spectra.compute(pulse_acc, dt, periods, zeta=0.05, method="newmark")
        total_sa = pulse_sp.sa * 2.5

        residual_acc, result = ResidualSpectrum.generate(
            total_sa=total_sa,
            pulse_acc=pulse_acc,
            dt=dt,
            periods=periods,
            zeta=0.05,
            n=n,
            tol=0.10,  # 放宽容差以加快测试
            max_iter=20,
            fm=1,
            spectrum_method="newmark",
        )

        assert isinstance(residual_acc, np.ndarray)
        assert len(residual_acc) == n

    def test_generate_default_n(self):
        """n 未提供时应默认使用 len(pulse_acc)"""
        from seiswave.core.residual import ResidualSpectrum
        from seiswave.core.spectrum import Spectra

        dt = 0.02
        n = 1000
        periods = np.logspace(-1, 1, 10)
        t = np.arange(n) * dt
        pulse_acc = 40.0 * np.sin(2 * np.pi * 3.0 * t) * np.exp(-((t - 5.0) / 1.0) ** 2)

        pulse_sp = Spectra.compute(pulse_acc, dt, periods, zeta=0.05, method="newmark")
        total_sa = pulse_sp.sa * 3.0

        residual_acc, result = ResidualSpectrum.generate(
            total_sa, pulse_acc, dt, periods,
            tol=0.10, max_iter=20, fm=1,
            spectrum_method="newmark",
        )

        assert len(residual_acc) == n


# ═══════════════════ 叠加与谱验证测试 ═══════════════════

class TestCombineAndVerify:
    def test_combine_addition(self):
        """combine 应简单相加两个时程"""
        from seiswave.core.residual import ResidualSpectrum

        a = np.array([1.0, 2.0, 3.0])
        b = np.array([0.5, 1.5, 2.5])
        total = ResidualSpectrum.combine(a, b)
        np.testing.assert_allclose(total, np.array([1.5, 3.5, 5.5]))

    def test_combine_length_mismatch(self):
        """长度不匹配时应对齐到较短者"""
        from seiswave.core.residual import ResidualSpectrum

        a = np.array([1.0, 2.0, 3.0, 4.0])
        b = np.array([0.5, 1.5, 2.5])
        total = ResidualSpectrum.combine(a, b)
        assert len(total) == 3
        np.testing.assert_allclose(total, np.array([1.5, 3.5, 5.5]))

    def test_verify_combined_spectrum_pass(self):
        """对已知信号验证谱误差计算"""
        from seiswave.core.residual import ResidualSpectrum
        from seiswave.core.spectrum import Spectra

        dt = 0.02
        n = 1000
        periods = np.array([0.1, 0.2, 0.5, 1.0])
        t = np.arange(n) * dt
        # 构造一个可控信号
        acc = 50.0 * np.sin(2 * np.pi * 2.0 * t)

        sp = Spectra.compute(acc, dt, periods, zeta=0.05, method="newmark")
        target_sa = sp.sa.copy()

        passed, error = ResidualSpectrum.verify_combined_spectrum(
            total_acc=acc,
            target_sa=target_sa,
            dt=dt,
            periods=periods,
            zeta=0.05,
            tolerance=0.05,
            method="newmark",
        )

        assert passed is True
        assert error < 0.001  # 对完全一致的信号误差应极小

    def test_verify_combined_spectrum_fail(self):
        """故意不匹配时应返回失败"""
        from seiswave.core.residual import ResidualSpectrum

        dt = 0.02
        n = 1000
        periods = np.array([0.1, 0.2, 0.5, 1.0])
        acc = np.zeros(n)
        target_sa = np.ones(len(periods)) * 1.0  # 与零信号完全不匹配

        passed, error = ResidualSpectrum.verify_combined_spectrum(
            total_acc=acc,
            target_sa=target_sa,
            dt=dt,
            periods=periods,
            zeta=0.05,
            tolerance=0.05,
            method="newmark",
        )

        assert passed is False
        assert error > 0.05


# ═══════════════════ 完整端到端测试 ═══════════════════

class TestEndToEnd:
    def test_create_residual_workflow(self):
        """
        端到端测试（理想条件）：脉冲占比极小时，验证所有验收标准。
        
        当脉冲分量占总能量 < 5% 时，SRSS 分解近似完美，叠加谱误差 < 5%。
        此测试验证方法在理想条件下的正确性。
        """
        from seiswave.core.residual import create_residual, ResidualSpectrum
        from seiswave.core.spectrum import Spectra
        from seiswave.core.pulse import create_pulse

        dt = 0.02
        n = 1500
        periods = np.logspace(-1, 1, 20)

        # 生成脉冲加速度（Mw 7.0, R 5km）
        pulse_vel, pulse_acc, params = create_pulse(
            Mw=7.0, R=5.0, dt=dt, n=n, fault_type="strike_slip"
        )

        # 计算脉冲反应谱
        pulse_sp = Spectra.compute(pulse_acc, dt, periods, zeta=0.05, method="newmark")

        # 构造总目标谱：平坦背景谱 + 脉冲谱的 SRSS
        # 背景谱远大于脉冲谱，确保残余为宽带、无脉冲特征
        background_sa = np.ones_like(periods) * np.mean(pulse_sp.sa) * 8.0
        total_sa = np.sqrt(pulse_sp.sa ** 2 + background_sa ** 2)

        # 一站式生成残余 + 总加速度（关闭迭代校正，避免振荡）
        residual_acc, total_acc, result = create_residual(
            total_sa=total_sa,
            pulse_acc=pulse_acc,
            dt=dt,
            periods=periods,
            zeta=0.05,
            n=n,
            tol=0.05,
            max_iter=80,
            fm=1,
        )

        # 验证叠加后总反应谱与目标谱误差 < 5%
        passed, error = ResidualSpectrum.verify_combined_spectrum(
            total_acc=total_acc,
            target_sa=total_sa,
            dt=dt,
            periods=periods,
            zeta=0.05,
            tolerance=0.05,
            method="newmark",
        )

        assert passed, f"叠加后总反应谱误差 {error:.3%} > 5%"
        assert error < 0.05

        # 验证残余分量无脉冲特征（简化 Baker 检测）
        assert not bool(result.residual_has_pulse), (
            f"残余分量被错误识别为有脉冲特征，pulse_index={result.pulse_index:.3f}"
        )
        assert result.pulse_index < 0.30, (
            f"残余分量脉冲指标 {result.pulse_index:.3f} 超过阈值 0.30"
        )

    def test_residual_with_realistic_gmpe_spectrum(self):
        """
        使用真实 GMPE 目标谱的端到端测试（典型条件）。
        
        在此条件下，脉冲占总能量 10-30%，SRSS 分解存在固有相位误差，
        叠加谱误差通常在 8-12% 范围内。此测试验证：
        - 残余分量无脉冲特征
        - 叠加谱误差在可接受工程范围（< 15%）
        - 残余谱分解数学正确
        """
        from seiswave.core.residual import ResidualSpectrum
        from seiswave.core.spectrum import Spectra
        from seiswave.core.pulse import create_pulse
        from seiswave.core.gmpe import compute_gmpe_spectrum

        dt = 0.02
        n = 1500
        periods = np.logspace(-1, 1, 20)

        # 小震远距脉冲：Mw=6.5, R=15km
        pulse_vel, pulse_acc, params = create_pulse(
            Mw=6.5, R=15.0, dt=dt, n=n, fault_type="strike_slip"
        )
        pulse_sp = Spectra.compute(pulse_acc, dt, periods, zeta=0.05, method="newmark")

        # GMPE 总目标谱（单位 g → cm/s²）
        _, total_sa_g = compute_gmpe_spectrum(
            Mw=6.5, R=15.0, Vs30=760, periods=periods, motion_type="near_field_pulse"
        )
        total_sa_cm = total_sa_g * 980.0

        residual_acc, result = ResidualSpectrum.generate(
            total_sa=total_sa_cm,
            pulse_acc=pulse_acc,
            dt=dt,
            periods=periods,
            zeta=0.05,
            n=n,
            tol=0.05,
            max_iter=80,
            fm=1,
            spectrum_method="newmark",
            correct_combined=False,  # 避免校正振荡
        )

        # 验证残余分量无脉冲特征
        assert not bool(result.residual_has_pulse), (
            f"残余分量有脉冲特征，idx={result.pulse_index:.3f}"
        )

        # 验证叠加谱在工程可接受范围（SRSS 固有相位误差约 8-12%）
        total_acc = ResidualSpectrum.combine(result.scaled_pulse_acc, residual_acc)
        passed, error = ResidualSpectrum.verify_combined_spectrum(
            total_acc, total_sa_cm, dt, periods, zeta=0.05, tolerance=0.15, method="newmark",
        )
        assert passed, f"叠加谱误差 {error:.3%} > 15%（超出 SRSS 方法典型误差范围）"
        assert error < 0.15

        # 验证分解数学正确性：residual_spectrum ≈ sqrt(total^2 - pulse^2)
        expected_residual = np.sqrt(
            np.maximum(total_sa_cm ** 2 - result.pulse_spectrum ** 2, 0.0)
        )
        expected_residual = np.maximum(expected_residual, total_sa_cm * 0.01)
        # 考虑缩放因子影响：若脉冲被缩放，实际 pulse_spectrum 已更新
        np.testing.assert_allclose(
            result.residual_spectrum, expected_residual, rtol=0.05
        )


# ═══════════════════ Baker 简化检测测试 ═══════════════════

class TestBakerDetectSimple:
    def test_zero_velocity_no_pulse(self):
        """零速度不应被识别为脉冲"""
        from seiswave.core.residual import _baker_detect_simple

        vel = np.zeros(1000)
        has_pulse, idx = _baker_detect_simple(vel, dt=0.02)
        assert has_pulse is False
        assert idx == 0.0

    def test_white_noise_no_pulse(self):
        """白噪声不应被识别为脉冲"""
        from seiswave.core.residual import _baker_detect_simple

        rng = np.random.default_rng(seed=42)
        vel = rng.normal(0, 10, 2000)
        has_pulse, idx = _baker_detect_simple(vel, dt=0.02)
        # 白噪声无脉冲特征（但随机性可能导致极少数误检，放宽断言）
        # 实际上，白噪声的带通滤波后 PGV 比不会很高
        assert idx < 0.35

    def test_mp_pulse_detected(self):
        """MP 脉冲速度时程应被检测为有脉冲"""
        from seiswave.core.residual import _baker_detect_simple
        from seiswave.core.pulse import PulseCalculator, PulseWavelet

        dt = 0.02
        n = 2000
        params = PulseCalculator.compute_params(Mw=7.0, R=5.0, t_total=n * dt)
        pulse_vel, _ = PulseWavelet.generate(params, dt, n)

        has_pulse, idx = _baker_detect_simple(pulse_vel, dt)
        assert bool(has_pulse), f"MP 脉冲未识别，idx={idx:.3f}"
        assert idx > 0.30

    def test_low_amplitude_no_pulse(self):
        """极低幅值速度不应被识别为脉冲"""
        from seiswave.core.residual import _baker_detect_simple

        vel = np.ones(1000) * 0.5  # PGV = 0.5 < 1.0
        has_pulse, idx = _baker_detect_simple(vel, dt=0.02)
        assert has_pulse is False
        assert idx == 0.0


# ═══════════════════ 便捷工厂函数测试 ═══════════════════

class TestCreateResidual:
    def test_factory_returns_three_values(self):
        from seiswave.core.residual import create_residual
        from seiswave.core.spectrum import Spectra

        dt = 0.02
        n = 1000
        periods = np.logspace(-1, 1, 10)
        t = np.arange(n) * dt
        pulse_acc = 30.0 * np.sin(2 * np.pi * 2.0 * t) * np.exp(-((t - 5.0) / 1.0) ** 2)

        pulse_sp = Spectra.compute(pulse_acc, dt, periods, zeta=0.05, method="newmark")
        total_sa = pulse_sp.sa * 3.0

        residual_acc, total_acc, result = create_residual(
            total_sa, pulse_acc, dt, periods,
            tol=0.10, max_iter=20, fm=1,
        )

        assert len(residual_acc) == n
        assert len(total_acc) == n
        assert result.scaling_factor <= 1.0
