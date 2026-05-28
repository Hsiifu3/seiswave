"""
GMPE 目标谱接口单元测试

覆盖: GMPEAdapter, GMPEParams, CustomSpectrum, FEMA P695 预设,
      近场/远场区分, 自定义谱, Sa 合理范围验证
"""

import numpy as np
import pytest


# ═══════════════════ GMPEParams ═══════════════════

class TestGMPEParams:
    def test_basic_creation(self):
        from seiswave.core.gmpe import GMPEParams, FaultType, MotionType
        p = GMPEParams(Mw=7.0, R=10.0, Vs30=760.0)
        assert p.Mw == 7.0
        assert p.R == 10.0
        assert p.Vs30 == 760.0
        assert p.fault_type == FaultType.STRIKE_SLIP
        assert p.motion_type == MotionType.FAR_FIELD

    def test_validation_Mw_range(self):
        from seiswave.core.gmpe import GMPEParams
        with pytest.raises(ValueError, match="Mw"):
            GMPEParams(Mw=4.0, R=10.0, Vs30=760.0)
        with pytest.raises(ValueError, match="Mw"):
            GMPEParams(Mw=9.0, R=10.0, Vs30=760.0)

    def test_validation_R_positive(self):
        from seiswave.core.gmpe import GMPEParams
        with pytest.raises(ValueError, match="R"):
            GMPEParams(Mw=7.0, R=-1.0, Vs30=760.0)

    def test_validation_Vs30_range(self):
        from seiswave.core.gmpe import GMPEParams
        with pytest.raises(ValueError, match="Vs30"):
            GMPEParams(Mw=7.0, R=10.0, Vs30=100.0)
        with pytest.raises(ValueError, match="Vs30"):
            GMPEParams(Mw=7.0, R=10.0, Vs30=2500.0)

    def test_validation_dip_range(self):
        from seiswave.core.gmpe import GMPEParams
        with pytest.raises(ValueError, match="dip"):
            GMPEParams(Mw=7.0, R=10.0, Vs30=760.0, dip=95.0)


# ═══════════════════ GMPEAdapter — 基本计算 ═══════════════════

class TestGMPEAdapterBasic:
    def test_default_periods_shape(self):
        from seiswave.core.gmpe import GMPEAdapter
        T = GMPEAdapter.default_periods(n=100)
        assert len(T) == 100
        assert T[0] == pytest.approx(0.1, rel=1e-6)
        assert T[-1] == pytest.approx(10.0, rel=1e-6)
        assert np.all(np.diff(T) > 0)

    def test_returns_tuple_of_arrays(self):
        from seiswave.core.gmpe import GMPEAdapter
        T, Sa = GMPEAdapter.compute_spectrum(7.0, 50.0, 760.0)
        assert isinstance(T, np.ndarray)
        assert isinstance(Sa, np.ndarray)
        assert len(T) == len(Sa)
        assert len(T) == 100  # default

    def test_Sa_positive(self):
        from seiswave.core.gmpe import GMPEAdapter
        T, Sa = GMPEAdapter.compute_spectrum(7.0, 50.0, 760.0)
        assert np.all(Sa > 0)

    def test_user_periods_respected(self):
        from seiswave.core.gmpe import GMPEAdapter
        periods = np.array([0.1, 0.5, 1.0, 2.0])
        T, Sa = GMPEAdapter.compute_spectrum(7.0, 50.0, 760.0, periods=periods)
        np.testing.assert_allclose(T, periods)

    def test_user_periods_negative_raises(self):
        from seiswave.core.gmpe import GMPEAdapter
        with pytest.raises(ValueError, match="periods"):
            GMPEAdapter.compute_spectrum(7.0, 50.0, 760.0,
                                          periods=np.array([-0.1, 0.5]))

    def test_use_median_vs_sigma(self):
        from seiswave.core.gmpe import GMPEAdapter
        T, Sa_median = GMPEAdapter.compute_spectrum(7.0, 50.0, 760.0, use_median=True)
        _, Sa_sigma = GMPEAdapter.compute_spectrum(7.0, 50.0, 760.0, use_median=False)
        # +1σ 应大于中位值
        assert np.all(Sa_sigma > Sa_median)


# ═══════════════════ Sa 值合理范围验证 ═══════════════════

