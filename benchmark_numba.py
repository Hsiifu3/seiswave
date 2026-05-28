#!/usr/bin/env python3
"""
SeisWave Numba 优化深度基准测试
对比当前实现与各优化方向的性能差异
"""

import numpy as np
import time
import gc
from concurrent.futures import ThreadPoolExecutor

# 确保 numba 可用
try:
    from numba import jit, prange
    import numba
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    print("Numba not available, exiting")
    exit(1)

# ========== 基准配置 ==========
n = 8192          # 时程点数
n_periods = 120   # 周期数
dt = 0.01         # 时间步长
zeta = 0.05       # 阻尼比

# 生成测试数据
np.random.seed(42)
acc = np.random.randn(n).astype(np.float64)
# 模拟真实加速度时程：带通滤波
acc = np.convolve(acc, np.ones(10)/10, mode='same')

# 混合周期分布（与 EQSignal 一致）
n_short = n_periods // 2
n_long = n_periods - n_short + 1
periods_short = np.logspace(np.log10(0.04), 0.0, n_short)
periods_long = np.linspace(1.0, 10.0, n_long)
periods = np.concatenate([periods_short, periods_long[1:]])

print(f"Benchmark config: n={n}, n_periods={n_periods}, dt={dt}")
print(f"Period range: {periods[0]:.4f}s ~ {periods[-1]:.4f}s")
print(f"Numba version: {numba.__version__}")
print("=" * 60)


def benchmark(func, *args, repeats=5, warmup=2):
    """精确计时，带 warmup 和 GC"""
    for _ in range(warmup):
        func(*args)
    gc.collect()
    
    times = []
    for _ in range(repeats):
        gc.collect()
        t0 = time.perf_counter()
        result = func(*args)
        t1 = time.perf_counter()
        times.append(t1 - t0)
    
    return min(times), np.mean(times), np.median(times)


# ============================================================
# 1. 当前 Numba kernel（带 ThreadPoolExecutor）
# ============================================================

@jit(nopython=True, cache=True, nogil=True)
def _newmark_beta_kernel_current(acc, dt, period, zeta):
    """当前实现"""
    mpr = 20
    omega = 2.0 * np.pi / period
    k = omega ** 2
    c = 2.0 * zeta * omega
    n = len(acc)

    if dt * mpr > period:
        r = int(np.ceil(mpr * dt / period))
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

    rl0, rl1, rl2, al = 0.0, 0.0, 0.0, 0.0
    rd = np.zeros(n)
    rv = np.zeros(n)
    ra = np.zeros(n)

    for i in range(n):
        ac = acc[i]
        da = (ac - al) / r
        for j in range(1, r + 1):
            ac_sub = al + da * j
            feff = ac_sub + (b1 * rl0 + b2 * rl1 + b3 * rl2) \
                + c * (b4 * rl0 + b5 * rl1 + b6 * rl2)
            rc0 = feff * kinv
            rc1 = b4 * (rc0 - rl0) - b5 * rl1 - b6 * rl2
            rc2 = ac_sub - k * rc0 - c * rc1
            rl0, rl1, rl2 = rc0, rc1, rc2
        rd[i] = rl0
        rv[i] = rl1
        ra[i] = rl2
        al = ac

    return ra, rv, rd


def run_current_parallel():
    """当前 ThreadPoolExecutor 并行实现"""
    tasks = [(acc, dt, T, zeta) for T in periods]
    with ThreadPoolExecutor() as executor:
        results = list(executor.map(lambda a: _newmark_beta_kernel_current(*a), tasks))
    return results


t_min, t_mean, t_med = benchmark(run_current_parallel)
print(f"\n[1] 当前实现 (ThreadPoolExecutor + Numba kernel)")
print(f"    min={t_min*1000:.3f}ms  mean={t_mean*1000:.3f}ms  median={t_med*1000:.3f}ms")
baseline = t_min


# ============================================================
# 2. 预分配 out 数组的 kernel
# ============================================================

