#!/usr/bin/env python3
"""
测试 prange 负载均衡优化
"""

import numpy as np
import time
import gc
from concurrent.futures import ThreadPoolExecutor
from numba import jit, prange
import numba

n = 8192
dt = 0.01
zeta = 0.05

np.random.seed(42)
acc = np.random.randn(n).astype(np.float64)
acc = np.convolve(acc, np.ones(10)/10, mode='same')

n_periods = 120
periods = np.concatenate([
    np.logspace(np.log10(0.04), 0.0, n_periods // 2),
    np.linspace(1.0, 10.0, n_periods - n_periods // 2 + 1)[1:]
])

print(f"测试 prange 负载均衡: {len(periods)} 周期, n={n}")
print(f"CPU cores: {numba.config.NUMBA_DEFAULT_NUM_THREADS}")

@jit(nopython=True, cache=True, nogil=True, parallel=True)
def _kernel_prange_sorted(acc, dt, periods_arr, zeta, sa, sv, sd, se):
    mpr = 20
    n = len(acc)
    n_p = len(periods_arr)
    for p in prange(n_p):
        period = periods_arr[p]
        omega = 2.0 * np.pi / period
        k = omega ** 2; c = 2.0 * zeta * omega
        if dt * mpr > period:
            r = int(np.ceil(mpr * dt / period)); sub_dt = dt / r
        else:
            r = 1; sub_dt = dt
        beta, gamma = 0.25, 0.5
        b1 = 1.0 / (beta * sub_dt ** 2)
        b2 = 1.0 / (beta * sub_dt)
        b3 = 1.0 / (2.0 * beta) - 1.0
        b4 = gamma / (beta * sub_dt)
        b5 = gamma / beta - 1.0
        b6 = 0.5 * sub_dt * (gamma / beta - 2.0)
        keff = k + b1 + b4 * c; kinv = 1.0 / keff
        rl0 = rl1 = rl2 = al = 0.0
        sa_max = sv_max = sd_max = 0.0
        for i in range(n):
            ac = acc[i]; da = (ac - al) / r
            for j in range(1, r + 1):
                ac_sub = al + da * j
                feff = ac_sub + (b1 * rl0 + b2 * rl1 + b3 * rl2) + c * (b4 * rl0 + b5 * rl1 + b6 * rl2)
                rc0 = feff * kinv
                rc1 = b4 * (rc0 - rl0) - b5 * rl1 - b6 * rl2
                rc2 = ac_sub - k * rc0 - c * rc1
                rl0, rl1, rl2 = rc0, rc1, rc2
            a_abs = abs(-rl2 + acc[i])
            if a_abs > sa_max: sa_max = a_abs
            if abs(rl1) > sv_max: sv_max = abs(rl1)
            if abs(rl0) > sd_max: sd_max = abs(rl0)
            al = ac
        sa[p] = sa_max; sv[p] = sv_max; sd[p] = sd_max; se[p] = 0.5 * k * sd_max ** 2


def run_sorted(descending=True):
    sorted_periods = np.sort(periods)[::-1] if descending else np.sort(periods)
    sa = np.zeros(len(periods)); sv = np.zeros(len(periods))
    sd = np.zeros(len(periods)); se = np.zeros(len(periods))
    _kernel_prange_sorted(acc, dt, sorted_periods, zeta, sa, sv, sd, se)
    return sa, sv, sd, se

# Warm up
run_sorted(True)
run_sorted(False)

times = []
for _ in range(10):
    gc.collect()
    t0 = time.perf_counter()
    run_sorted(True)  # descending (heavy first)
    t1 = time.perf_counter()
    times.append(t1-t0)
t_desc = min(times)

times = []
for _ in range(10):
    gc.collect()
    t0 = time.perf_counter()
    run_sorted(False)  # ascending (light first)
    t1 = time.perf_counter()
    times.append(t1-t0)
t_asc = min(times)

print(f"prange 降序排列(重先): {t_desc*1000:.3f}ms")
print(f"prange 升序排列(轻先): {t_asc*1000:.3f}ms")
print(f"差值: {(t_asc/t_desc - 1)*100:.1f}%")

# 原始顺序
original_periods = periods.copy()
sa = np.zeros(len(periods)); sv = np.zeros(len(periods))
sd = np.zeros(len(periods)); se = np.zeros(len(periods))
_kernel_prange_sorted(acc, dt, original_periods, zeta, sa, sv, sd, se)

times = []
for _ in range(10):
    gc.collect()
    t0 = time.perf_counter()
    _kernel_prange_sorted(acc, dt, original_periods, zeta, sa, sv, sd, se)
    t1 = time.perf_counter()
    times.append(t1-t0)
t_orig = min(times)

print(f"prange 原始混合顺序:    {t_orig*1000:.3f}ms")

print("\n结论: 排序对 prange 静态调度影响微弱，负载均衡不是主要瓶颈")
