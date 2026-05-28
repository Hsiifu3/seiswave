import numpy as np
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from seiswave.core.generator import (
    WaveGenerator,
    FarFieldGenerator,
    NearFieldNoPulseGenerator,
    NearFieldPulseGenerator,
    create_ground_motion,
    _estimate_pga_from_spectrum,
)


# ── 39-40: C 库加载失败 ──
def test_c_lib_load_failure(monkeypatch):
    """模拟 _newmark.so 存在但 ctypes.CDLL 抛 OSError，覆盖 except 分支。"""
    import seiswave.core.generator as gen_mod
    orig_c_lib = gen_mod._c_lib
    try:
        # 让 os.path.exists 返回 True，但 CDLL 抛异常
        monkeypatch.setattr("os.path.exists", lambda p: True)
        monkeypatch.setattr("ctypes.CDLL", lambda p: (_ for _ in ()).throw(OSError("mock")))
        # 重新加载模块触发顶层 import 逻辑
        import importlib
        importlib.reload(gen_mod)
        assert gen_mod._c_lib is None
    finally:
        gen_mod._c_lib = orig_c_lib


# ── 126-173: _generate_fortran ──
def test_generate_fortran_mocked(monkeypatch):
    """mock fortran_bridge 组件，覆盖 _generate_fortran 完整路径。"""
    import seiswave.core.fortran_bridge as fb

    # 构造 mock _eqs 对象：用 SimpleNamespace 替代 MagicMock 避免嵌套问题
    mock_eqs_obj = SimpleNamespace(
        initartwave=lambda n, dt, zeta, P, SPAT: np.ones(n),
        fitspectrum=lambda acc, dt, zeta, P, SPAT, tol, max_iter, fm, flag: np.ones(len(acc)),
    )
    mock_eqs_mod = SimpleNamespace(eqs=mock_eqs_obj)

    monkeypatch.setattr(fb, "_eqs", mock_eqs_mod)
    monkeypatch.setattr(fb, "HAS_FORTRAN", True)

    def mock_spectrum_mixed(acc, dt, zeta, periods):
        return np.ones(len(periods)), np.ones(len(periods), dtype=np.int32)
    monkeypatch.setattr(fb, "spectrum_mixed", mock_spectrum_mixed)

    ctrl_periods = np.array([0.5, 1.0, 2.0])
    ctrl_target = np.array([0.2, 0.3, 0.25])

    result = WaveGenerator._generate_fortran(
        ctrl_periods, ctrl_target, len(ctrl_periods),
        n=64, dt=0.02, zeta=0.05, peak0=0.3,
        tol=0.05, max_iter=2, fm=0,
        progress_callback=lambda it, merr, aerr: None,
    )
    assert result is not None
    assert hasattr(result, "acc")
    assert len(result.acc) == 64


# ── 313: _init_art_wave continue (wk≈0) ──
def test_init_art_wave_wk_zero_continue(monkeypatch):
    """让 IPf1=0 使 k=0 时 wk=0，触发 continue 分支。"""
    monkeypatch.setattr(WaveGenerator, "_decrfindfirst", staticmethod(lambda a, x: 0))
    monkeypatch.setattr(WaveGenerator, "_decrfindlast", staticmethod(lambda a, x: 2))

    P = np.array([1.0, 0.5])
    SPT = np.array([0.2, 0.3])
    a = WaveGenerator._init_art_wave(
        n=8, dt=0.02, zeta=0.05, P=P, SPT=SPT, nP=2, seed=42
    )
    assert len(a) == 8


# ── 319: _init_art_wave log_arg else ──
def test_init_art_wave_log_arg_else(monkeypatch):
    """调整参数使 log_arg >= 1，触发 else 分支。"""
    monkeypatch.setattr(WaveGenerator, "_decrfindfirst", staticmethod(lambda a, x: 1))
    monkeypatch.setattr(WaveGenerator, "_decrfindlast", staticmethod(lambda a, x: 2))
    # n=5 → nfft=8 → df 较大 → wk*dt*n 较小 → log_arg > 1
    P = np.array([1.0, 0.5, 0.16])
    SPT = np.array([0.2, 0.3, 0.4])
    a = WaveGenerator._init_art_wave(
        n=5, dt=0.02, zeta=0.05, P=P, SPT=SPT, nP=3, seed=42
    )
    assert len(a) == 5