@jit(nopython=True, cache=True, nogil=True)
def _newmark_beta_kernel_prealloc(acc, dt, period, zeta, rd, rv, ra):
    """预分配 out 数组版本"""
    mpr = 20
    omega = 2.0 * np.pi / period
    k = omega ** 2
    c = 2.0 * zeta * omega
    n = len(acc)

    if dt * mpr > period:
        r = int(np.ceil(mpr * dt / period))
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

    rl0, rl1, rl2, al = 0.0, 0.0, 0.0, 0.0

    for i in range(n):
        ac = acc[i]
        da = (ac - al) / r
        for j in range(1, r + 1):
            ac_sub = al + da * j
            feff = ac_sub + (b1 * rl0 + b2 * rl1 + b3 * rl2) \
                + c * (b4 * rl0 + b5 * rl1 + b6 * rl2)
            rc0 = feff * kinv
            rc1 = b4 * (rc0 - rl0) - b5 * rl1 - b6 * rl2
            rc2 = ac_sub - k * rc0 - c * rc1
            rl0, rl1, rl2 = rc0, rc1, rc2
        rd[i] = rl0
        rv[i] = rl1
        ra[i] = rl2
        al = ac

    # 返回峰值（模拟 compute 中需要的 max abs）
    sa_max = 0.0
    sv_max = 0.0
    sd_max = 0.0
    omega2 = k
    for i in range(n):
        a_abs = abs(-ra[i] + acc[i])
        if a_abs > sa_max:
            sa_max = a_abs
        if abs(rv[i]) > sv_max:
            sv_max = abs(rv[i])
        if abs(rd[i]) > sd_max:
            sd_max = abs(rd[i])
    se_max = 0.5 * omega2 * sd_max ** 2
    return sa_max, sv_max, sd_max, se_max


def run_prealloc():
    """预分配数组版本"""
    # 预先分配大数组池
    pool_rd = [np.zeros(n) for _ in range(len(periods))]
    pool_rv = [np.zeros(n) for _ in range(len(periods))]
    pool_ra = [np.zeros(n) for _ in range(len(periods))]
    
    results = []
    for i, T in enumerate(periods):
        sa, sv, sd, se = _newmark_beta_kernel_prealloc(
            acc, dt, T, zeta, pool_rd[i], pool_rv[i], pool_ra[i]
        )
        results.append((sa, sv, sd, se))
    return results


t_min, t_mean, t_med = benchmark(run_prealloc)
speedup = baseline / t_min
print(f"\n[2] 预分配 out 数组版本（单线程）")
print(f"    min={t_min*1000:.3f}ms  mean={t_mean*1000:.3f}ms  median={t_med*1000:.3f}ms")
print(f"    vs 当前: {speedup:.2f}x")


# ============================================================
# 3. numba.prange 并行版本
# ============================================================

@jit(nopython=True, cache=True, nogil=True, parallel=True)
def _newmark_beta_kernel_prange(acc, dt, periods_arr, zeta, 
                                 out_sa, out_sv, out_sd, out_se):
    """prange 并行版本——每个周期独立"""
    mpr = 20
    n = len(acc)
    n_p = len(periods_arr)
    
    for p in prange(n_p):
        period = periods_arr[p]
        omega = 2.0 * np.pi / period
        k = omega ** 2
        c = 2.0 * zeta * omega

        if dt * mpr > period:
            r = int(np.ceil(mpr * dt / period))
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

        rl0, rl1, rl2, al = 0.0, 0.0, 0.0, 0.0
        sa_max, sv_max, sd_max = 0.0, 0.0, 0.0

        for i in range(n):
            ac = acc[i]
            da = (ac - al) / r
            for j in range(1, r + 1):
                ac_sub = al + da * j
                feff = ac_sub + (b1 * rl0 + b2 * rl1 + b3 * rl2) \
                    + c * (b4 * rl0 + b5 * rl1 + b6 * rl2)
                rc0 = feff * kinv
                rc1 = b4 * (rc0 - rl0) - b5 * rl1 - b6 * rl2
                rc2 = ac_sub - k * rc0 - c * rc1
                rl0, rl1, rl2 = rc0, rc1, rc2
            
            a_abs = abs(-rl2 + ac)
            if a_abs > sa_max:
                sa_max = a_abs
            if abs(rl1) > sv_max:
                sv_max = abs(rl1)
            if abs(rl0) > sd_max:
                sd_max = abs(rl0)
            al = ac

        out_sa[p] = sa_max
        out_sv[p] = sv_max
        out_sd[p] = sd_max
        out_se[p] = 0.5 * k * sd_max ** 2


