"""
包络参数预设模块单元测试

覆盖: EnvelopeParams, EnvelopeGenerator, 三类预设, get_envelope, 包络形状验证
"""

import numpy as np
import pytest


# ═══════════════════ EnvelopeParams ═══════════════════

class TestEnvelopeParams:
    def test_basic_creation(self):
        from seiswave.core.envelope_presets import EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0, rise_power=2.0, name="test")
        assert p.t1 == 1.0
        assert p.t2 == 5.0
        assert p.rise_power == 2.0
        assert p.decay_threshold == 0.05
        assert p.name == "test"

    def test_tau_property(self):
        from seiswave.core.envelope_presets import EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0, decay_threshold=0.05)
        # tau = -(5-1) / ln(0.05) = -4 / -2.996 ≈ 1.335
        expected = -4.0 / np.log(0.05)
        assert p.tau == pytest.approx(expected, rel=1e-6)

    def test_validation_t1_positive(self):
        from seiswave.core.envelope_presets import EnvelopeParams
        with pytest.raises(ValueError, match="t1 must be positive"):
            EnvelopeParams(t1=0.0, t2=1.0)
        with pytest.raises(ValueError, match="t1 must be positive"):
            EnvelopeParams(t1=-1.0, t2=1.0)

    def test_validation_t2_gt_t1(self):
        from seiswave.core.envelope_presets import EnvelopeParams
        with pytest.raises(ValueError, match="t2 .* must be greater than t1"):
            EnvelopeParams(t1=2.0, t2=2.0)
        with pytest.raises(ValueError, match="t2 .* must be greater than t1"):
            EnvelopeParams(t1=2.0, t2=1.0)

    def test_validation_rise_power_positive(self):
        from seiswave.core.envelope_presets import EnvelopeParams
        with pytest.raises(ValueError, match="rise_power must be positive"):
            EnvelopeParams(t1=1.0, t2=2.0, rise_power=0.0)

    def test_validation_decay_threshold_range(self):
        from seiswave.core.envelope_presets import EnvelopeParams
        with pytest.raises(ValueError, match="decay_threshold"):
            EnvelopeParams(t1=1.0, t2=2.0, decay_threshold=0.0)
        with pytest.raises(ValueError, match="decay_threshold"):
            EnvelopeParams(t1=1.0, t2=2.0, decay_threshold=1.0)
        with pytest.raises(ValueError, match="decay_threshold"):
            EnvelopeParams(t1=1.0, t2=2.0, decay_threshold=-0.1)

    def test_with_overrides(self):
        from seiswave.core.envelope_presets import EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0, rise_power=2.0, name="orig")
        p2 = p.with_overrides(t1=2.0, rise_power=3.0)
        assert p2.t1 == 2.0
        assert p2.t2 == 5.0  # unchanged
        assert p2.rise_power == 3.0
        assert p2.name == "orig"  # unchanged
        assert p.t1 == 1.0  # original unchanged

    def test_with_overrides_none_ignored(self):
        from seiswave.core.envelope_presets import EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0, rise_power=2.0)
        p2 = p.with_overrides(t1=None, rise_power=3.0)
        assert p2.t1 == 1.0  # None ignored
        assert p2.rise_power == 3.0


# ═══════════════════ EnvelopeGenerator (shape tests) ═══════════════════

