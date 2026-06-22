"""
MP 脉冲小波生成模块单元测试

覆盖: PulseParams, PulseCalculator, PulseWavelet, 便捷工厂函数
验证: 对称/单向脉冲形状、有效区间外为0、峰值幅值、数值微分
"""

import numpy as np
import pytest


# ═══════════════════ PulseParams ═══════════════════

class TestPulseParams:
    def test_basic_creation(self):
        from seiswave.core.pulse import PulseParams
        p = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=9.0)
        assert p.Tp == 5.0
        assert p.A == 150.0
        assert p.phi == 0.0
        assert p.t0 == 9.0

    def test_validation_Tp_positive(self):
        from seiswave.core.pulse import PulseParams
        with pytest.raises(ValueError, match="Tp must be positive"):
            PulseParams(Tp=0.0, A=100.0, phi=0.0, t0=1.0)
        with pytest.raises(ValueError, match="Tp must be positive"):
            PulseParams(Tp=-1.0, A=100.0, phi=0.0, t0=1.0)

    def test_validation_A_positive(self):
        from seiswave.core.pulse import PulseParams
        with pytest.raises(ValueError, match="A must be positive"):
            PulseParams(Tp=5.0, A=0.0, phi=0.0, t0=1.0)
        with pytest.raises(ValueError, match="A must be positive"):
            PulseParams(Tp=5.0, A=-50.0, phi=0.0, t0=1.0)

    def test_validation_t0_nonnegative(self):
        from seiswave.core.pulse import PulseParams
        with pytest.raises(ValueError, match="t0 must be non-negative"):
            PulseParams(Tp=5.0, A=100.0, phi=0.0, t0=-1.0)

    def test_with_overrides(self):
        from seiswave.core.pulse import PulseParams
        p = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=9.0)
        p2 = p.with_overrides(A=200.0, phi=np.pi/2)
        assert p2.A == 200.0
        assert p2.phi == pytest.approx(np.pi/2)
        assert p2.Tp == 5.0  # unchanged
        assert p2.t0 == 9.0  # unchanged


# ═══════════════════ PulseCalculator ═══════════════════