def run_prange():
    """prange 并行"""
    out_sa = np.zeros(len(periods))
    out_sv = np.zeros(len(periods))
    out_sd = np.zeros(len(periods))
    out_se = np.zeros(len(periods))
    _newmark_beta_kernel_prange(acc, dt, periods, zeta, out_sa, out_sv, out_sd, out_se)
    return out_sa, out_sv, out_sd, out_se


t_min, t_mean, t_med = benchmark(run_prange)
speedup = baseline / t_min
print(f"\n[3] numba.prange 并行版本（直接出谱值，不存时程）")
print(f"    min={t_min*1000:.3f}ms  mean={t_mean*1000:.3f}ms  median={t_med*1000:.3f}ms")
print(f"    vs 当前: {speedup:.2f}x")


# ============================================================
# 4. r=1 专用 fast path（无子步插值）
# ============================================================

@jit(nopython=True, cache=True, nogil=True)
def _newmark_beta_kernel_r1(acc, dt, period, zeta):
    """r=1 专用版本——无内层循环"""
    omega = 2.0 * np.pi / period
    k = omega ** 2
    c = 2.0 * zeta * omega
    n = len(acc)
    
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

    rl0, rl1, rl2 = 0.0, 0.0, 0.0
    rd = np.zeros(n)
    rv = np.zeros(n)
    ra = np.zeros(n)

    for i in range(n):
        ac = acc[i]
        feff = ac + (b1 * rl0 + b2 * rl1 + b3 * rl2) \
            + c * (b4 * rl0 + b5 * rl1 + b6 * rl2)
        rc0 = feff * kinv
        rc1 = b4 * (rc0 - rl0) - b5 * rl1 - b6 * rl2
        rc2 = ac - k * rc0 - c * rc1
        rl0, rl1, rl2 = rc0, rc1, rc2
        rd[i] = rl0
        rv[i] = rl1
        ra[i] = rl2

    return ra, rv, rd


# 分离 r=1 和 r>1 的周期
r1_periods = [T for T in periods if dt * 20 <= T]
rN_periods = [T for T in periods if dt * 20 > T]
print(f"\n[4] r=1 专用 fast path")
print(f"    r=1 周期数: {len(r1_periods)} (T >= {dt*20:.3f}s)")
print(f"    r>1 周期数: {len(rN_periods)} (T < {dt*20:.3f}s)")


def run_r1_fastpath():
    """r=1 用 fast path，r>1 用当前 kernel"""
    results = []
    # r=1 用 prange 并行
    tasks_r1 = [(acc, dt, T, zeta) for T in r1_periods]
    tasks_rN = [(acc, dt, T, zeta) for T in rN_periods]
    
    with ThreadPoolExecutor() as executor:
        if tasks_r1:
            results_r1 = list(executor.map(lambda a: _newmark_beta_kernel_r1(*a), tasks_r1))
        else:
            results_r1 = []
        if tasks_rN:
            results_rN = list(executor.map(lambda a: _newmark_beta_kernel_current(*a), tasks_rN))
        else:
            results_rN = []
    
    return results_r1 + results_rN


t_min, t_mean, t_med = benchmark(run_r1_fastpath)
speedup = baseline / t_min
print(f"    min={t_min*1000:.3f}ms  mean={t_mean*1000:.3f}ms  median={t_med*1000:.3f}ms")
print(f"    vs 当前: {speedup:.2f}x")


# ============================================================
# 5. r=1 向量化版本（矩阵运算批量处理）
# ============================================================

def run_vectorized_r1():
    """r=1 周期的向量化实现——用 numpy 批量运算"""
    if len(r1_periods) == 0:
        return []
    
    # 准备批量参数
    periods_arr = np.array(r1_periods)
    omega = 2.0 * np.pi / periods_arr
    k = omega ** 2
    c = 2.0 * zeta * omega
    
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
    
    n_p = len(periods_arr)
    # 状态: [位移, 速度, 加速度] 每个周期一列
    rl = np.zeros((3, n_p))
    rd = np.zeros((n, n_p))
    rv = np.zeros((n, n_p))
    ra = np.zeros((n, n_p))
    
    for i in range(n):
        ac = acc[i]
        # feff = ac + (b1*rl0 + b2*rl1 + b3*rl2) + c*(b4*rl0 + b5*rl1 + b6*rl2)
        feff = ac + (b1 + c * b4) * rl[0] + (b2 + c * b5) * rl[1] + (b3 + c * b6) * rl[2]
        rc0 = feff * kinv
        rc1 = b4 * (rc0 - rl[0]) - b5 * rl[1] - b6 * rl[2]
        rc2 = ac - k * rc0 - c * rc1
        rl[0] = rc0
        rl[1] = rc1
        rl[2] = rc2
        rd[i] = rc0
        rv[i] = rc1
        ra[i] = rc2
    
    # 拆分为列表返回
    results = []
    for p in range(n_p):
        results.append((ra[:, p], rv[:, p], rd[:, p]))
    return results