# ── 347, 355: _nextpow2, _decrfindfirst, _decrfindlast 边界 ──
def test_nextpow2_and_decrfind_edge():
    assert WaveGenerator._nextpow2(1) == 1
    assert WaveGenerator._nextpow2(3) == 4
    assert WaveGenerator._nextpow2(8) == 8

    # _decrfindfirst: 递减数组中第一个 <= x
    assert WaveGenerator._decrfindfirst(np.array([5, 3, 1]), 0) == 2  # 都 > 0，返回 len-1
    assert WaveGenerator._decrfindfirst(np.array([5, 3, 1]), 6) == 0

    # _decrfindlast: 递减数组中最后一个 >= x
    assert WaveGenerator._decrfindlast(np.array([5, 3, 1]), 10) == 0   # 都 < 10，返回 0
    assert WaveGenerator._decrfindlast(np.array([5, 3, 1]), 0) == 2


# ── 375-377: _decrlininterp_core 外推 ──
def test_decrlininterp_core_extrapolation():
    x = np.array([5.0, 3.0, 1.0])
    y = np.array([10.0, 6.0, 2.0])
    xi = np.array([0.5, 0.1])  # 小于 x 最小值，触发外推
    yi = WaveGenerator._decrlininterp_core(x, y, xi)
    # 外推应使用最后段的 yp 值（因为 xi 始终 < xc，循环结束后 j 仍为 0）
    assert len(yi) == 2
    # 循环结束后 yp=10.0，外推用最后 yp 值填充
    assert np.isclose(yi[0], 10.0, atol=1e-12)
    assert np.isclose(yi[1], 10.0, atol=1e-12)


# ── 418: _rsimple 正常返回 ──
def test_rsimple_returns_cosine_or_full():
    # 正常路径（denom 不接近 0）
    out = WaveGenerator._rsimple(0.5, 1.0, 0.0, 0.1, 0.05)
    assert isinstance(out, (float, np.floating))


# ── 496: _fitspectra early return ──
def test_fitspectra_early_return(monkeypatch):
    """mock 初始谱误差已满足 tol，触发 early return。"""
    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._spamixed",
        lambda a, dt, zeta, P, nP: (np.ones(len(P)), np.ones(len(P), dtype=np.int32))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._error",
        lambda y, y0, n: (0.001, 0.001)  # aerror=0.001 < tol=0.05
    )
    acc = np.ones(32)
    P = np.array([1.0, 0.5])
    SPAT = np.array([0.2, 0.3])
    best, err = WaveGenerator._fitspectra(
        acc, 32, 0.02, 0.05, P, 2, SPAT, tol=0.05, max_iter=2, peak0=0.3,
        progress_callback=None,
    )
    # early return 直接返回 a = acc.copy()
    assert np.allclose(best, acc)
    assert err == 0.001


# ── 545: _fitspectra progress_callback ──
def test_fitspectra_progress_callback(monkeypatch):
    """确保迭代中 progress_callback 被调用。"""
    calls = []
    def cb(it, merr, aerr):
        calls.append((it, merr, aerr))

    # mock 初始误差不满足 tol，需要迭代
    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._spamixed",
        lambda a, dt, zeta, P, nP: (np.ones(len(P)) * 0.5, np.ones(len(P), dtype=np.int32))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._error",
        lambda y, y0, n: (0.2, 0.2)  # 不满足 tol
    )
    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._adjust_peak",
        lambda a, p: a
    )

    acc = np.ones(32)
    P = np.array([1.0, 0.5])
    SPAT = np.array([0.2, 0.3])
    best, err = WaveGenerator._fitspectra(
        acc, 32, 0.02, 0.05, P, 2, SPAT, tol=0.05, max_iter=1, peak0=0.3,
        progress_callback=cb,
    )
    assert len(calls) > 0


