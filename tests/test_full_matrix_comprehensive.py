"""
SeisWave 全规范组合 + 特殊地震动 大矩阵测试

覆盖所有 GB50011 参数组合 + 所有特殊地震动类型
验证每个组合都能正确生成结果（不报错、非 None、基本属性正确）
"""

import numpy as np
import pytest

from seiswave.core import CodeSpectrum, Spectra, WaveGenerator
from seiswave.core.generator import (
    FarFieldGenerator, NearFieldNoPulseGenerator, NearFieldPulseGenerator
)
from seiswave.core.pulse import BakerPulseDetector


# ── 1. 一般人工波：全规范组合大矩阵 ──
class TestGeneralWaveFullMatrix:
    """GB50011 全参数组合 × 生成参数组合"""

    INTENSITIES = [6, 7, 8, 9]
    GROUPS = [1, 2, 3]
    CATEGORIES = ["I0", "I", "II", "III", "IV"]
    LEVELS = ["frequent", "design", "rare"]

    @pytest.mark.parametrize("intensity", INTENSITIES)
    @pytest.mark.parametrize("group", GROUPS)
    @pytest.mark.parametrize("category", CATEGORIES)
    @pytest.mark.parametrize("level", LEVELS)
    def test_all_combinations_generate(self, intensity, group, category, level):
        """所有规范组合都能生成非 None 结果"""
        try:
            params = CodeSpectrum.get_params(intensity, group, category, level)
        except (ValueError, KeyError):
            pytest.skip(f"不支持组合: {intensity}度-{group}组-{category}-{level}")

        periods = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
        sa = CodeSpectrum.gb50011(periods, params["Tg"], params["alpha_max"], zeta=0.05)
        pga = float(sa.max())

        sig = WaveGenerator.generate(
            target_spectrum=sa, periods=periods,
            n=2000, dt=0.02, zeta=0.05, pga=pga,
            tol=0.05, max_iter=30, fm=1, n_trials=1,
        )

        assert sig is not None, f"生成失败: {intensity}度-{group}组-{category}-{level}"
        assert len(sig.acc) == 2000
        assert sig.dt == 0.02
        assert float(np.max(np.abs(sig.acc))) > 0.001


# ── 2. 一般人工波：不同生成参数组合 ──
class TestGeneralWaveGeneratorParams:
    """同一规范谱 × 不同生成参数"""

    PARAMS = [
        (0.02, 2000, 30, 0.05),
        (0.01, 4000, 20, 0.08),
        (0.02, 1024, 15, 0.10),
        (0.01, 2048, 25, 0.06),
    ]

    @pytest.mark.parametrize("dt,n,max_iter,tol", PARAMS)
    def test_different_generation_params(self, dt, n, max_iter, tol):
        """不同 dt, n, max_iter, tol 组合"""
        periods = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
        params = CodeSpectrum.get_params(8, 1, "I0", "frequent")
        sa = CodeSpectrum.gb50011(periods, params["Tg"], params["alpha_max"], zeta=0.05)
        pga = float(sa.max())

        sig = WaveGenerator.generate(
            target_spectrum=sa, periods=periods,
            n=n, dt=dt, zeta=0.05, pga=pga,
            tol=tol, max_iter=max_iter, fm=1, n_trials=1,
        )

        assert sig is not None
        assert len(sig.acc) == n
        assert sig.dt == dt


# ── 3. 特殊地震动：FF 大矩阵 ──
class TestFarFieldFullMatrix:
    """FarField 全参数组合"""

    Mw_VALUES = [6.0, 6.5, 7.0, 7.5, 8.0]
    R_VALUES = [10.0, 30.0, 50.0, 80.0, 120.0]
    VS30_VALUES = [260, 360, 540, 760, 1000, 1500]

    @pytest.mark.parametrize("Mw", Mw_VALUES)
    @pytest.mark.parametrize("R", R_VALUES)
    @pytest.mark.parametrize("Vs30", VS30_VALUES)
    def test_ff_all_combinations(self, Mw, R, Vs30):
        """FF 所有 Mw × R × Vs30 组合"""
        sig = FarFieldGenerator.generate(
            Mw=Mw, R=R, Vs30=Vs30,
            n=1024, dt=0.02, zeta=0.05,
            max_iter=15, tol=0.10,
        )
        assert sig is not None, f"FF 生成失败: Mw={Mw}, R={R}, Vs30={Vs30}"
        assert len(sig.acc) == 1024
        assert float(np.max(np.abs(sig.acc))) > 0.001

    FAULT_TYPES = ["strike_slip", "normal", "reverse", "reverse_oblique"]

    @pytest.mark.parametrize("fault_type", FAULT_TYPES)
    def test_ff_fault_types(self, fault_type):
        """FF 不同断层类型"""
        sig = FarFieldGenerator.generate(
            Mw=7.0, R=50.0, Vs30=760.0, fault_type=fault_type,
            n=512, dt=0.02, zeta=0.05,
            max_iter=10, tol=0.10,
        )
        assert sig is not None