# 向量化版本 + r>1 的 numba kernel
def run_vectorized_mixed():
    results_r1 = run_vectorized_r1()
    tasks_rN = [(acc, dt, T, zeta) for T in rN_periods]
    with ThreadPoolExecutor() as executor:
        if tasks_rN:
            results_rN = list(executor.map(lambda a: _newmark_beta_kernel_current(*a), tasks_rN))
        else:
            results_rN = []
    return results_r1 + results_rN


t_min, t_mean, t_med = benchmark(run_vectorized_mixed)
speedup = baseline / t_min
print(f"\n[5] r=1 向量化 + r>1 Numba kernel")
print(f"    min={t_min*1000:.3f}ms  mean={t_mean*1000:.3f}ms  median={t_med*1000:.3f}ms")
print(f"    vs 当前: {speedup:.2f}x")


# ============================================================
# 6. 纯 Python _newmark_beta（用于对比）
# ============================================================

def _newmark_beta_python(acc, dt, period, zeta):
    """纯 Python 实现"""
    MPR = 20
    omega = 2.0 * np.pi / period
    k = omega ** 2
    c = 2.0 * zeta * omega
    n = len(acc)

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

    rl = np.zeros(3)
    rd = np.zeros(n)
    rv = np.zeros(n)
    ra = np.zeros(n)
    al = 0.0

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
        rd[i] = rl[0]
        rv[i] = rl[1]
        ra[i] = rl[2]
        al = ac

    return ra, rv, rd


def run_python_single():
    results = []
    for T in periods:
        results.append(_newmark_beta_python(acc, dt, T, zeta))
    return results


# 只做1-2次（太慢了）
t0 = time.perf_counter()
run_python_single()
t1 = time.perf_counter()
t_python = t1 - t0
print(f"\n[6] 纯 Python 实现（单线程，仅测1次）")
print(f"    time={t_python*1000:.1f}ms")
print(f"    vs 当前 Numba: {t_python / baseline:.1f}x 慢")


# ============================================================
# 7. 预分配 + prange 组合（终极优化）
# ============================================================

@jit(nopython=True, cache=True, nogil=True, parallel=True)
def _newmark_beta_kernel_ultimate(acc, dt, periods_arr, zeta, 
                                   out_sa, out_sv, out_sd, out_se):
    """终极版本：prange + 不存时程 + 直接出峰值"""
    mpr = 20
    n = len(acc)
    n_p = len(periods_arr)
    
    for p in prange(n_p):
        period = periods_arr[p]
        omega = 2.0 * np.pi / period
        k = omega ** 2
        c = 2.0 * zeta * omega

        if dt * mpr > period:
            r = int(np.ceil(mpr * dt / period))
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

        rl0, rl1, rl2, al = 0.0, 0.0, 0.0, 0.0
        sa_max, sv_max, sd_max = 0.0, 0.0, 0.0

        for i in range(n):
            ac = acc[i]
            da = (ac - al) / r
            for j in range(1, r + 1):
                ac_sub = al + da * j
                feff = ac_sub + (b1 * rl0 + b2 * rl1 + b3 * rl2) \
                    + c * (b4 * rl0 + b5 * rl1 + b6 * rl2)
                rc0 = feff * kinv
                rc1 = b4 * (rc0 - rl0) - b5 * rl1 - b6 * rl2
                rc2 = ac_sub - k * rc0 - c * rc1
                rl0, rl1, rl2 = rc0, rc1, rc2
            
            a_abs = abs(-rl2 + acc[i])
            if a_abs > sa_max:
                sa_max = a_abs
            if abs(rl1) > sv_max:
                sv_max = abs(rl1)
            if abs(rl0) > sd_max:
                sd_max = abs(rl0)
            al = ac

        out_sa[p] = sa_max
        out_sv[p] = sv_max
        out_sd[p] = sd_max
        out_se[p] = 0.5 * k * sd_max ** 2


