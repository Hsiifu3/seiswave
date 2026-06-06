"""测试 FF/NF/NFP 使用 GB50011 规范设计谱 + 近场系数（方案甲）。

覆盖：
- FF/NF/NFP code 模式输出谱与 GB50011 × 近场系数的吻合
- 近场系数边界（_near_field_factor）
- NFP code 模式脉冲特性
- GMPE 回退（spectrum_source="gmpe" 或缺 code_sa）
"""
import numpy as np
import pytest


@pytest.fixture
def gb50011_spectrum():
    """8度0.2g中硬场地 GB50011 谱（Tg=0.40, alpha_max=0.08）。"""
    from seiswave.core import CodeSpectrum, Spectra
    periods = Spectra.default_periods(0.01, 6.0, 300, mode="mixed")
    params = CodeSpectrum.get_params(intensity=8, group=2, site_class="II", level="frequent")
    sa = CodeSpectrum.gb50011(periods, params["Tg"], params["alpha_max"], zeta=0.05)
    return periods, sa, params


def test_near_field_factor_boundaries():
    """近场系数边界正确（GB50011-2010 §3.10 + 附录L）。"""
    from seiswave.core.generator import _near_field_factor
    from seiswave.core.gmpe import MotionType

    # FF 恒 1.0
    assert _near_field_factor(3.0, MotionType.FAR_FIELD) == 1.0
    assert _near_field_factor(50.0, MotionType.FAR_FIELD) == 1.0

    # NF / NFP: <5 → 1.5; 5–10 → 1.25; >10 → 1.0
    assert _near_field_factor(4.9, MotionType.NEAR_FIELD) == 1.5
    assert _near_field_factor(5.0, MotionType.NEAR_FIELD) == 1.25
    assert _near_field_factor(7.5, MotionType.NEAR_FIELD) == 1.25
    assert _near_field_factor(10.0, MotionType.NEAR_FIELD) == 1.25
    assert _near_field_factor(10.1, MotionType.NEAR_FIELD) == 1.0
    assert _near_field_factor(50.0, MotionType.NEAR_FIELD) == 1.0

    assert _near_field_factor(3.0, MotionType.NEAR_FIELD_PULSE) == 1.5
    assert _near_field_factor(8.0, MotionType.NEAR_FIELD_PULSE) == 1.25
    assert _near_field_factor(20.0, MotionType.NEAR_FIELD_PULSE) == 1.0


def test_ff_code_spectrum_match(gb50011_spectrum):
    """FF code 模式：输出谱应≈ GB50011 谱（因子=1.0）。"""
    from seiswave.core.generator import create_ground_motion
    from seiswave.core import Spectra

    periods, code_sa, _ = gb50011_spectrum
    sig = create_ground_motion(
        "FF", Mw=7.0, R=50.0, n=2000, dt=0.02, max_iter=8,
        spectrum_source="code", code_periods=periods, code_sa=code_sa,
    )
    assert sig.near_field_factor == 1.0
    assert sig.spectrum_source == "code"

    resp = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method="mixed").sa
    # 0.04–2.0s 范围，RMS < 10%
    mask = (periods >= 0.04) & (periods <= 2.0)
    rms_err = np.sqrt(np.mean(((resp[mask] - code_sa[mask]) / code_sa[mask])**2)) * 100
    assert rms_err < 10.0, f"FF code 模式谱匹配误差 {rms_err:.1f}% 超标"


def test_nf_code_spectrum_with_factors(gb50011_spectrum):
    """NF code 模式：R=3/8/20 → 因子1.5/1.25/1.0，谱≈ code_sa × 因子。"""
    from seiswave.core.generator import create_ground_motion
    from seiswave.core import Spectra

    periods, code_sa, _ = gb50011_spectrum
    cases = [(3.0, 1.5), (8.0, 1.25), (20.0, 1.0)]

    for R, expected_factor in cases:
        sig = create_ground_motion(
            "NF", Mw=7.0, R=R, n=2000, dt=0.01, max_iter=8,
            spectrum_source="code", code_periods=periods, code_sa=code_sa,
        )
        assert sig.near_field_factor == expected_factor
        assert sig.spectrum_source == "code"

        resp = Spectra.compute(sig.acc, sig.dt, periods, zeta=0.05, method="mixed").sa
        target = code_sa * expected_factor
        mask = (periods >= 0.04) & (periods <= 2.0)
        rms_err = np.sqrt(np.mean(((resp[mask] - target[mask]) / target[mask])**2)) * 100
        assert rms_err < 10.0, f"NF R={R} 因子{expected_factor} 谱匹配误差 {rms_err:.1f}% 超标"


def test_nfp_code_spectrum_has_pulse(gb50011_spectrum):
    """NFP code 模式：R=3 → 因子1.5，注入脉冲(pulse_params 存在)。"""
    from seiswave.core.generator import create_ground_motion

    periods, code_sa, _ = gb50011_spectrum
    sig = create_ground_motion(
        "NFP", Mw=7.0, R=3.0, n=2000, dt=0.01, max_iter=8,
        spectrum_source="code", code_periods=periods, code_sa=code_sa,
    )
    assert sig.near_field_factor == 1.5
    assert sig.spectrum_source == "code"
    # NFP 生成器必定注入脉冲(pulse_params 非空),但 Baker 识别 has_pulse 有随机性
    assert hasattr(sig, "pulse_params")
    assert sig.pulse_params is not None
    assert hasattr(sig, "pulse_acc")
    # 如果 Baker 识别出脉冲,残差应无明显脉冲
    if sig.pulse_metrics["has_pulse"]:
        assert sig.pulse_metrics["confidence"] >= 0.85
        assert sig.residual_has_pulse is False or sig.residual_pulse_metrics["confidence"] < 0.7


def test_gmpe_fallback_when_no_code_sa():
    """GMPE 回退：spectrum_source="code" 但无 code_sa → 走 GMPE 不崩。"""
    from seiswave.core.generator import create_ground_motion

    sig = create_ground_motion(
        "FF", Mw=7.0, R=50.0, n=2000, dt=0.02, max_iter=5,
        spectrum_source="code",  # code_sa=None 触发回退
    )
    assert sig.near_field_factor == 1.0
    assert sig.spectrum_source == "code"  # 虽然请求 code，但实际走了 GMPE
    assert sig.acc.size > 0


def test_gmpe_mode_explicit():
    """显式 spectrum_source="gmpe" 走 GMPE 路径。"""
    from seiswave.core.generator import create_ground_motion

    sig = create_ground_motion(
        "NF", Mw=7.0, R=3.0, n=2000, dt=0.01, max_iter=5,
        spectrum_source="gmpe",
    )
    assert sig.near_field_factor == 1.5
    assert sig.spectrum_source == "gmpe"
    assert sig.acc.size > 0
