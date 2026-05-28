"""
调试脚本3：深入分析新小波响应符号问题
"""

import numpy as np
from numpy.fft import rfft, irfft

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

n, dt, zeta = 2000, 0.02, 0.05
itm = n // 2
T = 0.2

# 1. 分析旧小波的时间偏移
w_old = wfunc_old(n, dt, itm, T, zeta)
t = np.arange(n) * dt
tm = (itm - 1) * dt
w = 2.0 * np.pi / T
tmp1 = np.sqrt(1.0 - zeta**2)
deltaT = np.arctan(tmp1 / zeta) / (w * tmp1)
print(f"旧小波: tm={tm:.4f}s, deltaT={deltaT:.4f}s")
print(f"  小波峰值时刻: {tm - deltaT:.4f}s")
print(f"  小波在 tm 的值: {w_old[itm-1]:.6f}")
print(f"  小波峰值: {np.max(w_old):.6f} at t={t[np.argmax(w_old)]:.4f}s")
print()

# 2. 测试简单的指数衰减余弦（无基线修正，无taper）
def w_simple(n, dt, itm, T, zeta):
    TWO_PI = 2.0 * np.pi
    tp = (itm - 1) * dt
    omega = TWO_PI / T
    omega_d = omega * np.sqrt(1.0 - zeta**2)
    alpha = zeta * omega / np.sqrt(1.0 - zeta**2) if abs(zeta) < 0.999 else zeta * omega
    t = np.arange(n) * dt
    tau = t - tp
    return np.cos(omega_d * tau) * np.exp(-alpha * np.abs(tau))

w_s = w_simple(n, dt, itm, T, zeta)
periods = np.array([T])
spa_s, spi_s = spamixed(w_s, dt, zeta, periods, 1)
print(f"简单指数余弦 (无修正): SPA={spa_s[0]:.6f}, 峰值时刻={spi_s[0]}")
print(f"  峰值: {np.max(w_s):.6f} at t={t[np.argmax(w_s)]:.4f}s")
print(f"  在 tm={tm:.4f}s 的值: {w_s[itm-1]:.6f}")
print()

# 3. 对比：把旧小波的峰值时刻偏移去掉会怎样？
# 即 deltaT=0 的旧小波
w_old_no_shift = np.cos(w * tmp1 * (t - tm)) * np.exp(-((t - tm) / (1.178 * (1/T * tmp1)**(-0.93)))**2)
spa_old_ns, spi_old_ns = spamixed(w_old_no_shift, dt, zeta, periods, 1)
print(f"旧小波(deltaT=0): SPA={spa_old_ns[0]:.6f}, 峰值时刻={spi_old_ns[0]}")
print(f"  峰值: {np.max(w_old_no_shift):.6f} at t={t[np.argmax(w_old_no_shift)]:.4f}s")
print()

# 4. 分析频域响应的符号
# 对短周期 T=0.2s (< 0.4s threshold)，用频域法
nfft = nextpow2(n)
a0 = np.zeros(nfft)
a0[:n] = w_old
af = rfft(a0)
fs = 1.0 / dt
df = fs / nfft
nf = nfft // 2 + 1
wj = np.zeros(nf)
wj[1:] = 2.0 * np.pi * np.arange(1, nf) * df
wj2 = wj * wj
w0 = 2.0 * np.pi / T
w0i2 = w0 * w0
w0iwj = w0 * wj
denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
safe = np.abs(denom) > 1e-30
raf = np.zeros(nf, dtype=complex)
raf[safe] = af[safe] * (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]
ra_old = irfft(raf, nfft)[:n]

a0 = np.zeros(nfft)
a0[:n] = w_s
af = rfft(a0)
raf = np.zeros(nf, dtype=complex)
raf[safe] = af[safe] * (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]
ra_simple = irfft(raf, nfft)[:n]

idx_old = np.argmax(np.abs(ra_old))
idx_simple = np.argmax(np.abs(ra_simple))
print(f"频域响应峰值:")
print(f"  旧小波: idx={idx_old}, ra={ra_old[idx_old]:.6f}, sign={np.sign(ra_old[idx_old]):.0f}")
print(f"  简单余弦: idx={idx_simple}, ra={ra_simple[idx_simple]:.6f}, sign={np.sign(ra_simple[idx_simple]):.0f}")
print()

# 5. 关键发现：小波峰值时刻 vs 响应峰值时刻
print("小波峰值 vs 响应峰值时刻:")
print(f"  旧小波: 小波峰值={t[np.argmax(w_old)]:.4f}s, 响应峰值={idx_old*dt:.4f}s")
print(f"  简单余弦: 小波峰值={t[np.argmax(w_s)]:.4f}s, 响应峰值={idx_simple*dt:.4f}s")
print()

# 6. 测试：如果让新小波也有类似的 deltaT 偏移
def w_new_with_shift(n, dt, itm, T, zeta):
    TWO_PI = 2.0 * np.pi
    tm = (itm - 1) * dt
    omega = TWO_PI / T
    omega_d = omega * np.sqrt(1.0 - zeta**2)
    alpha = zeta * omega / np.sqrt(1.0 - zeta**2) if abs(zeta) < 0.999 else zeta * omega
    # 使用与旧小波相同的 deltaT
    deltaT = np.arctan(np.sqrt(1-zeta**2) / zeta) / (omega * np.sqrt(1-zeta**2))
    t = np.arange(n) * dt
    tau = t - tm + deltaT
    return np.cos(omega_d * tau) * np.exp(-alpha * np.abs(tau))

w_ns = w_new_with_shift(n, dt, itm, T, zeta)
spa_ns, spi_ns = spamixed(w_ns, dt, zeta, periods, 1)
print(f"新小波(带deltaT偏移): SPA={spa_ns[0]:.6f}, 峰值时刻={spi_ns[0]}")
print(f"  小波峰值: {np.max(w_ns):.6f} at t={t[np.argmax(w_ns)]:.4f}s")
print(f"  在 tm={tm:.4f}s 的值: {w_ns[itm-1]:.6f}")
print()

# 7. 对比旧小波和新小波(带偏移)的符号
print("符号对比:")
a0 = np.zeros(nfft)
a0[:n] = w_ns
af = rfft(a0)
raf = np.zeros(nf, dtype=complex)
raf[safe] = af[safe] * (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]
ra_ns = irfft(raf, nfft)[:n]
idx_ns = np.argmax(np.abs(ra_ns))
print(f"  新小波(带偏移): ra={ra_ns[idx_ns]:.6f}, sign={np.sign(ra_ns[idx_ns]):.0f}")
print(f"  旧小波: ra={ra_old[idx_old]:.6f}, sign={np.sign(ra_old[idx_old]):.0f}")
