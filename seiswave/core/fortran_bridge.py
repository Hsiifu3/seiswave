"""
Fortran 加速桥接层

自动检测 _eqsignal 模块可用性，提供 Pythonic 接口封装。
HAS_FORTRAN=False 时所有函数回退到纯 Python 实现。
"""

import numpy as np
import importlib.util
import os
import warnings

# ── 检测 Fortran 模块 ──
HAS_FORTRAN = False
_eqs = None

_so_dir = os.path.dirname(os.path.abspath(__file__))
_so_candidates = [f for f in os.listdir(_so_dir)
                  if f.startswith('_eqsignal') and (f.endswith('.so') or f.endswith('.dylib'))]

if _so_candidates:
    _so_path = os.path.join(_so_dir, _so_candidates[0])
    try:
        spec = importlib.util.spec_from_file_location('_eqsignal', _so_path)
        _mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_mod)
        _eqs = _mod
        HAS_FORTRAN = True
    except Exception as e:
        warnings.warn(f"Fortran module found but failed to load: {e}")


def spectrum_mixed(acc: np.ndarray, dt: float, zeta: float,
                   periods: np.ndarray) -> tuple:
    """混合法反应谱计算（短周期频域 + 长周期 Newmark）

    Parameters
    ----------
    acc : 加速度时程
    dt : 时间步长 (s)
    zeta : 阻尼比
    periods : 周期数组 (s)

    Returns
    -------
    (sa, spi) : 带符号加速度反应谱, 峰值位置索引(1-based)
    """
    acc = np.asarray(acc, dtype=np.float64)
    periods = np.asarray(periods, dtype=np.float64)

    if HAS_FORTRAN:
        spa, spi = _eqs.eqs.spamixed(acc, dt, zeta, periods)
        return spa, spi.astype(np.int32)
    else:
        from .generator import WaveGenerator
        return WaveGenerator._spamixed(acc, dt, zeta, periods, len(periods))


def spectrum_avd(acc: np.ndarray, dt: float, zeta: float,
                 periods: np.ndarray) -> tuple:
    """混合法计算完整反应谱（Sa, Sv, Sd, Se）

    Returns
    -------
    (sa, spi, sv, sd, se)
    """
    acc = np.asarray(acc, dtype=np.float64)
    periods = np.asarray(periods, dtype=np.float64)

    if HAS_FORTRAN:
        spa, spi, spv, spd, spe = _eqs.eqs.spavdmixed(acc, dt, zeta, periods)
        return np.abs(spa), spi.astype(np.int32), np.abs(spv), np.abs(spd), np.abs(spe)
    else:
        from .spectrum import Spectra
        sp = Spectra.compute(acc, dt, periods, zeta, method="mixed")
        spi = np.ones(len(periods), dtype=np.int32)
        return sp.sa, spi, sp.sv, sp.sd, sp.se


def fit_spectra(acc: np.ndarray, dt: float, zeta: float,
                periods: np.ndarray, target: np.ndarray,
                tol: float = 0.05, max_iter: int = 50,
                kpb: int = 1) -> np.ndarray:
    """频域迭代谱匹配（fm=0）

    Parameters
    ----------
    acc : 初始加速度时程
    dt : 时间步长
    zeta : 阻尼比
    periods : 控制周期数组
    target : 目标反应谱值
    tol : 收敛容差
    max_iter : 最大迭代次数
    kpb : 峰值约束 (1=启用)

    Returns
    -------
    调整后的加速度时程
    """
    acc = np.ascontiguousarray(acc, dtype=np.float64)
    periods = np.ascontiguousarray(periods, dtype=np.float64)
    target = np.ascontiguousarray(target, dtype=np.float64)

    if HAS_FORTRAN:
        return _eqs.eqs.fitspectrum(acc, dt, zeta, periods, target,
                                     tol, max_iter, 0, kpb)
    else:
        from .generator import WaveGenerator
        result, _ = WaveGenerator._fitspectra(
            acc, len(acc), dt, zeta, periods, len(periods),
            target, tol, max_iter, float(np.max(np.abs(acc))), None)
        return result


def adjust_spectra(acc: np.ndarray, dt: float, zeta: float,
                   periods: np.ndarray, target: np.ndarray,
                   tol: float = 0.05, max_iter: int = 50,
                   kpb: int = 1) -> np.ndarray:
    """时域小波叠加谱匹配（fm=1，默认）

    Parameters
    ----------
    acc : 初始加速度时程
    dt : 时间步长
    zeta : 阻尼比
    periods : 控制周期数组
    target : 目标反应谱值
    tol : 收敛容差
    max_iter : 最大迭代次数
    kpb : 峰值约束 (1=启用)

    Returns
    -------
    调整后的加速度时程
    """
    acc = np.ascontiguousarray(acc, dtype=np.float64)
    periods = np.ascontiguousarray(periods, dtype=np.float64)
    target = np.ascontiguousarray(target, dtype=np.float64)

    if HAS_FORTRAN:
        return _eqs.eqs.adjustspectra(acc, dt, zeta, periods, target,
                                       tol, max_iter, kpb)
    else:
        from .generator import WaveGenerator
        result, _ = WaveGenerator._adjustspectra(
            acc, len(acc), dt, zeta, periods, len(periods),
            target, tol, max_iter, None)
        return result


def init_art_wave(n: int, dt: float, zeta: float,
                  periods: np.ndarray, target: np.ndarray) -> np.ndarray:
    """从目标反应谱生成初始人工波

    Parameters
    ----------
    n : 信号长度
    dt : 时间步长
    zeta : 阻尼比
    periods : 周期数组
    target : 目标反应谱值

    Returns
    -------
    初始加速度时程
    """
    periods = np.ascontiguousarray(periods, dtype=np.float64)
    target = np.ascontiguousarray(target, dtype=np.float64)

    if HAS_FORTRAN:
        return _eqs.eqs.initartwave(n, dt, zeta, periods, target)
    else:
        from .generator import WaveGenerator
        return WaveGenerator._init_art_wave(n, dt, zeta, periods, target,
                                             len(periods))


def newmark_response(acc: np.ndarray, dt: float, zeta: float,
                     period: float) -> tuple:
    """Newmark-β 法计算 SDOF 完整响应

    Returns
    -------
    (ra, rv, rd) : 加速度、速度、位移响应时程
    """
    acc = np.ascontiguousarray(acc, dtype=np.float64)

    if HAS_FORTRAN:
        ra, rv, rd = _eqs.eqs.rnmk(acc, dt, zeta, period)
        return ra, rv, rd
    else:
        from .spectrum import Spectra
        return Spectra._newmark_beta(acc, dt, period, zeta)


def acc2vd(acc: np.ndarray, dt: float, v0: float = 0.0,
           d0: float = 0.0) -> tuple:
    """加速度积分为速度和位移

    Returns
    -------
    (v, d) : 速度、位移时程
    """
    acc = np.ascontiguousarray(acc, dtype=np.float64)

    if HAS_FORTRAN:
        v, d = _eqs.basic.acc2vd(acc, dt, v0, d0)
        return v, d
    else:
        n = len(acc)
        v = np.zeros(n)
        d = np.zeros(n)
        v[0] = v0
        d[0] = d0
        for i in range(1, n):
            v[i] = v[i-1] + 0.5 * (acc[i] + acc[i-1]) * dt
            d[i] = d[i-1] + 0.5 * (v[i] + v[i-1]) * dt
        return v, d
