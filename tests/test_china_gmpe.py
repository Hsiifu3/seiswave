"""测试 ChinaGMPEAdapter（第五代区划图 GB18306-2015，俞言祥分区模型）。

模型: lg Y = A + B·M + C·lg(R + D·e^(E·M))，震级以 6.5 分段。
由 aE/nE 构造 GB 设计谱: αmax=2.5·aE/g, Tg=2π·nE/aE。
系数来自俞言祥《新一代地震区划图…》表4(aE)、表5(nE)。
"""
import numpy as np
import pytest

from seiswave.core.gmpe import ChinaGMPEAdapter as C


def test_params_east_strong_major_m7_r10():
    """东部强震区长轴 M7 R10km — 对照手算值。"""
    pga, amax, Tg = C.compute_params(7.0, 10.0, "east_strong", "major")
    # 手算: aE=10^(3.533+0.432*7-2.315*lg(10+2.088*e^(0.399*7)))≈564 gal=0.574g
    assert pga == pytest.approx(0.574, abs=0.01)
    assert amax == pytest.approx(2.5 * 0.574, abs=0.03)   # 平台=2.5·aE/g
    assert Tg == pytest.approx(0.415, abs=0.02)


def test_magnitude_segmentation_at_6p5():
    """M=6.5 分段：6.4 与 6.6 用不同系数（A/B 跳变）。"""
    pga_lo, _, _ = C.compute_params(6.4, 20.0, "east_strong", "major")
    pga_hi, _, _ = C.compute_params(6.6, 20.0, "east_strong", "major")
    # 两侧都为正且单调（高震级更大）
    assert 0 < pga_lo < pga_hi


def test_region_and_axis_differences():
    """长轴 > 短轴；不同分区给出不同结果。"""
    pga_major, _, _ = C.compute_params(7.0, 15.0, "east_strong", "major")
    pga_minor, _, _ = C.compute_params(7.0, 15.0, "east_strong", "minor")
    assert pga_major > pga_minor   # 长轴方向地震动更强

    pga_tibet, _, _ = C.compute_params(7.0, 15.0, "tibet", "major")
    assert pga_tibet != pga_major  # 分区不同


def test_chinese_aliases():
    """中文/英文分区名与轴名均可识别。"""
    a = C.compute_params(7.0, 10.0, "east_strong", "major")
    b = C.compute_params(7.0, 10.0, "东部强震区", "长轴")
    assert a == pytest.approx(b)
    c = C.compute_params(6.0, 20.0, "青藏区", "短轴")
    assert c[0] > 0


def test_compute_spectrum_is_gb_shaped():
    """compute_spectrum 返回 GB 设计谱（g 单位，平台后下降）。"""
    periods = np.geomspace(0.01, 6.0, 300)
    per, sa = C.compute_spectrum(7.0, 10.0, "east_strong", "major", periods=periods)
    assert per.shape == sa.shape == (300,)
    assert np.all(sa > 0)
    # 平台峰值 ≈ αmax，长周期显著小于平台
    _, amax, Tg = C.compute_params(7.0, 10.0, "east_strong", "major")
    assert sa.max() == pytest.approx(amax, rel=0.05)
    assert sa[-1] < 0.5 * sa.max()   # 6s 处远小于平台


def test_distance_decay():
    """距离越大 PGA 越小（衰减）。"""
    pga10, _, _ = C.compute_params(7.0, 10.0, "east_strong", "major")
    pga50, _, _ = C.compute_params(7.0, 50.0, "east_strong", "major")
    pga100, _, _ = C.compute_params(7.0, 100.0, "east_strong", "major")
    assert pga10 > pga50 > pga100
