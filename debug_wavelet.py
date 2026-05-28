"""
调试脚本：检查 Atik 小波在 adjustspectra 中的行为
"""

import numpy as np
from numpy.fft import rfft, irfft

# 简化工具函数
def nextpow2(n):
    p = 1
    while p < n:
        p *= 2
    return p

def spamixed(acc, dt, zeta, periods, nP):
    n = len(acc)
    threshold = 20.0 * dt
    spa = np.zeros(nP, dtype=np.float64)
    spi = np.ones(nP, dtype=np.int32)
    m = 0
    while m < nP and periods[m] < threshold:
        m += 1
    if m < nP:
        m += 1
    if m > 0:
        nfft = nextpow2(n)
        a0 = np.zeros(nfft)
        a0[:n] = acc
        af = rfft(a0)
        fs = 1.0 / dt
        df = fs / nfft
        nf = nfft // 2 + 1
        wj = np.zeros(nf)
        wj[1:] = 2.0 * np.pi * np.arange(1, nf) * df
        wj2 = wj * wj
        for i in range(m):
            w0 = 2.0 * np.pi / periods[i]
            w0i2 = w0 * w0
            w0iwj = w0 * wj
            denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
            safe = np.abs(denom) > 1e-30
            raf = np.zeros(nf, dtype=complex)
            raf[safe] = af[safe] * (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]
            ra = irfft(raf, nfft)[:n]
            idx = np.argmax(np.abs(ra))
            spa[i] = ra[idx]
            spi[i] = idx + 1
    for i in range(m, nP):
        omega = 2.0 * np.pi / periods[i]
        k = omega ** 2
        c = 2.0 * zeta * omega
        MPR = 20
        if dt * MPR > periods[i]:
            r = int(np.ceil(MPR * dt / periods[i]))
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
        rl = np.zeros(3)
        al = 0.0
        ra_n = np.zeros(n)
        for j in range(n):
            ac = acc[j]
            da = (ac - al) / r
            for jj in range(1, r + 1):
                ac_sub = al + da * jj
                feff = ac_sub + (b1 * rl[0] + b2 * rl[1] + b3 * rl[2]) + c * (b4 * rl[0] + b5 * rl[1] + b6 * rl[2])
                rc0 = feff * kinv
                rc1 = b4 * (rc0 - rl[0]) - b5 * rl[1] - b6 * rl[2]
                rc2 = ac_sub - k * rc0 - c * rc1
                rl[0] = rc0
                rl[1] = rc1
                rl[2] = rc2
            ra_n[j] = -rl[2] + ac
            al = ac
        idx = np.argmax(np.abs(ra_n))
        spa[i] = ra_n[idx]
        spi[i] = idx + 1
    return spa, spi

# 小波函数
def wfunc_old(n, dt, itm, P, zeta):
    TWO_PI = 2.0 * np.pi
    tm = (itm - 1) * dt
    w = TWO_PI / P
    f = 1.0 / P
    tmp1 = np.sqrt(1.0 - zeta**2)
    gamma = 1.178 * (f * tmp1)**(-0.93)
    deltaT = np.arctan(tmp1 / zeta) / (w * tmp1) if abs(w * tmp1) > 1e-30 else 0.0
    t = np.arange(n) * dt
    tmp2 = t - tm + deltaT
    return np.cos(w * tmp1 * tmp2) * np.exp(-(tmp2 / gamma)**2)

def cosine_taper(tau, width):
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
    t = np.arange(n) * dt
    if order == 1:
        return w - np.mean(w)
    elif order == 2:
        v_raw = np.cumsum(w) * dt
        d_raw = np.cumsum(v_raw) * dt
        ones = np.ones(n)
        v_1 = np.cumsum(ones) * dt
        d_1 = np.cumsum(v_1) * dt
        v_t = np.cumsum(t) * dt
        d_t = np.cumsum(v_t) * dt
        A = np.array([[v_1[-1], v_t[-1]], [d_1[-1], d_t[-1]]])
        b = np.array([v_raw[-1], d_raw[-1]])
        try:
            coeffs = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            coeffs = np.array([np.mean(w), 0.0])
        return w - coeffs[0] - coeffs[1] * t
    else:
        raise ValueError(f"不支持的修正阶数: {order}")