class TestSaRanges:
    """验证典型场景下的 Sa 值落在工程合理范围内"""

    def test_farfield_M7_R50_PGA_range(self):
        """远场 M7 R50km：PGA (T=0.01s) 应在 0.1-0.5g 量级"""
        from seiswave.core.gmpe import GMPEAdapter
        T, Sa = GMPEAdapter.compute_ff(7.0, 50.0, 760.0)
        pga = Sa[0]  # T=0.01s 近似 PGA
        assert 0.05 < pga < 1.0, f"PGA={pga:.3f}g 超出远场 M7R50 的合理范围"

    def test_farfield_M7_R50_long_period_decrease(self):
        """远场长周期 Sa 应随周期增大而减小"""
        from seiswave.core.gmpe import GMPEAdapter
        T, Sa = GMPEAdapter.compute_ff(7.0, 50.0, 760.0)
        # 取 T=1s 和 T=5s 比较
        idx_1 = np.argmin(np.abs(T - 1.0))
        idx_5 = np.argmin(np.abs(T - 5.0))
        assert Sa[idx_5] < Sa[idx_1], "远场长周期应衰减"

    def test_nearfield_M7_R5_PGA_higher_than_farfield(self):
        """同震级同场地，近场 PGA 应显著大于远场"""
        from seiswave.core.gmpe import GMPEAdapter
        _, Sa_ff = GMPEAdapter.compute_ff(7.0, 50.0, 760.0)
        _, Sa_nf = GMPEAdapter.compute_nf(7.0, 5.0, 760.0)
        assert Sa_nf[0] > Sa_ff[0] * 2, "近场 PGA 应显著高于远场"

    def test_nearfield_vs_farfield_at_same_R(self):
        """同参数下，近场谱在短周期应高于远场谱（距离饱和效应）"""
        from seiswave.core.gmpe import GMPEAdapter
        _, Sa_ff = GMPEAdapter.compute_ff(7.0, 5.0, 760.0)
        _, Sa_nf = GMPEAdapter.compute_nf(7.0, 5.0, 760.0)
        # 短周期（PGA 附近）近场应更强
        assert Sa_nf[0] > Sa_ff[0]

    def test_nfp_long_period_amplification(self):
        """近场脉冲长周期 (T>=0.5s) 应相对 NF 有额外放大"""
        from seiswave.core.gmpe import GMPEAdapter
        T, Sa_nf = GMPEAdapter.compute_nf(7.5, 3.0, 760.0)
        _, Sa_nfp = GMPEAdapter.compute_nfp(7.5, 3.0, 760.0)
        idx_long = T >= 0.5
        assert np.all(Sa_nfp[idx_long] >= Sa_nf[idx_long]), \
            "NFP 长周期应不小于 NF"
        # 至少在某些长周期点有明显放大
        assert np.max(Sa_nfp[idx_long]) > np.max(Sa_nf[idx_long]) * 1.05

    def test_large_Mw_higher_Sa(self):
        """同距离同场地，大震 Sa 应大于小震"""
        from seiswave.core.gmpe import GMPEAdapter
        _, Sa_m6 = GMPEAdapter.compute_spectrum(6.0, 30.0, 760.0)
        _, Sa_m8 = GMPEAdapter.compute_spectrum(8.0, 30.0, 760.0)
        assert np.mean(Sa_m8) > np.mean(Sa_m6), "大震平均谱应更高"

    def test_soft_site_higher_long_period(self):
        """软场地长周期放大"""
        from seiswave.core.gmpe import GMPEAdapter
        T, Sa_rock = GMPEAdapter.compute_ff(7.0, 50.0, 1500.0)
        _, Sa_soft = GMPEAdapter.compute_ff(7.0, 50.0, 200.0)
        idx_long = T > 0.5
        # 软场地长周期平均 Sa 应大于硬场地
        assert np.mean(Sa_soft[idx_long]) > np.mean(Sa_rock[idx_long])

    def test_reverse_vs_normal(self):
        """逆断层 Sa 应略高于正断层"""
        from seiswave.core.gmpe import GMPEAdapter, FaultType
        _, Sa_rev = GMPEAdapter.compute_spectrum(
            7.0, 30.0, 760.0, fault_type=FaultType.REVERSE
        )
        _, Sa_norm = GMPEAdapter.compute_spectrum(
            7.0, 30.0, 760.0, fault_type=FaultType.NORMAL
        )
        assert np.mean(Sa_rev) > np.mean(Sa_norm), "逆断层平均谱应高于正断层"


