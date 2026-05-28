"""
独立小波验证脚本（避免 signal.py 命名冲突）
"""

import numpy as np
from numpy.fft import rfft, irfft
import sys
import os

# 避免 Python 标准库 signal 冲突
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'seiswave/core'))

# 手动导入必要模块（跳过 signal.py）
import importlib.util
import os as _os

_CORE_DIR = _os.path.join(_os.path.dirname(__file__), 'seiswave', 'core')

# 导入 code_spec
spec = importlib.util.spec_from_file_location('code_spec', _os.path.join(_CORE_DIR, 'code_spec.py'))
code_spec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(code_spec)
CodeSpectrum = code_spec.CodeSpectrum

# 定义简化版的 Newmark-beta（避免导入 spectrum.py 中的 numba 依赖）
def newmark_simple(acc, dt, period, zeta):
    """简化 Newmark-beta（平均加速度法）。"""
    omega = 2.0 * np.pi / period
    k = omega ** 2
    c = 2.0 * zeta * omega
    n = len(acc)

    MPR = 20
    if dt * MPR > period:
        r = int(np.ceil(MPR * dt / period))
        sub_dt = dt / r
    else:
        r = 1
        sub_dt = dt

    beta = 0.25
    gamma = 0.5
    b1 = 1.0 / (beta * sub_dt ** 2)
    b2 = 1.0 / (beta * sub_dt)
    b3 = 1.0 / (2.0 * beta) - 1.0
    b4 = gamma / (beta * sub_dt)
    b5 = gamma / beta - 1.0
    b6 = 0.5 * sub_dt * (gamma / beta - 2.0)

    keff = k + b1 + b4 * c
    kinv = 1.0 / keff

    rl = np.zeros(3)  # [u, v, a_rel]
    al = 0.0
    ra = np.zeros(n)

    for i in range(n):
        ac = acc[i]
        da = (ac - al) / r
        for j in range(1, r + 1):
            ac_sub = al + da * j
            feff = ac_sub + (b1 * rl[0] + b2 * rl[1] + b3 * rl[2]) \
                   + c * (b4 * rl[0] + b5 * rl[1] + b6 * rl[2])
            rc0 = feff * kinv
            rc1 = b4 * (rc0 - rl[0]) - b5 * rl[1] - b6 * rl[2]
            rc2 = ac_sub - k * rc0 - c * rc1
            rl[0] = rc0
            rl[1] = rc1
            rl[2] = rc2
        ra[i] = rl[2]
        al = ac

    abs_acc = -ra + acc
    return abs_acc


def compute_spectrum(acc, dt, periods, zeta=0.05):
    """计算反应谱。"""
    sa = np.zeros(len(periods))
    for i, T in enumerate(periods):
        ra = newmark_simple(acc, dt, T, zeta)
        sa[i] = np.max(np.abs(ra))
    return sa


# ═══════════════════════════════════════════════════════════
# 旧小波基（Gaussian-modulated cosine）
# ═══════════════════════════════════════════════════════════

def wfunc_old(n, dt, itm, P, zeta):
    """传统 Gaussian-modulated cosine 小波（复现 EQSignal wfunc）。"""
    TWO_PI = 2.0 * np.pi
    tm = (itm - 1) * dt
    w = TWO_PI / P
    f = 1.0 / P

    tmp1 = np.sqrt(1.0 - zeta**2)
    gamma = 1.178 * (f * tmp1)**(-0.93)
    deltaT = np.arctan(tmp1 / zeta) / (w * tmp1) if abs(w * tmp1) > 1e-30 else 0.0

    t = np.arange(n) * dt
    tmp2 = t - tm + deltaT

    wf = np.cos(w * tmp1 * tmp2) * np.exp(-(tmp2 / gamma)**2)
    return wf


# ═══════════════════════════════════════════════════════════
# 新小波基（Atik & Abrahamson 2010）
# ═══════════════════════════════════════════════════════════

def cosine_taper(tau, width):
    """Cosine taper 窗函数。"""
    taper = np.ones_like(tau, dtype=np.float64)
    w2 = 2.0 * width
    mask_rise = (np.abs(tau) > width) & (np.abs(tau) <= w2)
    mask_zero = np.abs(tau) > w2

    if np.any(mask_rise):
        x = (np.abs(tau[mask_rise]) - width) / width
        taper[mask_rise] = 0.5 * (1.0 + np.cos(np.pi * x))
    taper[mask_zero] = 0.0
    return taper


def baseline_correction(w, dt, n, order=2):
    """多项式基线修正。"""
    t = np.arange(n) * dt

    if order == 1:
        c0 = np.mean(w)
        return w - c0
    elif order == 2:
        v_raw = np.cumsum(w) * dt
        d_raw = np.cumsum(v_raw) * dt

        ones = np.ones(n)
        v_1 = np.cumsum(ones) * dt
        d_1 = np.cumsum(v_1) * dt
        v_t = np.cumsum(t) * dt
        d_t = np.cumsum(v_t) * dt

        A = np.array([
            [v_1[-1], v_t[-1]],
            [d_1[-1], d_t[-1]]
        ])
        b = np.array([v_raw[-1], d_raw[-1]])

        try:
            coeffs = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            coeffs = np.array([np.mean(w), 0.0])

        c0, c1 = coeffs
        return w - c0 - c1 * t
    else:
        raise ValueError(f"不支持的修正阶数: {order}")