class TestPulseCalculator:
    def test_compute_period_M7(self):
        from seiswave.core.pulse import PulseCalculator
        Mw = 7.0
        Tp = PulseCalculator.compute_period(Mw)
        expected = 10.0 ** (-2.9 + 0.5 * Mw)
        assert Tp == pytest.approx(expected, rel=1e-6)
        assert Tp > 0

    def test_compute_period_small_mw(self):
        from seiswave.core.pulse import PulseCalculator
        with pytest.raises(ValueError, match="脉冲模型不适用"):
            PulseCalculator.compute_period(5.0)

    def test_compute_params(self):
        from seiswave.core.pulse import PulseCalculator
        params = PulseCalculator.compute_params(
            Mw=7.0, R=5.0, fault_type="strike_slip", phi=0.0, t_total=30.0
        )
        assert params.Tp == pytest.approx(10.0 ** (-2.9 + 0.5 * 7.0), rel=1e-6)
        assert params.A > 0
        assert params.phi == 0.0
        assert params.t0 == 15.0  # t_total / 2

    def test_compute_params_reverse_fault(self):
        from seiswave.core.pulse import PulseCalculator
        ss = PulseCalculator.compute_params(
            Mw=7.0, R=5.0, fault_type="strike_slip"
        )
        rev = PulseCalculator.compute_params(
            Mw=7.0, R=5.0, fault_type="reverse"
        )
        # Reverse fault has higher amplitude (+0.20 in ln(A))
        assert rev.A > ss.A
        # Ratio is exp(0.20) ≈ 1.22
        assert rev.A == pytest.approx(ss.A * np.exp(0.20), rel=1e-6)

    def test_compute_params_user_overrides(self):
        """用户可直接覆盖 Tp, A, phi, t0"""
        from seiswave.core.pulse import PulseCalculator
        # 全部覆盖
        params = PulseCalculator.compute_params(
            Mw=7.0, R=5.0,
            Tp_override=10.0, A_override=200.0,
            phi_override=np.pi/2, t0_override=8.0,
        )
        assert params.Tp == 10.0
        assert params.A == 200.0
        assert params.phi == pytest.approx(np.pi/2)
        assert params.t0 == 8.0

        # 部分覆盖：只覆盖 Tp，其余用经验公式
        params2 = PulseCalculator.compute_params(
            Mw=7.0, R=5.0, Tp_override=12.0
        )
        assert params2.Tp == 12.0
        assert params2.A > 0  # 经验公式计算
        assert params2.phi == 0.0
        assert params2.t0 == 15.0  # 默认居中 (30/2)

    def test_A_empirical_formula_magnitude(self):
        """A 应随震级增大而增大"""
        from seiswave.core.pulse import PulseCalculator
        p65 = PulseCalculator.compute_params(Mw=6.5, R=10.0)
        p70 = PulseCalculator.compute_params(Mw=7.0, R=10.0)
        p75 = PulseCalculator.compute_params(Mw=7.5, R=10.0)
        assert p65.A < p70.A < p75.A

    def test_A_empirical_formula_distance(self):
        """A 应随距离增大而减小"""
        from seiswave.core.pulse import PulseCalculator
        near = PulseCalculator.compute_params(Mw=7.0, R=3.0)
        mid = PulseCalculator.compute_params(Mw=7.0, R=5.0)
        far = PulseCalculator.compute_params(Mw=7.0, R=10.0)
        assert near.A > mid.A > far.A

    def test_A_empirical_formula_fault_type(self):
        """逆断层 A 应大于走滑，正断层应小于走滑"""
        from seiswave.core.pulse import PulseCalculator
        ss = PulseCalculator.compute_params(Mw=7.0, R=5.0, fault_type="strike_slip")
        rev = PulseCalculator.compute_params(Mw=7.0, R=5.0, fault_type="reverse")
        norm = PulseCalculator.compute_params(Mw=7.0, R=5.0, fault_type="normal")
        assert rev.A > ss.A > norm.A

    def test_t0_default_centered(self):
        """t0 默认应居中"""
        from seiswave.core.pulse import PulseCalculator
        for t_total in [20.0, 30.0, 40.0]:
            params = PulseCalculator.compute_params(Mw=7.0, R=5.0, t_total=t_total)
            assert params.t0 == t_total / 2.0

    def test_A_typical_magnitude_reasonable(self):
        """典型震级/距离的 A 应在合理工程范围"""
        from seiswave.core.pulse import PulseCalculator
        # Mw 7.0, R 5km, 走滑: 典型脉冲 PGV 分量约 50-100 cm/s
        p = PulseCalculator.compute_params(Mw=7.0, R=5.0, fault_type="strike_slip")
        assert 30.0 < p.A < 120.0
        # Mw 7.5, R 3km, 逆冲: 大震近场脉冲较强，100-250 cm/s
        p2 = PulseCalculator.compute_params(Mw=7.5, R=3.0, fault_type="reverse")
        assert 80.0 < p2.A < 300.0


# ═══════════════════ PulseWavelet ── 基本生成 ═══════════════════