# ── 574: _adjustspectra early return ──
def test_adjustspectra_early_return(monkeypatch):
    """mock 初始谱误差已满足 tol，触发 early return。"""
    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._spamixed",
        lambda a, dt, zeta, P, nP: (np.ones(len(P)), np.ones(len(P), dtype=np.int32))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._errora",
        lambda y, y0, n: (0.001, 0.001)
    )
    acc = np.ones(32)
    P = np.array([1.0, 0.5])
    SPAT = np.array([0.2, 0.3])
    best, err = WaveGenerator._adjustspectra(
        acc, 32, 0.02, 0.05, P, 2, SPAT, tol=0.05, max_iter=2,
        progress_callback=None,
    )
    # early return 直接返回 a = acc.copy()
    assert np.allclose(best, acc)
    assert err == 0.001


# ── 765-789: _rafreq ──
def test_rafreq():
    acc = np.random.randn(64)
    ra = WaveGenerator._rafreq(acc, 64, 0.02, 0.05, 1.0)
    assert len(ra) == 64
    assert np.isfinite(ra).all()


# ── 794-800: _ranmk ──
def test_ranmk():
    acc = np.random.randn(64)
    ra = WaveGenerator._ranmk(acc, 64, 0.02, 0.05, 1.0)
    assert len(ra) == 64
    assert np.isfinite(ra).all()


# ── 896-903: _spamixed C 库不可用回退 ──
def test_spamixed_without_c_lib(monkeypatch):
    """mock _c_lib = None，走 Newmark-beta Python 回退路径。"""
    import seiswave.core.generator as gen_mod
    orig = gen_mod._c_lib
    try:
        gen_mod._c_lib = None
        acc = np.random.randn(64)
        spa, spi = WaveGenerator._spamixed(
            acc, 0.02, 0.05,
            np.array([0.1, 0.5, 1.0, 2.0]), 4
        )
        assert len(spa) == 4
        assert len(spi) == 4
        assert np.isfinite(spa).all()
    finally:
        gen_mod._c_lib = orig


# ── 979: fit_error empty mask ──
def test_fit_error_empty_mask():
    out = WaveGenerator.fit_error(np.array([0.0, 0.0]), np.array([0.0, 0.0]))
    assert out == {"max_error": 0.0, "mean_error": 0.0}


# ── 1055: _estimate_pga_from_spectrum empty ──
def test_estimate_pga_empty():
    assert _estimate_pga_from_spectrum(np.array([])) == 0.1


# ── 1161-1162: NFP 无效 fault_type 回退到 reverse ──
def test_nfp_invalid_fault_type(monkeypatch):
    """传入无效 fault_type，应回退到 reverse。"""
    # mock GMPE
    monkeypatch.setattr(
        "seiswave.core.gmpe.GMPEAdapter.compute_spectrum",
        lambda **kw: (np.array([0.5, 1.0]), np.array([0.2, 0.3]))
    )
    # mock WaveGenerator.generate 返回简单信号
    def mock_generate(**kw):
        from seiswave.core.signal import EQSignal as EQSig
        return EQSig(np.ones(kw.get("n", 64)) * 0.1, kw.get("dt", 0.02), name="base")
    monkeypatch.setattr(WaveGenerator, "generate", staticmethod(mock_generate))

    monkeypatch.setattr(
        "seiswave.core.pulse.PulseCalculator.compute_params",
        lambda **kw: SimpleNamespace(Tp=1.0, A=1.0, phi=0.0, t0=1.0)
    )
    monkeypatch.setattr(
        "seiswave.core.pulse.PulseWavelet.generate",
        lambda params, dt, n: (np.ones(n), np.ones(n))
    )
    monkeypatch.setattr(
        "seiswave.core.pulse.BakerPulseDetector.analyze",
        lambda vel, dt: {"has_pulse": True, "confidence": 0.9, "pulse_period": 1.0, "energy_ratio": 0.5}
    )
    monkeypatch.setattr(
        "seiswave.core.spectrum.Spectra.compute",
        lambda *a, **k: SimpleNamespace(sa=np.array([0.2, 0.3]))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.NearFieldPulseGenerator._small_freq_correct",
        staticmethod(lambda acc, dt, target_sa, periods: acc)
    )

    sig = NearFieldPulseGenerator.generate(
        Mw=7.0, R=5.0, fault_type="unknown_fault",
        n=64, dt=0.02, max_iter=2, tol=0.10,
    )
    assert sig is not None