# ═══════════════════ FEMA P695 预设 ═══════════════════

class TestFEMAScenarios:
    def test_get_scenario_by_name(self):
        from seiswave.core.gmpe import get_fema_scenario, FEMA_P695_SCENARIOS
        s = get_fema_scenario("FF_M7_R50_SS")
        assert s.Mw == 7.0
        assert s.R == 50.0
        assert s.fault_type.value == "strike_slip"

    def test_unknown_scenario_raises(self):
        from seiswave.core.gmpe import get_fema_scenario
        with pytest.raises(ValueError, match="未知场景"):
            get_fema_scenario("NOT_A_SCENARIO")

    def test_compute_fema_spectrum(self):
        from seiswave.core.gmpe import compute_fema_spectrum
        T, Sa = compute_fema_spectrum("FF_M7_R50_SS")
        assert len(T) == len(Sa)
        assert np.all(Sa > 0)
        # PGA 应在合理范围
        assert 0.05 < Sa[0] < 1.0

    def test_all_scenarios_positive_Sa(self):
        from seiswave.core.gmpe import FEMA_P695_SCENARIOS, compute_fema_spectrum
        for s in FEMA_P695_SCENARIOS:
            T, Sa = compute_fema_spectrum(s.name)
            assert np.all(Sa > 0), f"场景 {s.name} 出现非正 Sa"

    def test_nfp_higher_than_ff_for_same_Mw(self):
        """同震级下，NFP 长周期应显著高于 FF"""
        from seiswave.core.gmpe import compute_fema_spectrum
        T, Sa_ff = compute_fema_spectrum("FF_M7_R50_SS")
        _, Sa_nfp = compute_fema_spectrum("NFP_M7_R2_SS")
        idx_long = T >= 1.0
        assert np.mean(Sa_nfp[idx_long]) > np.mean(Sa_ff[idx_long])


# ═══════════════════ 自定义目标谱 ═══════════════════