def wfunc_new(n, dt, itm, T, zeta, taper_cycles=3.0):
    """
    Atik & Abrahamson (2010) 解析锥形余弦小波。
    """
    TWO_PI = 2.0 * np.pi
    tp = (itm - 1) * dt
    omega = TWO_PI / T
    omega_d = omega * np.sqrt(1.0 - zeta**2)

    if abs(zeta) < 0.999 and abs(1.0 - zeta**2) > 1e-30:
        alpha = zeta * omega / np.sqrt(1.0 - zeta**2)
    else:
        alpha = zeta * omega

    t = np.arange(n) * dt
    tau = t - tp

    # 基线修正相位
    phi_offset = np.arctan2(zeta, np.sqrt(max(1.0 - zeta**2, 0.0)))

    # 基础指数衰减余弦
    w_base = np.cos(omega_d * tau + phi_offset) * np.exp(-alpha * np.abs(tau))

    # 锥形处理
    taper_width = taper_cycles * T
    taper = cosine_taper(tau, taper_width)
    w_tapered = w_base * taper

    # 基线修正
    w_corrected = baseline_correction(w_tapered, dt, n, order=2)

    # 归一化
    peak = np.max(np.abs(w_corrected))
    if peak > 1e-30:
        w_corrected /= peak

    return w_corrected


# ═══════════════════════════════════════════════════════════
# 验证函数
# ═══════════════════════════════════════════════════════════

def check_drift(w, dt):
    """检查速度/位移末端是否归零。"""
    v = np.cumsum(w) * dt
    d = np.cumsum(v) * dt
    return {
        'v_end': float(v[-1]),
        'd_end': float(d[-1]),
        'v_max': float(np.max(np.abs(v))),
        'd_max': float(np.max(np.abs(d))),
        'v_end_ratio': float(abs(v[-1]) / (np.max(np.abs(v)) + 1e-30)),
        'd_end_ratio': float(abs(d[-1]) / (np.max(np.abs(d)) + 1e-30)),
    }


def spectral_concentration(freq, amp, f_target, bandwidth=0.2):
    """计算目标频率附近能量占比。"""
    total_energy = np.sum(amp**2)
    mask = np.abs(freq - f_target) < bandwidth * f_target
    band_energy = np.sum(amp[mask]**2)
    return float(band_energy / (total_energy + 1e-30))


def compare_wavelets(n, dt, itm, T, zeta):
    """对比两种小波。"""
    w_old = wfunc_old(n, dt, itm, T, zeta)
    w_new = wfunc_new(n, dt, itm, T, zeta)

    nfft = (1 << int(np.ceil(np.log2(n)))) * 4
    f_old = rfft(w_old, n=nfft)
    f_new = rfft(w_new, n=nfft)
    freq = np.fft.rfftfreq(nfft, dt)

    drift_old = check_drift(w_old, dt)
    drift_new = check_drift(w_new, dt)

    f_target = 1.0 / T
    conc_old = spectral_concentration(freq, np.abs(f_old), f_target)
    conc_new = spectral_concentration(freq, np.abs(f_new), f_target)

    return {
        'T': T,
        'drift_old': drift_old,
        'drift_new': drift_new,
        'spectral_concentration_old': conc_old,
        'spectral_concentration_new': conc_new,
    }


# ═══════════════════════════════════════════════════════════
# 主测试
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("SeisWave 小波基对比验证 (独立脚本)")
    print("=" * 60)

    n, dt, zeta = 2000, 0.02, 0.05
    test_periods = [0.1, 0.2, 0.5, 1.0, 2.0, 3.0]

    print(f"\n信号参数: n={n}, dt={dt}, zeta={zeta}")
    print(f"测试周期: {test_periods}")
    print()

    all_pass = True
    for T in test_periods:
        itm = n // 2
        r = compare_wavelets(n, dt, itm, T, zeta)

        print(f"T={T:.2f}s:")
        print(f"  旧小波 - 速度末端漂移: {r['drift_old']['v_end']:.6f} "
              f"(ratio={r['drift_old']['v_end_ratio']:.6f})")
        print(f"  旧小波 - 位移末端漂移: {r['drift_old']['d_end']:.6f} "
              f"(ratio={r['drift_old']['d_end_ratio']:.6f})")
        print(f"  新小波 - 速度末端漂移: {r['drift_new']['v_end']:.6f} "
              f"(ratio={r['drift_new']['v_end_ratio']:.6f})")
        print(f"  新小波 - 位移末端漂移: {r['drift_new']['d_end']:.6f} "
              f"(ratio={r['drift_new']['d_end_ratio']:.6f})")
        print(f"  频域集中度: 旧={r['spectral_concentration_old']:.4f}, "
              f"新={r['spectral_concentration_new']:.4f}")

        # 检查新小波基线漂移是否显著改善
        if r['drift_new']['v_end_ratio'] > 0.01 or r['drift_new']['d_end_ratio'] > 0.01:
            print(f"  ⚠️ 警告: T={T}s 新小波基线漂移过大")
            all_pass = False
        else:
            print(f"  ✅ T={T}s 基线漂移通过")
        print()

    print("=" * 60)
    if all_pass:
        print("Phase 1 验证: ✅ 全部通过")
    else:
        print("Phase 1 验证: ⚠️ 部分未通过，需调整参数")
    print("=" * 60)