# ── 1225-1248: NFP best_sig is None 回退 ──
def test_nfp_best_sig_none_fallback(monkeypatch):
    """让所有 Baker 候选都不满足 has_pulse & confidence>=0.85，触发回退路径。"""
    # mock GMPE
    monkeypatch.setattr(
        "seiswave.core.gmpe.GMPEAdapter.compute_spectrum",
        lambda **kw: (np.array([0.5, 1.0]), np.array([0.2, 0.3]))
    )
    # mock WaveGenerator.generate 返回简单信号
    def mock_generate(**kw):
        from seiswave.core.signal import EQSignal as EQSig
        return EQSig(np.ones(kw.get("n", 64)) * 0.1, kw.get("dt", 0.02), name="base")
    monkeypatch.setattr(WaveGenerator, "generate", staticmethod(mock_generate))

    monkeypatch.setattr(
        "seiswave.core.pulse.PulseCalculator.compute_params",
        lambda **kw: SimpleNamespace(Tp=1.0, A=1.0, phi=0.0, t0=1.0)
    )
    monkeypatch.setattr(
        "seiswave.core.pulse.PulseWavelet.generate",
        lambda params, dt, n: (np.ones(n), np.ones(n))
    )
    # Baker 始终返回不满足条件的结果
    monkeypatch.setattr(
        "seiswave.core.pulse.BakerPulseDetector.analyze",
        lambda vel, dt: {"has_pulse": False, "confidence": 0.0, "pulse_period": 0.0, "energy_ratio": 0.0}
    )
    monkeypatch.setattr(
        "seiswave.core.spectrum.Spectra.compute",
        lambda *a, **k: SimpleNamespace(sa=np.array([0.2, 0.3]))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.NearFieldPulseGenerator._small_freq_correct",
        staticmethod(lambda acc, dt, target_sa, periods: acc)
    )

    sig = NearFieldPulseGenerator.generate(
        Mw=7.0, R=5.0,
        n=64, dt=0.02, max_iter=2, tol=0.10,
    )
    assert sig is not None
    assert hasattr(sig, "name")


# ── 1311: _small_freq_correct short ctrl ──
def test_small_freq_correct_short_ctrl():
    """传入 periods 长度 < 2，触发 else 分支（ratio_freq = ones）。"""
    acc = np.ones(32) * 0.1
    periods = np.array([0.5])  # 只有一个有效周期
    target_sa = np.array([0.2])
    corrected = NearFieldPulseGenerator._small_freq_correct(
        acc, 0.02, target_sa, periods
    )
    assert len(corrected) == 32


# ── 69-89, 92: generate 类型分发 + 空参数校验 ──
def test_generate_type_dispatch_and_empty(monkeypatch):
    """覆盖 WaveGenerator.generate 的 type 分发路径和空参数校验。"""
    # mock 三个子生成器
    calls = []
    monkeypatch.setattr(
        "seiswave.core.generator.FarFieldGenerator.generate",
        lambda **kw: (calls.append("FF") or SimpleNamespace(acc=np.ones(kw.get("n", 64)), dt=kw.get("dt", 0.02), name="FF"))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.NearFieldNoPulseGenerator.generate",
        lambda **kw: (calls.append("NF") or SimpleNamespace(acc=np.ones(kw.get("n", 64)), dt=kw.get("dt", 0.02), name="NF"))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.NearFieldPulseGenerator.generate",
        lambda **kw: (calls.append("NFP") or SimpleNamespace(acc=np.ones(kw.get("n", 64)), dt=kw.get("dt", 0.02), name="NFP"))
    )

    # FF / NF / NFP（大小写兼容）
    WaveGenerator.generate(type="FF", Mw=7.0, R=50.0)
    assert "FF" in calls
    WaveGenerator.generate(type="nf", Mw=7.0, R=5.0)
    assert "NF" in calls
    WaveGenerator.generate(type="Nfp", Mw=7.0, R=5.0)
    assert "NFP" in calls

    # 无效 type
    with pytest.raises(ValueError, match="无效的地震动类型"):
        WaveGenerator.generate(type="UNKNOWN")

    # 空 target_spectrum / periods
    with pytest.raises(ValueError, match="target_spectrum 不能为空"):
        WaveGenerator.generate()