class TestCustomSpectrum:
    def test_basic_creation(self):
        from seiswave.core.gmpe import CustomSpectrum
        cs = CustomSpectrum(
            periods=np.array([0.1, 0.5, 1.0, 2.0]),
            Sa=np.array([0.5, 0.4, 0.3, 0.2]),
            name="test_spec"
        )
        assert cs.name == "test_spec"
        np.testing.assert_allclose(cs.periods, [0.1, 0.5, 1.0, 2.0])

    def test_validation_length_mismatch(self):
        from seiswave.core.gmpe import CustomSpectrum
        with pytest.raises(ValueError, match="长度必须相同"):
            CustomSpectrum(periods=np.array([0.1, 0.5]), Sa=np.array([0.5]))

    def test_validation_empty(self):
        from seiswave.core.gmpe import CustomSpectrum
        with pytest.raises(ValueError, match="不能为空"):
            CustomSpectrum(periods=np.array([]), Sa=np.array([]))

    def test_validation_negative_period(self):
        from seiswave.core.gmpe import CustomSpectrum
        with pytest.raises(ValueError, match="periods"):
            CustomSpectrum(periods=np.array([-0.1, 0.5]), Sa=np.array([0.5, 0.4]))

    def test_validation_negative_Sa(self):
        from seiswave.core.gmpe import CustomSpectrum
        with pytest.raises(ValueError, match="Sa"):
            CustomSpectrum(periods=np.array([0.1, 0.5]), Sa=np.array([0.5, -0.1]))

    def test_interpolate(self):
        from seiswave.core.gmpe import CustomSpectrum
        cs = CustomSpectrum(
            periods=np.array([0.1, 1.0, 10.0]),
            Sa=np.array([1.0, 0.5, 0.1]),
        )
        target = np.array([0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
        Sa_interp = cs.interpolate(target)
        assert len(Sa_interp) == len(target)
        # 边界精确匹配
        assert Sa_interp[0] == pytest.approx(1.0, rel=1e-6)
        assert Sa_interp[-1] == pytest.approx(0.1, rel=1e-6)
        # 中间单调递减（对数线性插值保单调）
        assert np.all(np.diff(Sa_interp) <= 0)

    def test_interpolate_extrapolation(self):
        """对数插值在范围外应能外推（数值合理）"""
        from seiswave.core.gmpe import CustomSpectrum
        cs = CustomSpectrum(
            periods=np.array([0.1, 1.0, 10.0]),
            Sa=np.array([1.0, 0.5, 0.1]),
        )
        target = np.array([0.01, 20.0])
        Sa_interp = cs.interpolate(target)
        assert len(Sa_interp) == 2
        assert np.all(np.isfinite(Sa_interp))
        assert np.all(Sa_interp > 0)


# ═══════════════════ 统一入口 get_target_spectrum ═══════════════════

class TestGetTargetSpectrum:
    def test_gmpe_source(self):
        from seiswave.core.gmpe import get_target_spectrum
        T, Sa = get_target_spectrum("gmpe", Mw=7.0, R=50.0, Vs30=760.0)
        assert len(T) == len(Sa)
        assert np.all(Sa > 0)

    def test_gmpe_missing_params_raises(self):
        from seiswave.core.gmpe import get_target_spectrum
        with pytest.raises(ValueError, match="Mw"):
            get_target_spectrum("gmpe", R=50.0, Vs30=760.0)

    def test_custom_source(self):
        from seiswave.core.gmpe import get_target_spectrum, CustomSpectrum
        cs = CustomSpectrum(
            periods=np.array([0.1, 0.5, 1.0]),
            Sa=np.array([0.5, 0.4, 0.3]),
        )
        T, Sa = get_target_spectrum("custom", custom_spec=cs)
        np.testing.assert_allclose(T, cs.periods)
        np.testing.assert_allclose(Sa, cs.Sa)

    def test_custom_source_with_interpolation(self):
        from seiswave.core.gmpe import get_target_spectrum, CustomSpectrum
        cs = CustomSpectrum(
            periods=np.array([0.1, 1.0, 10.0]),
            Sa=np.array([1.0, 0.5, 0.1]),
        )
        target_periods = np.array([0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
        T, Sa = get_target_spectrum("custom", target_periods, custom_spec=cs)
        np.testing.assert_allclose(T, target_periods)
        assert len(Sa) == 6

    def test_fema_source(self):
        from seiswave.core.gmpe import get_target_spectrum
        T, Sa = get_target_spectrum("fema", fema_name="FF_M7_R50_SS")
        assert len(T) == len(Sa)
        assert np.all(Sa > 0)

    def test_unknown_source_raises(self):
        from seiswave.core.gmpe import get_target_spectrum
        with pytest.raises(ValueError, match="未知的 source"):
            get_target_spectrum("invalid")


# ═══════════════════ 兼容接口 compute_gmpe_spectrum ═══════════════════

class TestCompatInterface:
    def test_string_params(self):
        from seiswave.core.gmpe import compute_gmpe_spectrum
        T, Sa = compute_gmpe_spectrum(
            7.0, 50.0, 760.0,
            fault_type="reverse", motion_type="near_field"
        )
        assert len(T) == len(Sa)
        assert np.all(Sa > 0)

    def test_unknown_string_defaults(self):
        from seiswave.core.gmpe import compute_gmpe_spectrum
        T, Sa = compute_gmpe_spectrum(
            7.0, 50.0, 760.0,
            fault_type="unknown_type", motion_type="unknown_type"
        )
        assert len(T) == len(Sa)
        # 未知参数应回退到默认值（strike_slip, far_field）


# ═══════════════════ 数值稳定性 ═══════════════════

class TestNumericalStability:
    def test_extremely_short_period(self):
        """超短周期不应爆炸"""
        from seiswave.core.gmpe import GMPEAdapter
        periods = np.array([0.001, 0.005])
        T, Sa = GMPEAdapter.compute_spectrum(7.0, 50.0, 760.0, periods=periods)
        assert np.all(np.isfinite(Sa))
        assert np.all(Sa > 0)

    def test_large_distance(self):
        """大距离不应出现负值或 NaN"""
        from seiswave.core.gmpe import GMPEAdapter
        T, Sa = GMPEAdapter.compute_spectrum(7.0, 300.0, 760.0)
        assert np.all(np.isfinite(Sa))
        assert np.all(Sa > 0)
        # 大距离 Sa 应很小
        assert np.max(Sa) < 0.5

    def test_zero_distance_nearfield(self):
        """零距离近场应有有限值"""
        from seiswave.core.gmpe import GMPEAdapter
        T, Sa = GMPEAdapter.compute_nf(7.0, 0.0, 760.0)
        assert np.all(np.isfinite(Sa))
        assert np.all(Sa > 0)
