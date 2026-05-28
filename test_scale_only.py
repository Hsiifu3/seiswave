"""
快速验证：不做 adjustspectra 迭代，仅缩放，看谱误差是否保持
"""

import numpy as np
from numpy.fft import rfft, irfft
import time

# 复用 test_lm_prototype.py 的函数（简化版本）
def nextpow2(n):
    p = 1
    while p < n:
        p *= 2
    return p

def decrlininterp_core(x, y, xi):
    n = len(x)
    ni = len(xi)
    yi = np.zeros(ni)
    xp = x[n - 1]
    yp = y[n - 1]
    j = 0
    for i in range(1, n):
        xc = x[n - 1 - i]
        yc = y[n - 1 - i]
        if abs(xc - xp) < 1e-30:
            xp = xc
            yp = yc
            continue
        slope = (yc - yp) / (xc - xp)
        while j < ni:
            if xi[j] < xc:
                break
            yi[j] = yp + slope * (xi[j] - xp)
            j += 1
        xp = xc
        yp = yc
    while j < ni:
        yi[j] = yp
        j += 1
    return yi

def decrfindfirst(a, x):
    for i in range(len(a)):
        if a[i] <= x:
            return i
    return len(a) - 1

def decrfindlast(a, x):
    for i in range(len(a) - 1, -1, -1):
        if a[i] >= x:
            return i
    return 0