# ── 133-135: _generate_fortran 控制点降采样 ──
def test_generate_fortran_downsample(monkeypatch):
    """nP_orig > 50 时触发降采样分支。"""
    import seiswave.core.fortran_bridge as fb

    mock_eqs_obj = SimpleNamespace(
        initartwave=lambda n, dt, zeta, P, SPAT: np.ones(n),
        fitspectrum=lambda acc, dt, zeta, P, SPAT, tol, max_iter, fm, flag: np.ones(len(acc)),
    )
    mock_eqs_mod = SimpleNamespace(eqs=mock_eqs_obj)
    monkeypatch.setattr(fb, "_eqs", mock_eqs_mod)
    monkeypatch.setattr(fb, "HAS_FORTRAN", True)
    monkeypatch.setattr(
        fb, "spectrum_mixed",
        lambda acc, dt, zeta, periods: (np.ones(len(periods)), np.ones(len(periods), dtype=np.int32))
    )

    ctrl_periods = np.linspace(0.01, 10.0, 80)
    ctrl_target = np.ones(80)
    result = WaveGenerator._generate_fortran(
        ctrl_periods, ctrl_target, len(ctrl_periods),
        n=64, dt=0.02, zeta=0.05, peak0=0.3,
        tol=0.05, max_iter=2, fm=0, progress_callback=None,
    )
    assert result is not None


# ── 655: _adjustspectra progress_callback ──
def test_adjustspectra_progress_callback(monkeypatch):
    calls = []
    def cb(it, merr, aerr):
        calls.append((it, merr, aerr))

    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._spamixed",
        lambda a, dt, zeta, P, nP: (np.ones(len(P)) * 0.5, np.ones(len(P), dtype=np.int32))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._errora",
        lambda y, y0, n: (0.2, 0.2)
    )
    monkeypatch.setattr(
        "seiswave.core.generator.WaveGenerator._adjust_peak",
        lambda a, p: a
    )

    acc = np.ones(32)
    P = np.array([1.0, 0.5])
    SPAT = np.array([0.2, 0.3])
    best, err = WaveGenerator._adjustspectra(
        acc, 32, 0.02, 0.05, P, 2, SPAT, tol=0.05, max_iter=1,
        progress_callback=cb,
    )
    assert len(calls) > 0


# ── 1001, 1007, 1013: create_ground_motion 分发 ──
def test_create_ground_motion_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "seiswave.core.generator.FarFieldGenerator.generate",
        lambda **kw: (calls.append("FF") or SimpleNamespace(acc=np.ones(64), dt=0.02, name="FF"))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.NearFieldNoPulseGenerator.generate",
        lambda **kw: (calls.append("NF") or SimpleNamespace(acc=np.ones(64), dt=0.02, name="NF"))
    )
    monkeypatch.setattr(
        "seiswave.core.generator.NearFieldPulseGenerator.generate",
        lambda **kw: (calls.append("NFP") or SimpleNamespace(acc=np.ones(64), dt=0.02, name="NFP"))
    )

    create_ground_motion("FF", Mw=7.0, R=50.0)
    assert "FF" in calls
    create_ground_motion("NF", Mw=7.0, R=5.0)
    assert "NF" in calls
    create_ground_motion("NFP", Mw=7.0, R=5.0)
    assert "NFP" in calls