def run_ultimate():
    out_sa = np.zeros(len(periods))
    out_sv = np.zeros(len(periods))
    out_sd = np.zeros(len(periods))
    out_se = np.zeros(len(periods))
    _newmark_beta_kernel_ultimate(acc, dt, periods, zeta, out_sa, out_sv, out_sd, out_se)
    return out_sa, out_sv, out_sd, out_se


t_min, t_mean, t_med = benchmark(run_ultimate)
speedup = baseline / t_min
print(f"\n[7] 终极优化: prange + 不存时程 + 直接峰值")
print(f"    min={t_min*1000:.3f}ms  mean={t_mean*1000:.3f}ms  median={t_med*1000:.3f}ms")
print(f"    vs 当前: {speedup:.2f}x")


# ============================================================
# 8. 微基准：单 kernel 调用对比
# ============================================================
print(f"\n{'='*60}")
print("[8] 微基准：单周期 kernel 调用")

# 选一个 r=1 的周期
T_r1 = 5.0
# 选一个 r>1 的周期  
T_rN = 0.1

# 单周期 Numba
for _ in range(3):
    _newmark_beta_kernel_current(acc, dt, T_r1, zeta)
gc.collect()
t0 = time.perf_counter()
for _ in range(100):
    _newmark_beta_kernel_current(acc, dt, T_r1, zeta)
t1 = time.perf_counter()
print(f"    Numba r=1 (T={T_r1}s): {(t1-t0)/100*1000:.3f}ms/call")

# 单周期 Python
for _ in range(100):
    _newmark_beta_python(acc, dt, T_r1, zeta)
t0 = time.perf_counter()
for _ in range(10):
    _newmark_beta_python(acc, dt, T_r1, zeta)
t1 = time.perf_counter()
print(f"    Python r=1 (T={T_r1}s): {(t1-t0)/10*1000:.3f}ms/call")

# r>1
for _ in range(3):
    _newmark_beta_kernel_current(acc, dt, T_rN, zeta)
gc.collect()
t0 = time.perf_counter()
for _ in range(100):
    _newmark_beta_kernel_current(acc, dt, T_rN, zeta)
t1 = time.perf_counter()
r_N = int(np.ceil(20 * dt / T_rN))
print(f"    Numba r={r_N} (T={T_rN}s): {(t1-t0)/100*1000:.3f}ms/call")


# ============================================================
# 9. 内存分配开销分析
# ============================================================
print(f"\n{'='*60}")
print("[9] 内存分配开销分析")

# 当前 kernel 每次分配 3*n*8 bytes = 196KB (for n=8192)
mem_per_call = 3 * n * 8 / 1024  # KB
print(f"    每周期内存分配: 3 arrays × {n} × 8 bytes = {mem_per_call:.1f} KB")
print(f"    总分配 ({n_periods} 周期): {mem_per_call * n_periods:.1f} KB = {mem_per_call * n_periods / 1024:.2f} MB")
print(f"    注: Numba 在 nopython mode 下 np.zeros 分配的是原生内存，")
print(f"    不受 Python GC 影响，但仍需要 malloc/free 开销")


# ============================================================
# 10. 结果汇总
# ============================================================
print(f"\n{'='*60}")
print("📊 结果汇总 (基准={baseline*1000:.3f}ms)")
print(f"{'='*60}")
print(f"{'方案':<50} {'时间(ms)':<12} {'提速':<8}")
print("-" * 70)

results_summary = [
    ("[1] 当前 ThreadPoolExecutor + Numba", baseline, 1.0),
    ("[2] 预分配 out 数组（单线程）", t_min if 't_min' in dir() and False else None, None),  # placeholder
]

# 用实际变量重新收集
all_results = {
    "当前 ThreadPoolExecutor+Numba": baseline,
    "预分配 out (单线程)": None,  # will fill
    "numba.prange 并行": None,
    "r=1 fast path + TPE": None,
    "r=1 向量化 + TPE": None,
    "纯 Python (参考)": t_python,
    "终极: prange+不存时程": None,
}

print("\n⚠️  注意：以上部分测试需要重新运行以获取精确值")
print("请查看各节详细输出")