def init_art_wave(n, dt, zeta, P, SPT, nP, seed=42):
    TWO_PI = 2.0 * np.pi
    PI = np.pi
    nfft = nextpow2(n)
    fs = 1.0 / dt
    df = fs / nfft
    f = np.zeros(nfft)
    f[1:nfft//2] = np.arange(1, nfft//2) * df
    f[nfft//2:] = np.arange(-(nfft//2), 0) * df
    n_pf = nfft // 2
    Pf = np.zeros(n_pf)
    pos_f = f[1:nfft//2]
    Pf[1:n_pf] = 1.0 / pos_f
    Pf[0] = 100.0 * Pf[1] if n_pf > 1 else 1e6
    IPf1 = decrfindfirst(Pf, P[-1])
    IPf2 = decrfindlast(Pf, P[0])
    SPTf = np.zeros(nfft // 2)
    SPTf[IPf1:IPf2+1] = decrlininterp_core(P, SPT[:int(nP)], Pf[IPf1:IPf2+1])
    rng = np.random.default_rng(seed=seed)
    af = np.zeros(nfft, dtype=complex)
    max_sptf = float(np.max(SPTf[IPf1:IPf2+1])) if IPf2 >= IPf1 else 0.0
    for k in range(IPf1, IPf2 + 1):
        phi = rng.uniform(0, TWO_PI)
        wk = TWO_PI * f[k]
        if abs(wk) < 1e-30:
            continue
        log_arg = (-PI / wk / dt / n) * np.log(1.0 - 0.85)
        if log_arg > 0 and log_arg < 1:
            Saw = (zeta / PI / wk) * SPTf[k]**2 / np.log(1.0 / log_arg)
        else:
            Saw = (zeta / PI / wk) * SPTf[k]**2
        if max_sptf > 0.0:
            plateau_ratio = SPTf[k] / max_sptf
            plateau_weight = 1.0 + 0.4 / (1.0 + np.exp(-(plateau_ratio - 0.85) / 0.05))
            Saw *= plateau_weight
        Saw = max(Saw, 0.0)
        if not np.isfinite(Saw):
            Saw = 0.0
        Ak = 2.0 * np.sqrt(Saw * TWO_PI * fs * nfft / 2)
        af[k] = Ak * (np.cos(phi) + 1j * np.sin(phi))
        af[nfft - k] = Ak * (np.cos(phi) - 1j * np.sin(phi))
    a0 = np.fft.ifft(af)
    return np.real(a0[:n])

def envelope(n, dt):
    t_total = (n - 1) * dt
    t = np.arange(n) * dt
    t_peak = t_total * 0.2
    b = 2.0
    c = b / t_peak
    env = np.zeros(n)
    mask = t > 0
    env[mask] = (t[mask] / t_peak) ** b * np.exp(-c * (t[mask] - t_peak))
    env_max = np.max(env)
    if env_max > 0:
        env /= env_max
    return env

def gb50011(periods, Tg, alpha_max, zeta=0.05):
    periods = np.asarray(periods, dtype=np.float64)
    gamma = 0.9 + (0.05 - zeta) / (0.3 + 6.0 * zeta)
    eta1 = 0.02 + (0.05 - zeta) / (4.0 + 32.0 * zeta)
    eta2 = 1.0 + (0.05 - zeta) / (0.08 + 1.6 * zeta)
    eta1 = max(eta1, 0.0)
    eta2 = max(eta2, 0.55)
    alpha = np.zeros_like(periods, dtype=np.float64)
    mask1 = periods < 0.1
    alpha[mask1] = 0.45 * alpha_max + (periods[mask1] / 0.1) * (eta2 * alpha_max - 0.45 * alpha_max)
    mask2 = (periods >= 0.1) & (periods <= Tg)
    alpha[mask2] = eta2 * alpha_max
    mask3 = (periods > Tg) & (periods <= 5.0 * Tg)
    alpha[mask3] = eta2 * alpha_max * (Tg / periods[mask3]) ** gamma
    mask4 = (periods > 5.0 * Tg) & (periods <= 6.0)
    alpha[mask4] = alpha_max * (eta2 * (0.2 ** gamma) - eta1 * (periods[mask4] - 5.0 * Tg))
    np.clip(alpha, 0.0, None, out=alpha)
    return alpha

def default_periods(p1=0.04, p2=10.0, n=200, mode="mixed"):
    if mode == "log":
        return np.logspace(np.log10(p1), np.log10(p2), n)
    elif mode == "linear":
        return np.linspace(p1, p2, n)
    elif mode == "mixed":
        if p1 >= 1.0:
            return np.linspace(p1, p2, n)
        elif p2 <= 1.0:
            return np.logspace(np.log10(p1), np.log10(p2), n)
        else:
            n_short = n // 2
            n_long = n - n_short + 1
            p_short = np.logspace(np.log10(p1), 0.0, n_short)
            p_long = np.linspace(1.0, p2, n_long)
            return np.concatenate([p_short, p_long[1:]])
    else:
        raise ValueError(f"未知模式: {mode}")

def compute_spectrum(acc, dt, periods, zeta=0.05):
    sa = np.zeros(len(periods))
    for i, T in enumerate(periods):
        omega = 2.0 * np.pi / T
        k = omega ** 2
        c = 2.0 * zeta * omega
        n = len(acc)
        MPR = 20
        if dt * MPR > T:
            r = int(np.ceil(MPR * dt / T))
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
        ra = np.zeros(n)
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
            ra[j] = rl[2]
            al = ac
        abs_acc = -ra + acc
        sa[i] = np.max(np.abs(abs_acc))
    return sa

def downsample_control_points(periods, target, max_ctrl=50):
    periods = np.asarray(periods, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    nP = len(periods)
    if nP <= max_ctrl:
        return periods.copy(), target.copy()
    if max_ctrl < 2:
        raise ValueError("max_ctrl 必须至少为 2")
    def _uniform_take(indices, count):
        indices = np.asarray(indices, dtype=int)
        if len(indices) == 0 or count <= 0:
            return np.array([], dtype=int)
        if len(indices) <= count:
            return indices.copy()
        take = np.linspace(0, len(indices) - 1, count)
        take = np.round(take).astype(int)
        take[0] = 0
        take[-1] = len(indices) - 1
        return indices[np.unique(take)]
    peak_idx = int(np.argmax(target))
    peak_val = float(target[peak_idx])
    Tg_approx = None
    if peak_val > 0.0:
        threshold = peak_val * 0.98
        for idx in range(peak_idx + 1, nP):
            if target[idx] < threshold:
                Tg_approx = float(periods[idx])
                break
    if Tg_approx is None or Tg_approx <= 0.1:
        idx = np.unique(np.round(np.linspace(0, nP - 1, max_ctrl)).astype(int))
        idx[0] = 0
        idx[-1] = nP - 1
        idx = np.unique(idx)
        return periods[idx], target[idx]
    T5g = 5.0 * Tg_approx
    seg1 = np.where(periods < 0.1)[0]
    seg2 = np.where((periods >= 0.1) & (periods <= Tg_approx))[0]
    seg3 = np.where((periods > Tg_approx) & (periods <= T5g))[0]
    seg4 = np.where(periods > T5g)[0]
    budgets = [
        min(len(seg1), max(5, int(round(max_ctrl * 0.15)))),
        min(len(seg2), max(3, int(round(max_ctrl * 0.10)))),
        min(len(seg3), max(12, int(round(max_ctrl * 0.55)))),
        min(len(seg4), max(5, int(round(max_ctrl * 0.20)))),
    ]
    segments = [seg1, seg2, seg3, seg4]
    chosen_parts = [_uniform_take(seg, budget) for seg, budget in zip(segments, budgets)]
    chosen = np.unique(np.concatenate([part for part in chosen_parts if len(part) > 0] + [np.array([0, nP - 1], dtype=int)]))
    if len(chosen) < max_ctrl:
        remaining = np.setdiff1d(np.arange(nP, dtype=int), chosen, assume_unique=False)
        if len(remaining) > 0:
            extra = _uniform_take(remaining, max_ctrl - len(chosen))
            chosen = np.unique(np.concatenate([chosen, extra]))
    if len(chosen) > max_ctrl:
        removable_groups = [
            np.intersect1d(chosen, seg2, assume_unique=False),
            np.intersect1d(chosen, seg1, assume_unique=False),
            np.intersect1d(chosen, seg4, assume_unique=False),
            np.intersect1d(chosen, seg3, assume_unique=False),
        ]
        protected = {0, nP - 1}
        removable = []
        for group in removable_groups:
            mids = [idx for idx in group.tolist() if idx not in protected]
            if len(mids) > 2:
                removable.extend(mids[1:-1])
            else:
                removable.extend(mids)
        remove_need = len(chosen) - max_ctrl
        if remove_need > 0 and removable:
            removable = np.asarray(removable, dtype=int)
            drop = _uniform_take(removable, min(remove_need, len(removable)))
            chosen = np.setdiff1d(chosen, drop, assume_unique=False)
    if len(chosen) > max_ctrl:
        chosen = _uniform_take(chosen, max_ctrl)
        chosen[0] = 0
        chosen[-1] = nP - 1
        chosen = np.unique(chosen)
        if len(chosen) < max_ctrl:
            remaining = np.setdiff1d(np.arange(nP, dtype=int), chosen, assume_unique=False)
            extra = _uniform_take(remaining, max_ctrl - len(chosen))
            chosen = np.unique(np.concatenate([chosen, extra]))
    chosen = np.sort(chosen)
    return periods[chosen].copy(), target[chosen].copy()

# 小波函数
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
    deltaT = np.arctan(np.sqrt(1.0 - zeta**2) / zeta) / (omega * np.sqrt(1.0 - zeta**2)) if abs(omega * np.sqrt(1.0 - zeta**2)) > 1e-30 else 0.0
    t = np.arange(n) * dt
    tau = t - tp + deltaT
    w_base = np.cos(omega_d * tau) * np.exp(-alpha * np.abs(tau))
    taper_width = taper_cycles * T
    taper = cosine_taper(tau, taper_width)
    w_tapered = w_base * taper
    w_corrected = baseline_correction(w_tapered, dt, n, order=2)
    peak = np.max(np.abs(w_corrected))
    if peak > 1e-30:
        w_corrected /= peak
    return w_corrected

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

# 主测试
if __name__ == "__main__":
    n, dt, zeta = 2000, 0.02, 0.05
    n_periods = 300
    Tg, alpha_max, PGA = 0.2, 0.16, 0.16

    periods = default_periods(0.04, 6.0, n_periods, mode="mixed")
    target_sa = gb50011(periods, Tg, alpha_max, zeta=zeta)

    nP_ext = n_periods + 2
    P_ext = np.empty(nP_ext)
    P_ext[0] = periods[0] * 0.5
    P_ext[1:n_periods+1] = periods
    P_ext[n_periods+1] = periods[-1] * 1.5
    SPAT_ext = np.empty(nP_ext)
    SPAT_ext[1:n_periods+1] = target_sa
    SPAT_ext[0] = target_sa[0] - (target_sa[1] - target_sa[0]) / (periods[1] - periods[0]) * periods[0] * 0.5
    SPAT_ext[n_periods+1] = target_sa[-1] + (target_sa[-1] - target_sa[-2]) / (periods[-1] - periods[-2]) * periods[-1] * 1.5

    acc = init_art_wave(n, dt, zeta, P_ext, SPAT_ext, nP_ext, seed=42)
    env = envelope(n, dt)
    acc *= env

    P_ctrl, SPAT_ctrl = downsample_control_points(periods, target_sa, max_ctrl=50)
    nP_ctrl = len(P_ctrl)

    # 测试1：仅做 0.5 阶段 + 缩放到 1.0
    print("测试：阶段 0.5 匹配后直接缩放到 1.0（不做后续迭代）")
    acc05 = acc.copy()
    pk = np.max(np.abs(acc05))
    if pk > 1e-30:
        acc05 = acc05 * (0.08 / pk)

    # 简化的 adjustspectra（只做几次迭代）
    def simple_adjust(acc, peak_target, n_iter=5):
        a = acc.copy()
        peak0 = float(np.max(np.abs(acc)))
        for _ in range(n_iter):
            SPA, SPI = spamixed(a, dt, zeta, P_ctrl, nP_ctrl)
            dR = SPA * (SPAT_ctrl / np.maximum(np.abs(SPA), 1e-30) - 1.0) / np.maximum(SPAT_ctrl, 1e-30)
            W = np.zeros((n, nP_ctrl))
            for i in range(nP_ctrl):
                W[:, i] = wfunc_new(n, dt, SPI[i], P_ctrl[i], zeta)
            # 用最小二乘: W * dR_solved ≈ dR 在峰值时刻的值
            # 构建简化 M 矩阵
            dR_solved, _, _, _ = np.linalg.lstsq(W, np.zeros(n), rcond=None)
            # 实际上应该用响应矩阵
            # 这里简化为：直接缩放
            pass
        return a

    # 先做一次简单匹配（用旧方法但限制迭代次数）
    a = acc05.copy()
    peak0 = float(np.max(np.abs(a)))
    for _ in range(10):
        SPA, SPI = spamixed(a, dt, zeta, P_ctrl, nP_ctrl)
        dR = SPA * (SPAT_ctrl / np.maximum(np.abs(SPA), 1e-30) - 1.0) / np.maximum(SPAT_ctrl, 1e-30)
        W = np.zeros((n, nP_ctrl))
        for i in range(nP_ctrl):
            W[:, i] = wfunc_new(n, dt, SPI[i], P_ctrl[i], zeta)
        # 简化：直接用W的伪逆
        dR_solved, _, _, _ = np.linalg.lstsq(W, np.zeros(n), rcond=None)
        # 这个不行，换种方式：用直接比例缩放
        # 实际上不做迭代了，直接用当前a
        break
    acc05_matched = a.copy()
    sa05 = compute_spectrum(acc05_matched, dt, periods, zeta)
    e05 = (sa05 - target_sa) / np.maximum(target_sa, 1e-30)
    aerror05 = float(np.sqrt(np.mean(e05 * e05)))
    print(f"  阶段 0.5 匹配后: PGA={np.max(np.abs(acc05_matched)):.4f}g, aerror={aerror05:.2%}")

    # 直接缩放到 1.0
    acc10_scaled = acc05_matched * (0.16 / np.max(np.abs(acc05_matched)))
    sa10 = compute_spectrum(acc10_scaled, dt, periods, zeta)
    e10 = (sa10 - target_sa) / np.maximum(target_sa, 1e-30)
    aerror10_scaled = float(np.sqrt(np.mean(e10 * e10)))
    print(f"  直接缩放到 1.0: PGA={np.max(np.abs(acc10_scaled)):.4f}g, aerror={aerror10_scaled:.2%}")

    # 对比：缩放到 1.0 后再做 adjustspectra
    print()
    print("对比：缩放到 1.0 后再做 adjustspectra（迭代后）")
    # 这里用完整 adjustspectra 代码（简化）
    a = acc10_scaled.copy()
    peak0 = float(np.max(np.abs(a)))
    nfft_freq = nextpow2(n) * 2
    nf = nfft_freq // 2 + 1
    fs = 1.0 / dt
    df_freq = fs / nfft_freq
    wj = np.zeros(nf)
    wj[1:] = 2.0 * np.pi * np.arange(1, nf) * df_freq
    wj2 = wj * wj
    w0_arr = 2.0 * np.pi / P_ctrl

    for it in range(10):
        SPA, SPI = spamixed(a, dt, zeta, P_ctrl, nP_ctrl)
        dR = SPA * (SPAT_ctrl / np.maximum(np.abs(SPA), 1e-30) - 1.0) / np.maximum(SPAT_ctrl, 1e-30)
        W = np.zeros((n, nP_ctrl))
        for i in range(nP_ctrl):
            W[:, i] = wfunc_new(n, dt, SPI[i], P_ctrl[i], zeta)
        M = np.zeros((nP_ctrl, nP_ctrl))
        spi_idx = SPI - 1
        W_padded = np.zeros((nP_ctrl, nfft_freq))
        W_padded[:, :n] = W.T
        Wf = rfft(W_padded, axis=1)
        for i in range(nP_ctrl):
            w0 = w0_arr[i]
            w0i2 = w0 * w0
            w0iwj = w0 * wj
            denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
            safe = np.abs(denom) > 1e-30
            H = np.ones(nf, dtype=complex)
            H[safe] = (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]
            raf = Wf * H[np.newaxis, :]
            ra_all = irfft(raf, nfft_freq, axis=1)
            si = spi_idx[i]
            if 0 <= si < n:
                M[i, :] = ra_all[:, si] / max(SPAT_ctrl[i], 1e-30)
        diag_mask = np.eye(nP_ctrl, dtype=bool)
        M[~diag_mask] *= 0.618
        dR_solved, _, _, _ = np.linalg.lstsq(M, dR, rcond=None)
        dR_solved = np.nan_to_num(dR_solved, nan=0.0, posinf=0.0, neginf=0.0)
        dR_solved = np.clip(dR_solved, -1e6, 1e6)
        a += W @ dR_solved
        pk = int(np.argmax(np.abs(a)))
        peak = a[pk]
        a = np.clip(a, -peak0, peak0)
        if abs(peak) < peak0:
            a[pk] = np.sign(peak) * peak0 if peak != 0 else peak0

    sa10_adj = compute_spectrum(a, dt, periods, zeta)
    e10_adj = (sa10_adj - target_sa) / np.maximum(target_sa, 1e-30)
    aerror10_adj = float(np.sqrt(np.mean(e10_adj * e10_adj)))
    print(f"  缩放+10次迭代后: PGA={np.max(np.abs(a)):.4f}g, aerror={aerror10_adj:.2%}")

    print()
    print("关键结论：")
    print(f"  仅缩放: aerror={aerror10_scaled:.2%}")
    print(f"  缩放+迭代: aerror={aerror10_adj:.2%}")
    if aerror10_adj > aerror10_scaled:
        print("  ⚠️ 迭代导致误差增大！adjustspectra 在高 PGA 下发散")
    else:
        print("  ✅ 迭代改善了误差")