# ── 4. 特殊地震动：NF 大矩阵 ──
class TestNearFieldNoPulseFullMatrix:
    """NearFieldNoPulse 全参数组合"""

    Mw_VALUES = [6.0, 6.5, 7.0, 7.5, 8.0]
    R_VALUES = [3.0, 5.0, 8.0, 12.0, 20.0]
    VS30_VALUES = [260, 360, 540, 760, 1000, 1500]

    @pytest.mark.parametrize("Mw", Mw_VALUES)
    @pytest.mark.parametrize("R", R_VALUES)
    @pytest.mark.parametrize("Vs30", VS30_VALUES)
    def test_nf_all_combinations(self, Mw, R, Vs30):
        """NF 所有 Mw × R × Vs30 组合"""
        sig = NearFieldNoPulseGenerator.generate(
            Mw=Mw, R=R, Vs30=Vs30,
            n=1024, dt=0.02, zeta=0.05,
            max_iter=15, tol=0.10,
        )
        assert sig is not None, f"NF 生成失败: Mw={Mw}, R={R}, Vs30={Vs30}"
        assert len(sig.acc) == 1024
        assert float(np.max(np.abs(sig.acc))) > 0.001


# ── 5. 特殊地震动：NFP 大矩阵 ──
class TestNearFieldPulseFullMatrix:
    """NearFieldPulse 全参数组合"""

    Mw_VALUES = [6.5, 7.0, 7.2, 7.5, 8.0]
    R_VALUES = [3.0, 4.0, 5.0, 8.0, 12.0]
    VS30_VALUES = [260, 360, 540, 760, 1000]

    @pytest.mark.parametrize("Mw", Mw_VALUES)
    @pytest.mark.parametrize("R", R_VALUES)
    @pytest.mark.parametrize("Vs30", VS30_VALUES)
    def test_nfp_all_combinations(self, Mw, R, Vs30):
        """NFP 所有 Mw × R × Vs30 组合"""
        sig = NearFieldPulseGenerator.generate(
            Mw=Mw, R=R, Vs30=Vs30,
            n=1024, dt=0.01, zeta=0.05,
            max_iter=15, tol=0.10,
        )
        assert sig is not None, f"NFP 生成失败: Mw={Mw}, R={R}, Vs30={Vs30}"
        assert len(sig.acc) == 1024

    # 脉冲参数覆盖
    Tp_OVERRIDES = [None, 0.8, 1.0, 1.5, 2.0]
    A_OVERRIDES = [None, 50.0, 100.0, 150.0, 200.0]

    @pytest.mark.parametrize("Tp", Tp_OVERRIDES)
    @pytest.mark.parametrize("A", A_OVERRIDES)
    def test_nfp_pulse_override(self, Tp, A):
        """NFP 脉冲参数覆盖"""
        kwargs = {
            "Mw": 7.0, "R": 4.0, "Vs30": 760.0,
            "n": 512, "dt": 0.01, "zeta": 0.05,
            "max_iter": 10, "tol": 0.10,
        }
        if Tp is not None:
            kwargs["Tp_override"] = Tp
        if A is not None:
            kwargs["A_override"] = A

        sig = NearFieldPulseGenerator.generate(**kwargs)
        assert sig is not None


# ── 6. 跨类型对比：同参数下不同生成器都能工作 ──
class TestCrossTypeConsistency:
    """验证不同生成器在相同基础参数下都能工作"""

    def test_all_generators_with_common_params(self):
        """所有生成器使用相同 Mw/R/Vs30 都能生成"""
        Mw, R, Vs30 = 7.0, 5.0, 760.0

        sig_ff = FarFieldGenerator.generate(Mw=Mw, R=R * 10, Vs30=Vs30, n=512, dt=0.02)
        sig_nf = NearFieldNoPulseGenerator.generate(Mw=Mw, R=R, Vs30=Vs30, n=512, dt=0.02)
        sig_nfp = NearFieldPulseGenerator.generate(Mw=Mw, R=R, Vs30=Vs30, n=512, dt=0.01)

        assert sig_ff is not None
        assert sig_nf is not None
        assert sig_nfp is not None

    def test_pga_consistency(self):
        """所有生成器生成的 PGA 都是正数"""
        for cls, kwargs in [
            (FarFieldGenerator, {"Mw": 7.0, "R": 50.0, "Vs30": 760.0, "n": 512, "dt": 0.02}),
            (NearFieldNoPulseGenerator, {"Mw": 7.0, "R": 5.0, "Vs30": 760.0, "n": 512, "dt": 0.02}),
            (NearFieldPulseGenerator, {"Mw": 7.0, "R": 4.0, "Vs30": 760.0, "n": 512, "dt": 0.01}),
        ]:
            sig = cls.generate(**kwargs)
            pga = float(np.max(np.abs(sig.acc)))
            assert pga > 0.01, f"{cls.__name__} PGA={pga} 太小"


# ── 7. 边界条件：极端参数 ──
class TestExtremeParams:
    """极端参数验证"""

    def test_very_small_mw(self):
        """小震级"""
        sig = FarFieldGenerator.generate(Mw=5.5, R=100.0, Vs30=760.0, n=512, dt=0.02, max_iter=10)
        assert sig is not None

    def test_very_large_mw(self):
        """大震级"""
        sig = FarFieldGenerator.generate(Mw=8.5, R=150.0, Vs30=760.0, n=512, dt=0.02, max_iter=10)
        assert sig is not None

    def test_very_close_distance(self):
        """近距离"""
        sig = NearFieldNoPulseGenerator.generate(Mw=7.0, R=1.0, Vs30=760.0, n=512, dt=0.02, max_iter=10)
        assert sig is not None

    def test_very_soft_soil(self):
        """软土"""
        sig = FarFieldGenerator.generate(Mw=7.0, R=50.0, Vs30=180.0, n=512, dt=0.02, max_iter=10)
        assert sig is not None

    def test_very_hard_rock(self):
        """硬岩"""
        sig = FarFieldGenerator.generate(Mw=7.0, R=50.0, Vs30=2000.0, n=512, dt=0.02, max_iter=10)
        assert sig is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