def wfunc_new(n, dt, itm, T, zeta, taper_cycles=3.0):
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
    phi_offset = np.arctan2(zeta, np.sqrt(max(1.0 - zeta**2, 0.0)))
    w_base = np.cos(omega_d * tau + phi_offset) * np.exp(-alpha * np.abs(tau))
    taper_width = taper_cycles * T
    taper = cosine_taper(tau, taper_width)
    w_tapered = w_base * taper
    w_corrected = baseline_correction(w_tapered, dt, n, order=2)
    peak = np.max(np.abs(w_corrected))
    if peak > 1e-30:
        w_corrected /= peak
    return w_corrected

# 测试：检查单个小波的响应特性
n, dt, zeta = 2000, 0.02, 0.05
T = 0.2
itm = n // 2

w_old = wfunc_old(n, dt, itm, T, zeta)
w_new = wfunc_new(n, dt, itm, T, zeta)

periods = np.array([T])
spa_old, spi_old = spamixed(w_old, dt, zeta, periods, 1)
spa_new, spi_new = spamixed(w_new, dt, zeta, periods, 1)

print(f"周期 T={T}s 的单小波响应:")
print(f"  旧小波 SPA={spa_old[0]:.6f}, 峰值时刻={spi_old[0]}")
print(f"  新小波 SPA={spa_new[0]:.6f}, 峰值时刻={spi_new[0]}")
print(f"  比值: 新/旧 = {spa_new[0]/spa_old[0]:.4f}")
print()

# 检查能量
print(f"  旧小波: max={np.max(np.abs(w_old)):.6f}, sum={np.sum(w_old):.6f}, energy={np.sum(w_old**2):.6f}")
print(f"  新小波: max={np.max(np.abs(w_new)):.6f}, sum={np.sum(w_new):.6f}, energy={np.sum(w_new**2):.6f}")
print()

# 检查多种周期
print("多种周期响应对比:")
test_periods = [0.1, 0.2, 0.5, 1.0]
for T in test_periods:
    w_old = wfunc_old(n, dt, itm, T, zeta)
    w_new = wfunc_new(n, dt, itm, T, zeta)
    periods = np.array([T])
    spa_old, _ = spamixed(w_old, dt, zeta, periods, 1)
    spa_new, _ = spamixed(w_new, dt, zeta, periods, 1)
    ratio = spa_new[0] / spa_old[0] if abs(spa_old[0]) > 1e-30 else 0
    print(f"  T={T:.2f}s: 旧SPA={spa_old[0]:.6f}, 新SPA={spa_new[0]:.6f}, 比值={ratio:.4f}")

# 关键测试：检查新小波的 M 矩阵对角元素
print()
print("M矩阵对角元素对比（T=0.2s）:")
P = np.array([0.2])
nP = 1
nfft_freq = nextpow2(n) * 2
nf = nfft_freq // 2 + 1
fs = 1.0 / dt
df_freq = fs / nfft_freq
wj = np.zeros(nf)
wj[1:] = 2.0 * np.pi * np.arange(1, nf) * df_freq
wj2 = wj * wj
w0_arr = 2.0 * np.pi / P

for wavelet_name, wfunc in [('旧', wfunc_old), ('新', wfunc_new)]:
    w = wfunc(n, dt, itm, 0.2, zeta)
    W_padded = np.zeros(nfft_freq)
    W_padded[:n] = w
    Wf = rfft(W_padded)
    
    w0 = w0_arr[0]
    w0i2 = w0 * w0
    w0iwj = w0 * wj
    denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
    safe = np.abs(denom) > 1e-30
    H = np.ones(nf, dtype=complex)
    H[safe] = (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]
    raf = Wf * H
    ra = irfft(raf, nfft_freq)[:n]
    
    # 峰值时刻
    spa, spi = spamixed(w, dt, zeta, P, 1)
    si = spi[0] - 1
    M_ii = ra[si]
    print(f"  {wavelet_name}小波: M_ii={M_ii:.6f}, SPA={spa[0]:.6f}, 峰值时刻={spi[0]}")