class TestPulseWaveletGenerate:
    def test_basic_generation(self):
        from seiswave.core.pulse import PulseWavelet, PulseParams
        params = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=9.0)
        dt = 0.02
        n = 1500  # 30s
        v, a = PulseWavelet.generate(params, dt, n)
        assert len(v) == n
        assert len(a) == n
        assert v.dtype == np.float64
        assert a.dtype == np.float64

    def test_invalid_dt(self):
        from seiswave.core.pulse import PulseWavelet, PulseParams
        params = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=9.0)
        with pytest.raises(ValueError, match="dt must be positive"):
            PulseWavelet.generate(params, dt=0.0, n=100)
        with pytest.raises(ValueError, match="dt must be positive"):
            PulseWavelet.generate(params, dt=-0.01, n=100)

    def test_invalid_n(self):
        from seiswave.core.pulse import PulseWavelet, PulseParams
        params = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=9.0)
        with pytest.raises(ValueError, match="n must be positive"):
            PulseWavelet.generate(params, dt=0.02, n=0)
        with pytest.raises(ValueError, match="n must be positive"):
            PulseWavelet.generate(params, dt=0.02, n=-10)

    def test_zero_outside_interval(self):
        """有效区间外速度必须为 0"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        Tp = 5.0
        t0 = 9.0
        params = PulseParams(Tp=Tp, A=150.0, phi=0.0, t0=t0)
        dt = 0.02
        n = 1500
        v, a = PulseWavelet.generate(params, dt, n)
        t = np.arange(n) * dt
        # 区间外（窗口为 ±γ·Tp/2）
        half = params.gamma * Tp / 2
        left_mask = t < (t0 - half - 1e-9)
        right_mask = t > (t0 + half + 1e-9)
        assert np.all(v[left_mask] == 0.0)
        assert np.all(v[right_mask] == 0.0)

    def test_velocity_at_boundaries(self):
        """边界处速度应为 0（envelope [1+cos] = 0 当 tau = ±γ·Tp/2）"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        Tp = 5.0
        t0 = 9.0
        params = PulseParams(Tp=Tp, A=150.0, phi=0.0, t0=t0)
        dt = 0.02
        n = 1500
        v, _ = PulseWavelet.generate(params, dt, n)
        t = np.arange(n) * dt
        # 找最接近边界的点（窗口 ±γ·Tp/2）
        half = params.gamma * Tp / 2
        left_idx = np.argmin(np.abs(t - (t0 - half)))
        right_idx = np.argmin(np.abs(t - (t0 + half)))
        # 边界处应为 0 或接近 0
        assert np.abs(v[left_idx]) < 1.0  # cm/s, 边界 envelope 为 0
        assert np.abs(v[right_idx]) < 1.0

    def test_peak_amplitude_symmetric(self):
        """对称脉冲峰值应接近 A（理论最大值在 t=t0 处为 A）"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        A = 150.0
        params = PulseParams(Tp=5.0, A=A, phi=0.0, t0=9.0)
        dt = 0.02
        n = 1500
        v, _ = PulseWavelet.generate(params, dt, n)
        pgv = np.max(np.abs(v))
        # t0 处理论值 = A * cos(0) = A
        assert pgv == pytest.approx(A, rel=0.02)

    def test_peak_amplitude_one_sided(self):
        """单向脉冲峰值应小于 A（因 phi=pi/2 时 t0 处为 0）"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        A = 150.0
        params = PulseParams(Tp=5.0, A=A, phi=np.pi/2, t0=9.0)
        dt = 0.02
        n = 1500
        v, _ = PulseWavelet.generate(params, dt, n)
        pgv = np.max(np.abs(v))
        # 单向脉冲峰值小于 A，但显著大于 0
        assert 0.3 * A < pgv < A

    def test_symmetric_shape(self):
        """φ=0 时速度时程应关于 t0 近似对称"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        params = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=10.0)
        dt = 0.02
        n = 1500
        v, _ = PulseWavelet.generate(params, dt, n)
        t = np.arange(n) * dt
        # 在有效区间内取对称点对
        t0 = params.t0
        Tp = params.Tp
        # 取 [t0-2, t0+2] 内的点，dt=0.02，找对称索引
        for offset in [0.0, 0.5, 1.0, 1.5]:
            t_left = t0 - offset
            t_right = t0 + offset
            idx_l = np.argmin(np.abs(t - t_left))
            idx_r = np.argmin(np.abs(t - t_right))
            # 对称脉冲应近似对称
            assert v[idx_l] == pytest.approx(v[idx_r], rel=0.05)

    def test_one_sided_shape(self):
        """φ=π/2 时速度时程应为反对称（位移单向，工程上称"单向脉冲"）"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        # 显式 γ=1（单周期）：0.6495A 是单周期单向脉冲的精确理论峰值
        params = PulseParams(Tp=5.0, A=150.0, phi=np.pi/2, t0=10.0, gamma=1.0)
        dt = 0.02
        n = 1500
        v, _ = PulseWavelet.generate(params, dt, n)
        t = np.arange(n) * dt
        # 在 t0 两侧取对称点，应近似反对称
        for offset in [0.0, 0.5, 1.0, 1.5]:
            t_left = params.t0 - offset
            t_right = params.t0 + offset
            idx_l = np.argmin(np.abs(t - t_left))
            idx_r = np.argmin(np.abs(t - t_right))
            assert v[idx_l] == pytest.approx(-v[idx_r], rel=0.05)
        # 峰值约为 0.65*A（理论最大在 θ=±π/3 处为 ~0.65A）
        pgv = np.max(np.abs(v))
        assert pgv == pytest.approx(params.A * 0.6495, rel=0.05)

    def test_acceleration_shape(self):
        """加速度应近似为速度的数值微分"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        params = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=9.0)
        dt = 0.02
        n = 1500
        v, a = PulseWavelet.generate(params, dt, n)
        # 数值微分验证：中点处 a ≈ (v[i+1]-v[i-1])/(2dt)
        a_manual = np.zeros_like(v)
        a_manual[1:-1] = (v[2:] - v[:-2]) / (2 * dt)
        a_manual[0] = (v[1] - v[0]) / dt
        a_manual[-1] = (v[-1] - v[-2]) / dt
        # 排除边界和零值区，比较内部有效区间
        t = np.arange(n) * dt
        valid = (t > params.t0 - params.Tp/2 + 0.5) & (t < params.t0 + params.Tp/2 - 0.5)
        assert np.allclose(a[valid], a_manual[valid], rtol=0.05)


# ═══════════════════ PulseWavelet ── 便捷方法 ═══════════════════

class TestPulseWaveletConvenience:
    def test_generate_symmetric(self):
        from seiswave.core.pulse import PulseWavelet
        v, a = PulseWavelet.generate_symmetric(Tp=5.0, A=150.0, t0=9.0, dt=0.02, n=1500)
        assert len(v) == 1500
        pgv = np.max(np.abs(v))
        assert pgv == pytest.approx(150.0, rel=0.02)

    def test_generate_one_sided(self):
        from seiswave.core.pulse import PulseWavelet
        v, a = PulseWavelet.generate_one_sided(Tp=5.0, A=150.0, t0=9.0, dt=0.02, n=1500)
        assert len(v) == 1500
        pgv = np.max(np.abs(v))
        # 单向脉冲峰值 < A
        assert 40.0 < pgv < 150.0

    def test_effective_duration(self):
        from seiswave.core.pulse import PulseWavelet, PulseParams
        params = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=9.0)
        # 有效持时 = γ·Tp
        assert PulseWavelet.effective_duration(params) == params.gamma * 5.0

    def test_peak_velocity(self):
        from seiswave.core.pulse import PulseWavelet
        v, a = PulseWavelet.generate_symmetric(Tp=5.0, A=150.0, t0=9.0, dt=0.02, n=1500)
        assert PulseWavelet.peak_velocity(v) == pytest.approx(150.0, rel=0.02)

    def test_peak_acceleration(self):
        from seiswave.core.pulse import PulseWavelet
        v, a = PulseWavelet.generate_symmetric(Tp=5.0, A=150.0, t0=9.0, dt=0.02, n=1500)
        pga = PulseWavelet.peak_acceleration(a)
        assert pga > 0
        # 加速度峰值与 A/Tp 成正比，比例系数约为 π~2π 量级
        assert 50.0 < pga < 300.0

    def test_peak_acceleration_one_sided(self):
        from seiswave.core.pulse import PulseWavelet
        v, a = PulseWavelet.generate_one_sided(Tp=5.0, A=150.0, t0=9.0, dt=0.02, n=1500)
        pga = PulseWavelet.peak_acceleration(a)
        assert pga > 0
        # 单向脉冲加速度峰值与 A/Tp 成正比
        assert 50.0 < pga < 300.0


# ═══════════════════ create_pulse 工厂函数 ═══════════════════

class TestCreatePulse:
    def test_create_pulse_basic(self):
        from seiswave.core.pulse import create_pulse
        v, a, params = create_pulse(Mw=7.0, R=5.0, dt=0.02, n=1500)
        assert len(v) == 1500
        assert len(a) == 1500
        assert params.Tp == pytest.approx(10.0 ** (-2.9 + 0.5 * 7.0), rel=1e-6)
        assert params.A > 0
        assert params.phi == 0.0

    def test_create_pulse_one_sided(self):
        from seiswave.core.pulse import create_pulse
        v, a, params = create_pulse(
            Mw=7.0, R=5.0, dt=0.02, n=1500, phi=np.pi/2
        )
        assert params.phi == pytest.approx(np.pi / 2)
        pgv = np.max(np.abs(v))
        assert 0.3 * params.A < pgv < params.A

    def test_create_pulse_custom_t_total(self):
        from seiswave.core.pulse import create_pulse
        v, a, params = create_pulse(
            Mw=7.0, R=5.0, dt=0.02, n=1500, t_total=20.0
        )
        assert params.t0 == 10.0  # t_total / 2


# ═══════════════════ 文献形状一致性验证 ═══════════════════

class TestLiteratureShape:
    """验证生成波形与 Mavroeidis & Papageorgiou (2003) 文献描述一致"""

    def test_symmetric_pulse_has_two_lobes(self):
        """对称脉冲应有正负两个叶（负叶幅值约 A/8）"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        params = PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=10.0)
        dt = 0.02
        n = 1500
        v, _ = PulseWavelet.generate(params, dt, n)
        t = np.arange(n) * dt
        # 有效区间内
        valid = (t >= params.t0 - params.Tp/2) & (t <= params.t0 + params.Tp/2)
        v_valid = v[valid]
        # 应有正负两个叶（正叶约 A，负叶约 A/8）
        has_pos = np.any(v_valid > 0.5 * params.A)
        has_neg = np.any(v_valid < -0.05 * params.A)
        assert has_pos and has_neg, "对称脉冲应同时有正负叶"

    def test_one_sided_pulse_antisymmetric(self):
        """单向脉冲(φ=π/2)为反对称，峰值约 0.65A"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        # 显式 γ=1（单周期）：0.6495A 为该情形精确理论峰值
        params = PulseParams(Tp=5.0, A=150.0, phi=np.pi/2, t0=10.0, gamma=1.0)
        dt = 0.02
        n = 1500
        v_one, _ = PulseWavelet.generate(params, dt, n)
        v_sym, _ = PulseWavelet.generate(
            PulseParams(Tp=5.0, A=150.0, phi=0.0, t0=10.0, gamma=1.0), dt, n
        )
        t = np.arange(n) * dt
        idx_t0 = np.argmin(np.abs(t - 10.0))
        # φ=π/2 时 t0 处接近 0，φ=0 时 t0 处约 A
        assert abs(v_one[idx_t0]) < 5.0
        assert abs(v_sym[idx_t0]) > 140.0
        # 有效区间内验证反对称性
        valid = (t >= params.t0 - params.Tp/2) & (t <= params.t0 + params.Tp/2)
        v_valid = v_one[valid]
        pos_max = np.max(v_valid)
        neg_max = np.abs(np.min(v_valid))
        assert pos_max == pytest.approx(neg_max, rel=0.1)
        assert pos_max == pytest.approx(params.A * 0.6495, rel=0.05)

    def test_pgv_scales_with_A(self):
        """PGV 应随 A 线性缩放"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        for A in [50.0, 100.0, 200.0]:
            params = PulseParams(Tp=5.0, A=A, phi=0.0, t0=9.0)
            v, _ = PulseWavelet.generate(params, dt=0.02, n=1500)
            pgv = np.max(np.abs(v))
            assert pgv == pytest.approx(A, rel=0.05)

    def test_pgv_scales_weakly_with_Tp(self):
        """PGV 不随 Tp 剧烈变化（对固定 A）"""
        from seiswave.core.pulse import PulseWavelet, PulseParams
        A = 150.0
        pgvs = []
        for Tp in [3.0, 5.0, 8.0]:
            params = PulseParams(Tp=Tp, A=A, phi=0.0, t0=10.0)
            v, _ = PulseWavelet.generate(params, dt=0.02, n=1500)
            pgvs.append(np.max(np.abs(v)))
        # 峰值基本不变（约 A）
        assert all(p == pytest.approx(A, rel=0.05) for p in pgvs)