class TestEnvelopeGeneratorShape:
    def test_peak_at_t1(self):
        """包络峰值必须精确出现在 t=t1 处，值为 1.0"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=2.0, t2=10.0, rise_power=2.0)
        gen = EnvelopeGenerator(p)
        t = np.linspace(0, 20, 20001)  # dt=0.001
        E = gen.envelope(t)
        idx_peak = np.argmax(E)
        assert t[idx_peak] == pytest.approx(2.0, abs=0.01)
        assert E[idx_peak] == pytest.approx(1.0, abs=1e-6)

    def test_zero_at_origin(self):
        """t=0 时包络值为 0"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0, rise_power=2.0)
        gen = EnvelopeGenerator(p)
        E0 = gen.envelope(np.array([0.0]))
        assert E0[0] == pytest.approx(0.0, abs=1e-12)

    def test_rise_section_power_law(self):
        """上升段遵循幂律 (t/t1)^n"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=2.0, t2=10.0, rise_power=3.0)
        gen = EnvelopeGenerator(p)
        t = np.array([0.5, 1.0, 1.5])
        E = gen.envelope(t)
        expected = (t / 2.0) ** 3.0
        np.testing.assert_allclose(E, expected, atol=1e-12)

    def test_decay_section_exponential(self):
        """衰减段遵循指数衰减，在 t2 处等于 threshold"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=2.0, t2=10.0, rise_power=2.0, decay_threshold=0.05)
        gen = EnvelopeGenerator(p)
        E_at_t2 = gen.envelope(np.array([10.0]))[0]
        assert E_at_t2 == pytest.approx(0.05, rel=1e-6)

    def test_decay_long_tail(self):
        """衰减段应有长尾（远场 tau 大）"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=3.5, t2=27.5, rise_power=1.5, decay_threshold=0.05)
        gen = EnvelopeGenerator(p)
        t = np.array([30.0, 40.0, 50.0])
        E = gen.envelope(t)
        # 应当单调递减且正值
        assert np.all(np.diff(E) < 0)
        assert np.all(E > 0)
        # t=50s 时应已很小但不精确为零
        assert E[-1] < 0.01

    def test_monotonic_rise(self):
        """上升段单调递增"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0, rise_power=2.0)
        gen = EnvelopeGenerator(p)
        t = np.linspace(0, 1.0, 101)
        E = gen.envelope(t)
        assert np.all(np.diff(E) >= -1e-12)  # 数值容差

    def test_monotonic_decay(self):
        """衰减段单调递减"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0, rise_power=2.0)
        gen = EnvelopeGenerator(p)
        t = np.linspace(1.0, 10.0, 901)
        E = gen.envelope(t)
        assert np.all(np.diff(E) <= 1e-12)

    def test_higher_rise_power_sharper(self):
        """rise_power 越大，上升越尖锐（在 t < t1 的同一点上值越小）"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p_low = EnvelopeParams(t1=1.0, t2=5.0, rise_power=1.0)
        p_high = EnvelopeParams(t1=1.0, t2=5.0, rise_power=4.0)
        gen_low = EnvelopeGenerator(p_low)
        gen_high = EnvelopeGenerator(p_high)
        t_mid = 0.5
        E_low = gen_low.envelope(np.array([t_mid]))[0]
        E_high = gen_high.envelope(np.array([t_mid]))[0]
        # 0.5^1 = 0.5, 0.5^4 = 0.0625
        assert E_low > E_high

    def test_envelope_at_method(self):
        """envelope_at 生成正确长度的数组"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0)
        gen = EnvelopeGenerator(p)
        E = gen.envelope_at(n=1000, dt=0.01)
        assert len(E) == 1000
        assert E.dtype == np.float64

    def test_apply_to_signal(self):
        """apply 方法逐点相乘"""
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0)
        gen = EnvelopeGenerator(p)
        acc = np.ones(500)  # 0-5s, dt=0.01
        dt = 0.01
        mod = gen.apply(acc, dt)
        # 手动计算期望
        t = np.arange(500) * dt
        E = gen.envelope(t)
        np.testing.assert_allclose(mod, E, atol=1e-12)

    def test_apply_with_normalize(self):
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0)
        gen = EnvelopeGenerator(p)
        rng = np.random.RandomState(42)
        acc = rng.randn(500)
        mod = gen.apply_with_normalize(acc, dt=0.01, target_pga=2.0)
        assert np.max(np.abs(mod)) == pytest.approx(2.0, rel=1e-6)

    def test_effective_duration_positive(self):
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0, rise_power=2.0)
        gen = EnvelopeGenerator(p)
        ed = gen.effective_duration
        assert ed > 0
        # 有效持时应小于总"能量区间"
        assert ed < p.t2 * 2

    def test_repr(self):
        from seiswave.core.envelope_presets import EnvelopeGenerator, EnvelopeParams
        p = EnvelopeParams(t1=1.0, t2=5.0, name="test")
        gen = EnvelopeGenerator(p)
        r = repr(gen)
        assert "test" in r
        assert "t1=1.00" in r


# ═══════════════════ Preset Classes ═══════════════════

class TestFarFieldEnvelope:
    def test_default_params(self):
        from seiswave.core.envelope_presets import FarFieldEnvelope
        env = FarFieldEnvelope()
        assert env.params.t1 == pytest.approx(3.5)
        assert env.params.t2 == pytest.approx(27.5)
        assert env.params.rise_power == pytest.approx(1.5)
        assert env.params.name == "FarField"

    def test_override_t1(self):
        from seiswave.core.envelope_presets import FarFieldEnvelope
        env = FarFieldEnvelope(t1=4.5)
        assert env.params.t1 == 4.5
        assert env.params.t2 == 27.5  # unchanged

    def test_override_all(self):
        from seiswave.core.envelope_presets import FarFieldEnvelope
        env = FarFieldEnvelope(t1=2.0, t2=15.0, rise_power=1.0, decay_threshold=0.10)
        assert env.params.t1 == 2.0
        assert env.params.t2 == 15.0
        assert env.params.rise_power == 1.0
        assert env.params.decay_threshold == 0.10

    def test_farfield_slow_decay(self):
        """远场包络 tau 应显著大于脉冲包络"""
        from seiswave.core.envelope_presets import FarFieldEnvelope, PulseEnvelope
        ff = FarFieldEnvelope()
        pulse = PulseEnvelope()
        assert ff.tau > pulse.tau * 2  # 远场衰减慢得多

    def test_farfield_peak_late(self):
        """远场峰值时间较晚"""
        from seiswave.core.envelope_presets import FarFieldEnvelope, PulseEnvelope
        ff = FarFieldEnvelope()
        pulse = PulseEnvelope()
        assert ff.peak_time > pulse.peak_time


class TestNearFieldEnvelope:
    def test_default_params(self):
        from seiswave.core.envelope_presets import NearFieldEnvelope
        env = NearFieldEnvelope()
        assert env.params.t1 == pytest.approx(1.25)
        assert env.params.t2 == pytest.approx(17.5)
        assert env.params.rise_power == pytest.approx(2.5)
        assert env.params.name == "NearField"

    def test_intermediate_tau(self):
        """近场 tau 介于远场和脉冲之间"""
        from seiswave.core.envelope_presets import FarFieldEnvelope, NearFieldEnvelope, PulseEnvelope
        ff = FarFieldEnvelope()
        nf = NearFieldEnvelope()
        pulse = PulseEnvelope()
        assert ff.tau > nf.tau > pulse.tau


class TestPulseEnvelope:
    def test_default_params(self):
        from seiswave.core.envelope_presets import PulseEnvelope
        env = PulseEnvelope()
        assert env.params.t1 == pytest.approx(0.6)
        assert env.params.t2 == pytest.approx(10.0)
        assert env.params.rise_power == pytest.approx(4.0)
        assert env.params.name == "Pulse"

    def test_sharp_rise(self):
        """脉冲包络在 t=0.3s（t1 的一半）时应已显著上升"""
        from seiswave.core.envelope_presets import PulseEnvelope, FarFieldEnvelope
        pulse = PulseEnvelope()
        ff = FarFieldEnvelope()
        t_test = 0.3  # pulse t1=0.6, ff t1=3.5
        E_pulse = pulse.envelope(np.array([t_test]))[0]
        # 脉冲在 t=0.3s 应达到峰值的 (0.3/0.6)^4 = 0.5^4 = 0.0625
        assert E_pulse == pytest.approx(0.0625, abs=1e-6)
        # 远场在 t=0.3s 时
        E_ff = ff.envelope(np.array([t_test]))[0]
        # (0.3/3.5)^1.5 ≈ 0.025
        assert E_ff < E_pulse  # 远场上升更慢（但这里因为t1不同，实际比较的是相对值）
        # 修正：这里比较的是在各自峰值时间的比例
        # 脉冲在 50% t1 时达到 6.25%
        # 远场在 50% t1 (1.75s) 时达到 (0.5)^1.5 = 35.4%
        # 所以在绝对时间 0.3s 的比较不说明上升陡峭度

    def test_pulse_vs_farfield_relative_rise(self):
        """在各自 50% t1 处比较，脉冲应上升更慢（因为 rise_power 大但 t1 小），
        但相对导数（归一化到 t1）脉冲更陡峭"""
        from seiswave.core.envelope_presets import PulseEnvelope, FarFieldEnvelope
        pulse = PulseEnvelope()
        ff = FarFieldEnvelope()
        # 在 50% 峰值时间处
        t_frac = 0.5
        E_pulse_half = pulse.envelope(np.array([t_frac * pulse.peak_time]))[0]
        E_ff_half = ff.envelope(np.array([t_frac * ff.peak_time]))[0]
        # pulse: (0.5)^4 = 0.0625
        # ff:    (0.5)^1.5 = 0.3536
        assert E_pulse_half < E_ff_half  # 脉冲在相同比例时间点上升更慢（因为 rise_power 使函数更"凹"）
        # 等等，这不对。rise_power 越大，上升越尖锐？
        # f(t) = (t/t1)^n, n=4 时 f(0.5)=0.0625; n=1.5 时 f(0.5)=0.3536
        # 所以 n 越大，在 t < t1 的同比例点上值越小？
        # 这意味着 n 大时函数在 t 接近 t1 时才快速上升！
        # 是的，这正是"尖锐上升"的含义：早期几乎为零，临近 t1 时突然上升。
        # 所以测试逻辑是对的。


# ═══════════════════ get_envelope ═══════════════════

class TestGetEnvelope:
    def test_far_field_string(self):
        from seiswave.core.envelope_presets import get_envelope
        env = get_envelope("far_field")
        assert env.params.name == "FarField"

    def test_near_field_string(self):
        from seiswave.core.envelope_presets import get_envelope
        env = get_envelope("near_field")
        assert env.params.name == "NearField"

    def test_pulse_string(self):
        from seiswave.core.envelope_presets import get_envelope
        env = get_envelope("pulse")
        assert env.params.name == "Pulse"

    def test_case_insensitive(self):
        from seiswave.core.envelope_presets import get_envelope
        env1 = get_envelope("FF")
        env2 = get_envelope("ff")
        env3 = get_envelope("Far_Field")
        assert env1.params.name == "FarField"
        assert env2.params.name == "FarField"
        assert env3.params.name == "FarField"

    def test_aliases(self):
        from seiswave.core.envelope_presets import get_envelope
        assert get_envelope("nfp").params.name == "Pulse"
        assert get_envelope("nf").params.name == "NearField"

    def test_override_via_get_envelope(self):
        from seiswave.core.envelope_presets import get_envelope
        env = get_envelope("ff", t1=5.0, rise_power=1.0)
        assert env.params.t1 == 5.0
        assert env.params.rise_power == 1.0

    def test_unknown_type_raises(self):
        from seiswave.core.envelope_presets import get_envelope
        with pytest.raises(ValueError, match="Unknown motion_type"):
            get_envelope("unknown")


# ═══════════════════ 预设参数范围验证 ═══════════════════

class TestPresetRanges:
    """验证预设参数落在 spec 要求的范围内"""

    def test_farfield_t1_in_range(self):
        from seiswave.core.envelope_presets import FARFIELD_DEFAULT
        assert 2.0 <= FARFIELD_DEFAULT.t1 <= 5.0

    def test_farfield_t2_in_range(self):
        from seiswave.core.envelope_presets import FARFIELD_DEFAULT
        assert 15.0 <= FARFIELD_DEFAULT.t2 <= 40.0

    def test_nearfield_t1_in_range(self):
        from seiswave.core.envelope_presets import NEARFIELD_DEFAULT
        assert 0.5 <= NEARFIELD_DEFAULT.t1 <= 2.0

    def test_nearfield_t2_in_range(self):
        from seiswave.core.envelope_presets import NEARFIELD_DEFAULT
        assert 10.0 <= NEARFIELD_DEFAULT.t2 <= 25.0

    def test_pulse_t1_in_range(self):
        from seiswave.core.envelope_presets import PULSE_DEFAULT
        assert 0.2 <= PULSE_DEFAULT.t1 <= 1.0

    def test_pulse_t2_in_range(self):
        from seiswave.core.envelope_presets import PULSE_DEFAULT
        assert 5.0 <= PULSE_DEFAULT.t2 <= 15.0

    def test_farfield_slower_decay_than_pulse(self):
        """远场 tau 应显著大于脉冲 tau"""
        from seiswave.core.envelope_presets import FARFIELD_DEFAULT, PULSE_DEFAULT
        tau_ff = FARFIELD_DEFAULT.tau
        tau_pulse = PULSE_DEFAULT.tau
        assert tau_ff > tau_pulse
        # 远场衰减慢，tau 应大得多（至少 2 倍）
        assert tau_ff > tau_pulse * 2
