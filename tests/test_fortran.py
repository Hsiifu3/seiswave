"""
Task 1.5: Fortran 集成验证测试

验证 Fortran 加速后的反应谱计算和人工波生成。
"""

import sys
import os
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from seiswave.core.fortran_bridge import HAS_FORTRAN, spectrum_mixed, spectrum_avd, acc2vd
from seiswave.core.spectrum import Spectra
from seiswave.core.code_spec import CodeSpectrum
from seiswave.core.generator import WaveGenerator


def test_fortran_available():
    """Fortran 模块应可用"""
    assert HAS_FORTRAN, "Fortran module not available"
    print("✅ HAS_FORTRAN = True")


def test_spectrum_mixed_basic():
    """反应谱基本计算"""
    np.random.seed(42)
    acc = np.random.randn(2000) * 0.1
    dt = 0.02
    periods = np.logspace(np.log10(0.1), np.log10(6.0), 50)

    spa, spi = spectrum_mixed(acc, dt, 0.05, periods)
    assert spa.shape == (50,), f"shape mismatch: {spa.shape}"
    assert np.all(np.isfinite(spa)), "non-finite values in spa"
    assert np.max(np.abs(spa)) > 0, "all zeros"
    print(f"✅ spectrum_mixed: max|spa|={np.max(np.abs(spa)):.4f}")


def test_spectrum_avd():
    """完整反应谱（Sa, Sv, Sd, Se）"""
    np.random.seed(42)
    acc = np.random.randn(2000) * 0.1
    dt = 0.02
    periods = np.logspace(np.log10(0.1), np.log10(6.0), 30)

    sa, spi, sv, sd, se = spectrum_avd(acc, dt, 0.05, periods)
    assert sa.shape == (30,)
    assert np.all(sa >= 0), "negative Sa values"
    assert np.all(sv >= 0), "negative Sv values"
    assert np.all(sd >= 0), "negative Sd values"
    print(f"✅ spectrum_avd: Sa max={np.max(sa):.4f}, Sv max={np.max(sv):.4f}")


def test_spectra_compute_uses_fortran():
    """Spectra.compute(method='mixed') 应走 Fortran 路径"""
    np.random.seed(42)
    acc = np.random.randn(2000) * 0.1
    dt = 0.02
    periods = np.logspace(np.log10(0.1), np.log10(6.0), 50)

    t0 = time.time()
    sp = Spectra.compute(acc, dt, periods, 0.05, method='mixed')
    t_fortran = time.time() - t0

    assert sp.sa is not None
    assert sp.sv is not None
    assert sp.sd is not None
    assert t_fortran < 0.5, f"too slow ({t_fortran:.2f}s), Fortran not used?"
    print(f"✅ Spectra.compute(mixed): {t_fortran:.4f}s for {len(periods)} periods")


def test_spectrum_speed():
    """Numba/Python 反应谱应与 Fortran 处于同一数量级"""
    np.random.seed(42)
    acc = np.random.randn(4096) * 0.2
    dt = 0.02
    periods = np.logspace(np.log10(0.1), np.log10(6.0), 100)

    # Fortran / mixed
    t0 = time.time()
    sp_f = Spectra.compute(acc, dt, periods, 0.05, method='mixed')
    t_fortran = time.time() - t0

    # Numba Python 串行 vs 并行（应完全等价）
    t0 = time.time()
    sp_s = Spectra.compute(acc, dt, periods, 0.05, method='newmark', parallel=False)
    t_serial = time.time() - t0

    t0 = time.time()
    sp_p = Spectra.compute(acc, dt, periods, 0.05, method='newmark', parallel=True)
    t_parallel = time.time() - t0

    print(f"✅ Speed: Fortran={t_fortran:.4f}s, Serial={t_serial:.4f}s, Parallel={t_parallel:.4f}s")
    assert t_fortran < 0.5, f"Fortran too slow: {t_fortran:.2f}s"
    assert t_parallel < 0.5, f"Python too slow: {t_parallel:.2f}s"
    assert np.allclose(sp_s.sa, sp_p.sa, rtol=1e-10), "并行与串行结果不一致"


def test_acc2vd():
    """加速度积分"""
    acc = np.ones(100) * 1.0
    dt = 0.01
    v, d = acc2vd(acc, dt)
    # v should be roughly linear: v(t) = t
    assert abs(v[-1] - 0.99) < 0.02, f"v[-1]={v[-1]}"
    assert d[-1] > 0
    print(f"✅ acc2vd: v[-1]={v[-1]:.4f}, d[-1]={d[-1]:.4f}")


def test_generator_fortran():
    """人工波生成（Fortran 路径）"""
    periods = np.linspace(0.1, 6.0, 50)
    sa_target = CodeSpectrum.gb50011(periods, Tg=0.35, alpha_max=0.16, zeta=0.05)

    t0 = time.time()
    result = WaveGenerator.generate(sa_target, periods, n=4096, dt=0.02,
                                     zeta=0.05, pga=0.16, tol=0.05,
                                     max_iter=30, fm=1)
    elapsed = time.time() - t0

    assert len(result.acc) == 4096
    assert abs(np.max(np.abs(result.acc)) - 0.16) < 0.01, \
        f"PGA={np.max(np.abs(result.acc)):.4f}, expected 0.16"

    # 验证反应谱匹配
    sp = Spectra.compute(result.acc, result.dt, periods, 0.05)
    e = (sp.sa - sa_target) / np.maximum(sa_target, 1e-30)
    rmse = np.sqrt(np.mean(e**2))

    print(f"✅ generator (Fortran): {elapsed:.1f}s, PGA={np.max(np.abs(result.acc)):.4f}, RMSE={rmse:.4f}")
    assert elapsed < 30, f"too slow: {elapsed:.1f}s"
    assert rmse < 0.15, f"RMSE too large: {rmse:.4f}"


def test_generator_freq_domain():
    """人工波生成 — 频域法（fm=0）"""
    periods = np.linspace(0.1, 6.0, 50)
    sa_target = CodeSpectrum.gb50011(periods, Tg=0.35, alpha_max=0.16, zeta=0.05)

    result = WaveGenerator.generate(sa_target, periods, n=4096, dt=0.02,
                                     zeta=0.05, pga=0.16, tol=0.05,
                                     max_iter=30, fm=0)
    assert len(result.acc) == 4096
    print(f"✅ generator (fm=0): PGA={np.max(np.abs(result.acc)):.4f}")


if __name__ == '__main__':
    tests = [
        test_fortran_available,
        test_spectrum_mixed_basic,
        test_spectrum_avd,
        test_spectra_compute_uses_fortran,
        test_spectrum_speed,
        test_acc2vd,
        test_generator_fortran,
        test_generator_freq_domain,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"❌ {t.__name__}: {e}")
            failed += 1

    print(f"\n{'='*40}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("🎉 All tests passed!")
