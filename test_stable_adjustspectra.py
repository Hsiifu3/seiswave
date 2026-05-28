"""
单一算法稳定方案：内嵌渐进 PGA + 线搜索的 adjustspectra

核心改进（全部在 adjustspectra 框架内，不切换算法）：
1. peak0 在迭代中渐进提升（从初始 PGA 平滑过渡到目标 PGA）
2. backtracking line search：确保每次叠加小波后误差确实下降
3. 智能步长衰减：当误差震荡时自动减小搜索步长
4. 保持 Atik 小波基
"""

import numpy as np
from numpy.fft import rfft, irfft
import time

# ═══════════════════════════════════════════════════════════
# 基础函数（复用之前验证过的实现）
# ═══════════════════════════════════════════════════════════

def nextpow2(n):
    p = 1
    while p < n:
        p *= 2
    return p

def decrlininterp_core(x, y, xi):
    n = len(x); ni = len(xi); yi = np.zeros(ni)
    xp, yp, j = x[n-1], y[n-1], 0
    for i in range(1, n):
        xc, yc = x[n-1-i], y[n-1-i]
        if abs(xc-xp) < 1e-30: xp, yp = xc, yc; continue
        slope = (yc-yp)/(xc-xp)
        while j < ni:
            if xi[j] < xc: break
            yi[j] = yp + slope*(xi[j]-xp); j += 1
        xp, yp = xc, yc
    while j < ni: yi[j] = yp; j += 1
    return yi

def decrfindfirst(a, x):
    for i in range(len(a)):
        if a[i] <= x: return i
    return len(a)-1

def decrfindlast(a, x):
    for i in range(len(a)-1, -1, -1):
        if a[i] >= x: return i
    return 0

def init_art_wave(n, dt, zeta, P, SPT, nP, seed=42):
    TWO_PI, PI = 2.0*np.pi, np.pi
    nfft = nextpow2(n)
    fs, df = 1.0/dt, 1.0/dt/nfft
    f = np.zeros(nfft)
    f[1:nfft//2] = np.arange(1, nfft//2)*df
    f[nfft//2:] = np.arange(-(nfft//2), 0)*df
    n_pf = nfft//2
    Pf = np.zeros(n_pf)
    Pf[1:n_pf] = 1.0/f[1:nfft//2]
    Pf[0] = 100.0*Pf[1] if n_pf > 1 else 1e6
    IPf1 = decrfindfirst(Pf, P[-1])
    IPf2 = decrfindlast(Pf, P[0])
    SPTf = np.zeros(nfft//2)
    SPTf[IPf1:IPf2+1] = decrlininterp_core(P, SPT[:int(nP)], Pf[IPf1:IPf2+1])
    rng = np.random.default_rng(seed=seed)
    af = np.zeros(nfft, dtype=complex)
    max_sptf = float(np.max(SPTf[IPf1:IPf2+1])) if IPf2 >= IPf1 else 0.0
    for k in range(IPf1, IPf2+1):
        phi = rng.uniform(0, TWO_PI)
        wk = TWO_PI*f[k]
        if abs(wk) < 1e-30: continue
        log_arg = (-PI/wk/dt/n)*np.log(1.0-0.85)
        Saw = (zeta/PI/wk)*SPTf[k]**2/(np.log(1.0/log_arg) if log_arg>0 and log_arg<1 else 1.0)
        if max_sptf > 0.0:
            plateau_ratio = SPTf[k]/max_sptf
            Saw *= 1.0 + 0.4/(1.0+np.exp(-(plateau_ratio-0.85)/0.05))
        Saw = max(Saw, 0.0)
        if not np.isfinite(Saw): Saw = 0.0
        Ak = 2.0*np.sqrt(Saw*TWO_PI*fs*nfft/2)
        af[k] = Ak*(np.cos(phi)+1j*np.sin(phi))
        af[nfft-k] = Ak*(np.cos(phi)-1j*np.sin(phi))
    return np.real(np.fft.ifft(af)[:n])

def envelope(n, dt):
    t_total = (n-1)*dt
    t = np.arange(n)*dt
    t_peak = t_total*0.2
    b, c = 2.0, 2.0/t_peak
    env = np.zeros(n)
    mask = t > 0
    env[mask] = (t[mask]/t_peak)**b * np.exp(-c*(t[mask]-t_peak))
    env_max = np.max(env)
    return env/env_max if env_max > 0 else env

def gb50011(periods, Tg, alpha_max, zeta=0.05):
    periods = np.asarray(periods, dtype=np.float64)
    gamma = 0.9 + (0.05-zeta)/(0.3+6.0*zeta)
    eta1 = max(0.02+(0.05-zeta)/(4.0+32.0*zeta), 0.0)
    eta2 = max(1.0+(0.05-zeta)/(0.08+1.6*zeta), 0.55)
    alpha = np.zeros_like(periods)
    m1 = periods < 0.1
    alpha[m1] = 0.45*alpha_max + (periods[m1]/0.1)*(eta2*alpha_max-0.45*alpha_max)
    m2 = (periods >= 0.1) & (periods <= Tg)
    alpha[m2] = eta2*alpha_max
    m3 = (periods > Tg) & (periods <= 5.0*Tg)
    alpha[m3] = eta2*alpha_max*(Tg/periods[m3])**gamma
    m4 = (periods > 5.0*Tg) & (periods <= 6.0)
    alpha[m4] = alpha_max*(eta2*(0.2**gamma)-eta1*(periods[m4]-5.0*Tg))
    return np.clip(alpha, 0.0, None)

def default_periods(p1=0.04, p2=10.0, n=200, mode="mixed"):
    if mode == "log": return np.logspace(np.log10(p1), np.log10(p2), n)
    elif mode == "linear": return np.linspace(p1, p2, n)
    elif mode == "mixed":
        if p1 >= 1.0: return np.linspace(p1, p2, n)
        elif p2 <= 1.0: return np.logspace(np.log10(p1), np.log10(p2), n)
        else:
            n_short, n_long = n//2, n-n//2+1
            return np.concatenate([np.logspace(np.log10(p1), 0.0, n_short),
                                   np.linspace(1.0, p2, n_long)[1:]])
    else: raise ValueError(f"未知模式: {mode}")

def compute_spectrum(acc, dt, periods, zeta=0.05):
    sa = np.zeros(len(periods))
    for i, T in enumerate(periods):
        omega = 2.0*np.pi/T
        k, c = omega**2, 2.0*zeta*omega
        n, MPR = len(acc), 20
        if dt*MPR > T:
            r, sub_dt = int(np.ceil(MPR*dt/T)), dt/int(np.ceil(MPR*dt/T))
        else: r, sub_dt = 1, dt
        beta, gamma = 0.25, 0.5
        b1, b2, b3 = 1.0/(beta*sub_dt**2), 1.0/(beta*sub_dt), 1.0/(2.0*beta)-1.0
        b4, b5 = gamma/(beta*sub_dt), gamma/beta-1.0
        b6 = 0.5*sub_dt*(gamma/beta-2.0)
        keff, kinv = k+b1+b4*c, 1.0/(k+b1+b4*c)
        rl, al, ra = np.zeros(3), 0.0, np.zeros(len(acc))
        for j in range(len(acc)):
            ac, da = acc[j], (acc[j]-al)/r
            for jj in range(1, r+1):
                ac_sub = al+da*jj
                feff = ac_sub+(b1*rl[0]+b2*rl[1]+b3*rl[2])+c*(b4*rl[0]+b5*rl[1]+b6*rl[2])
                rc0, rc1, rc2 = feff*kinv, b4*(feff*kinv-rl[0])-b5*rl[1]-b6*rl[2], ac_sub-k*feff*kinv-c*(b4*(feff*kinv-rl[0])-b5*rl[1]-b6*rl[2])
                rl[0], rl[1], rl[2] = rc0, rc1, rc2
            ra[j] = rl[2]
            al = acc[j]
        sa[i] = np.max(np.abs(-ra+acc))
    return sa

def downsample_control_points(periods, target, max_ctrl=50):
    periods, target, nP = np.asarray(periods), np.asarray(target), len(periods)
    if nP <= max_ctrl: return periods.copy(), target.copy()
    def _uniform_take(indices, count):
        indices = np.asarray(indices, dtype=int)
        if len(indices)==0 or count<=0: return np.array([], dtype=int)
        if len(indices)<=count: return indices.copy()
        take = np.round(np.linspace(0, len(indices)-1, count)).astype(int)
        take[0], take[-1] = 0, len(indices)-1
        return indices[np.unique(take)]
    peak_idx, peak_val = int(np.argmax(target)), float(np.max(target))
    Tg_approx = None
    if peak_val > 0.0:
        for idx in range(peak_idx+1, nP):
            if target[idx] < peak_val*0.98:
                Tg_approx = float(periods[idx]); break
    if Tg_approx is None or Tg_approx <= 0.1:
        idx = np.unique(np.round(np.linspace(0, nP-1, max_ctrl)).astype(int))
        idx[0], idx[-1] = 0, nP-1
        return periods[np.unique(idx)], target[np.unique(idx)]
    T5g = 5.0*Tg_approx
    seg = [np.where(periods < 0.1)[0],
           np.where((periods >= 0.1) & (periods <= Tg_approx))[0],
           np.where((periods > Tg_approx) & (periods <= T5g))[0],
           np.where(periods > T5g)[0]]
    budgets = [min(len(s), max(5,int(round(max_ctrl*0.15)))) for s in seg[:2]] + \
              [min(len(seg[2]), max(12,int(round(max_ctrl*0.55)))),
               min(len(seg[3]), max(5,int(round(max_ctrl*0.20))))]
    parts = [_uniform_take(s, b) for s, b in zip(seg, budgets)]
    chosen = np.unique(np.concatenate([p for p in parts if len(p)>0] + [np.array([0,nP-1],dtype=int)]))
    if len(chosen) < max_ctrl:
        rem = np.setdiff1d(np.arange(nP,dtype=int), chosen, assume_unique=False)
        if len(rem) > 0:
            chosen = np.unique(np.concatenate([chosen, _uniform_take(rem, max_ctrl-len(chosen))]))
    if len(chosen) > max_ctrl:
        for g in [np.intersect1d(chosen, seg[1], assume_unique=False),
                  np.intersect1d(chosen, seg[0], assume_unique=False),
                  np.intersect1d(chosen, seg[3], assume_unique=False),
                  np.intersect1d(chosen, seg[2], assume_unique=False)]:
            mids = [idx for idx in g.tolist() if idx not in {0, nP-1}]
            drop = _uniform_take(mids[1:-1] if len(mids)>2 else mids, len(chosen)-max_ctrl)
            chosen = np.setdiff1d(chosen, np.asarray(drop,dtype=int), assume_unique=False)
            if len(chosen) <= max_ctrl: break
    if len(chosen) > max_ctrl:
        chosen = _uniform_take(chosen, max_ctrl)
        chosen[0], chosen[-1] = 0, nP-1
        chosen = np.unique(chosen)
    return periods[np.sort(chosen)].copy(), target[np.sort(chosen)].copy()

def spamixed(acc, dt, zeta, periods, nP):
    n, threshold = len(acc), 20.0*dt
    spa, spi = np.zeros(nP), np.ones(nP, dtype=np.int32)
    m = sum(1 for i in range(nP) if periods[i] < threshold) + (1 if sum(1 for i in range(nP) if periods[i] < threshold) < nP else 0)
    if m > 0:
        nfft = nextpow2(n)
        a0, nf = np.zeros(nfft), nfft//2+1
        a0[:n] = acc
        af, fs, df = rfft(a0), 1.0/dt, 1.0/dt/nfft
        wj = np.zeros(nf)
        wj[1:] = 2.0*np.pi*np.arange(1,nf)*df
        wj2 = wj*wj
        for i in range(m):
            w0, w0i2, w0iwj = 2.0*np.pi/periods[i], (2.0*np.pi/periods[i])**2, (2.0*np.pi/periods[i])*wj
            denom = w0i2 - wj2 + 2.0j*zeta*w0iwj
            safe = np.abs(denom) > 1e-30
            raf = np.zeros(nf, dtype=complex)
            raf[safe] = af[safe]*(w0i2+2.0j*zeta*w0iwj[safe])/denom[safe]
            ra = irfft(raf, nfft)[:n]
            idx = np.argmax(np.abs(ra))
            spa[i], spi[i] = ra[idx], idx+1
    for i in range(m, nP):
        omega, k, c = 2.0*np.pi/periods[i], (2.0*np.pi/periods[i])**2, 2.0*zeta*(2.0*np.pi/periods[i])
        MPR = 20
        if dt*MPR > periods[i]:
            r, sub_dt = int(np.ceil(MPR*dt/periods[i])), dt/int(np.ceil(MPR*dt/periods[i]))
        else: r, sub_dt = 1, dt
        beta, gamma = 0.25, 0.5
        b1, b2, b3 = 1.0/(beta*sub_dt**2), 1.0/(beta*sub_dt), 1.0/(2.0*beta)-1.0
        b4, b5 = gamma/(beta*sub_dt), gamma/beta-1.0
        b6 = 0.5*sub_dt*(gamma/beta-2.0)
        keff, kinv = k+b1+b4*c, 1.0/(k+b1+b4*c)
        rl, al, ra_n = np.zeros(3), 0.0, np.zeros(n)
        for j in range(n):
            ac, da = acc[j], (acc[j]-al)/r
            for jj in range(1, r+1):
                ac_sub = al+da*jj
                feff = ac_sub+(b1*rl[0]+b2*rl[1]+b3*rl[2])+c*(b4*rl[0]+b5*rl[1]+b6*rl[2])
                rc0, rc1 = feff*kinv, b4*(feff*kinv-rl[0])-b5*rl[1]-b6*rl[2]
                rc2 = ac_sub-k*feff*kinv-c*(b4*(feff*kinv-rl[0])-b5*rl[1]-b6*rl[2])
                rl[0], rl[1], rl[2] = rc0, rc1, rc2
            ra_n[j] = -rl[2]+ac
            al = ac
        idx = np.argmax(np.abs(ra_n))
        spa[i], spi[i] = ra_n[idx], idx+1
    return spa, spi

# ═══════════════════════════════════════════════════════════
# 小波基
# ═══════════════════════════════════════════════════════════

def cosine_taper(tau, width):
    taper = np.ones_like(tau, dtype=np.float64)
    w2 = 2.0*width
    mr, mz = (np.abs(tau)>width)&(np.abs(tau)<=w2), np.abs(tau)>w2
    if np.any(mr):
        taper[mr] = 0.5*(1.0+np.cos(np.pi*(np.abs(tau[mr])-width)/width))
    taper[mz] = 0.0
    return taper

def baseline_correction(w, dt, n, order=2):
    t = np.arange(n)*dt
    if order == 1: return w - np.mean(w)
    v_raw, d_raw = np.cumsum(w)*dt, np.cumsum(np.cumsum(w)*dt)*dt
    ones = np.ones(n)
    v_1, d_1 = np.cumsum(ones)*dt, np.cumsum(np.cumsum(ones)*dt)*dt
    v_t, d_t = np.cumsum(t)*dt, np.cumsum(np.cumsum(t)*dt)*dt
    try:
        c0, c1 = np.linalg.solve(np.array([[v_1[-1],v_t[-1]],[d_1[-1],d_t[-1]]]), np.array([v_raw[-1],d_raw[-1]]))
    except np.linalg.LinAlgError:
        c0, c1 = np.mean(w), 0.0
    return w - c0 - c1*t

def wfunc_old(n, dt, itm, P, zeta):
    TWO_PI = 2.0*np.pi
    tm = (itm-1)*dt
    w, f, tmp1 = TWO_PI/P, 1.0/P, np.sqrt(1.0-zeta**2)
    gamma = 1.178*(f*tmp1)**(-0.93)
    deltaT = np.arctan(tmp1/zeta)/(w*tmp1) if abs(w*tmp1) > 1e-30 else 0.0
    t = np.arange(n)*dt
    return np.cos(w*tmp1*(t-tm+deltaT))*np.exp(-((t-tm+deltaT)/gamma)**2)

def wfunc_new(n, dt, itm, T, zeta, taper_cycles=3.0):
    TWO_PI = 2.0*np.pi
    tp = (itm-1)*dt
    omega = TWO_PI/T
    omega_d = omega*np.sqrt(1.0-zeta**2)
    alpha = zeta*omega/np.sqrt(1.0-zeta**2) if abs(zeta)<0.999 and abs(1.0-zeta**2)>1e-30 else zeta*omega
    # deltaT 补偿 SDOF 相位滞后，使小波峰值与响应峰值对齐
    deltaT = np.arctan(np.sqrt(1.0-zeta**2)/zeta)/(omega*np.sqrt(1.0-zeta**2)) if abs(omega*np.sqrt(1.0-zeta**2))>1e-30 else 0.0
    t = np.arange(n)*dt
    tau = t - tp + deltaT
    w_base = np.cos(omega_d*tau)*np.exp(-alpha*np.abs(tau))
    taper = cosine_taper(tau, taper_cycles*T)
    w_tapered = w_base*taper
    w_corr = baseline_correction(w_tapered, dt, n, order=2)
    peak = np.max(np.abs(w_corr))
    return w_corr/peak if peak > 1e-30 else w_corr

# ═══════════════════════════════════════════════════════════
# 核心改进：内嵌渐进 PGA + 线搜索的 adjustspectra
# ═══════════════════════════════════════════════════════════

def adjustspectra_stable(acc, n, dt, zeta, P, nP, SPAT, tol, max_iter,
                          target_peak=None,           # 目标 PGA（如果为 None，则保持原有行为）
                          peak_ramp_fraction=0.7,      # 在前 70% 迭代内完成 PGA 提升
                          line_search=True,             # 启用线搜索
                          use_new_wavelet=True,         # 使用 Atik 小波
                          damping=0.0,                # M^T M 对角阻尼（0=无）
                          verbose=False):
    """
    稳定版 adjustspectra：单一算法内解决高 PGA 下发散问题。

    核心改进：
    1. 渐进 peak0：iteration 0→N 时，peak0 从 initial_peak 平滑提升到 target_peak
       避免了外部"缩放+再匹配"导致的谱形破坏
    2. Backtracking line search：尝试多个步长，确保每次迭代误差下降
    3. 阻尼：在 M^T M 对角加 lambda，改善病态矩阵的稳定性
    4. 智能 dR clip：基于当前 peak0 的比例限制单次调整量
    """
    a = acc.copy()
    initial_peak = float(np.max(np.abs(acc)))
    # 如果未指定目标峰值，使用初始峰值（向后兼容）
    target_peak = target_peak if target_peak is not None else initial_peak

    # 预计算常数
    nfft_freq = nextpow2(n)*2
    nf = nfft_freq//2+1
    fs, df_freq = 1.0/dt, 1.0/dt/nfft_freq
    wj = np.zeros(nf)
    wj[1:] = 2.0*np.pi*np.arange(1,nf)*df_freq
    wj2 = wj*wj
    w0_arr = 2.0*np.pi/P

    # 迭代记录
    best_a, best_err = a.copy(), float('inf')
    current_alpha = 1.0  # 线搜索起始步长

    for iteration in range(max_iter):
        # ── 1. 渐进 peak0 ──
        if target_peak > initial_peak:
            ramp_iters = max(1, int(max_iter*peak_ramp_fraction))
            if iteration < ramp_iters:
                frac = iteration/ramp_iters
                # 使用平滑曲线 (ease-in-out) 避免突变
                frac = frac*frac*(3.0-2.0*frac)
                peak0 = initial_peak + (target_peak-initial_peak)*frac
            else:
                peak0 = target_peak
        else:
            peak0 = target_peak

        # ── 2. 计算当前反应谱和误差 ──
        SPA, SPI = spamixed(a, dt, zeta, P, nP)
        e = (np.abs(SPA)-SPAT)/np.maximum(np.abs(SPAT), 1e-30)
        aerror = float(np.sqrt(np.mean(e*e)))
        merror = float(np.max(np.abs(e)))

        if aerror < best_err:
            best_err, best_a = aerror, a.copy()

        if verbose and iteration % 5 == 0:
            print(f"  iter {iteration:3d}: peak0={peak0:.4f}g aerror={aerror:.2%} merror={merror:.2%} alpha={current_alpha:.3f}")

        # 收敛判断
        if aerror <= tol and merror <= 3.0*tol:
            if verbose: print(f"  收敛于 iter {iteration}")
            break

        # ── 3. 计算目标调整量 dR ──
        dR = SPA*(SPAT/np.maximum(np.abs(SPA), 1e-30)-1.0)/np.maximum(SPAT, 1e-30)

        # ── 4. 构建小波和响应矩阵 ──
        W = np.zeros((n, nP))
        for i in range(nP):
            W[:,i] = wfunc_new(n, dt, SPI[i], P[i], zeta) if use_new_wavelet else wfunc_old(n, dt, SPI[i], P[i], zeta)

        M = np.zeros((nP, nP))
        spi_idx = SPI-1
        W_padded = np.zeros((nP, nfft_freq))
        W_padded[:,:n] = W.T
        Wf = rfft(W_padded, axis=1)

        for i in range(nP):
            w0, w0i2, w0iwj = w0_arr[i], w0_arr[i]**2, w0_arr[i]*wj
            denom = w0i2 - wj2 + 2.0j*zeta*w0iwj
            safe = np.abs(denom) > 1e-30
            H = np.ones(nf, dtype=complex)
            H[safe] = (w0i2+2.0j*zeta*w0iwj[safe])/denom[safe]
            raf = Wf*H[np.newaxis,:]
            ra_all = irfft(raf, nfft_freq, axis=1)
            si = spi_idx[i]
            if 0 <= si < n:
                M[i,:] = ra_all[:,si]/max(SPAT[i], 1e-30)

        diag_mask = np.eye(nP, dtype=bool)
        M[~diag_mask] *= 0.618

        # ── 5. 求解 dR_solved（带阻尼）──
        if damping > 0:
            MTM = M.T @ M
            for i in range(nP):
                MTM[i,i] += damping
            try:
                dR_solved = np.linalg.solve(MTM, M.T @ dR)
            except np.linalg.LinAlgError:
                dR_solved, _, _, _ = np.linalg.lstsq(M, dR, rcond=None)
        else:
            dR_solved, _, _, _ = np.linalg.lstsq(M, dR, rcond=None)

        dR_solved = np.nan_to_num(dR_solved, nan=0.0, posinf=0.0, neginf=0.0)

        # 智能 clip：单次调整不超过当前 peak0 的 30%
        max_dR = peak0 * 0.3
        dR_solved = np.clip(dR_solved, -max_dR, max_dR)

        # ── 6. 线搜索（backtracking）──
        if line_search:
            # 尝试的步长：从 current_alpha 开始，逐步减半
            alphas = [current_alpha, current_alpha*0.5, current_alpha*0.25, 0.125, 0.0625, 0.03125]
            alphas = [a for a in alphas if a >= 0.03125]

            best_alpha_this_iter, best_err_this_iter, best_a_this_iter = 0, aerror, a.copy()

            for alpha in alphas:
                a_test = a + alpha * (W @ dR_solved)
                a_test = np.nan_to_num(a_test, nan=0.0, posinf=peak0, neginf=-peak0)
                a_test = np.clip(a_test, -peak0, peak0)
                # 软 peak 约束：如果峰值不足，轻微提升
                pk_test = np.max(np.abs(a_test))
                if pk_test < peak0*0.99 and pk_test > 0:
                    a_test = a_test * (peak0/pk_test)

                SPA_test, _ = spamixed(a_test, dt, zeta, P, nP)
                e_test = (np.abs(SPA_test)-SPAT)/np.maximum(np.abs(SPAT), 1e-30)
                aerror_test = float(np.sqrt(np.mean(e_test*e_test)))

                if aerror_test < best_err_this_iter:
                    best_err_this_iter = aerror_test
                    best_alpha_this_iter = alpha
                    best_a_this_iter = a_test.copy()

            if best_alpha_this_iter > 0:
                a = best_a_this_iter
                current_alpha = min(1.0, best_alpha_this_iter * 1.5)  # 下次稍微大胆一点
            else:
                # 所有步长都增大误差，尝试更小步长或停止
                current_alpha *= 0.5
                if current_alpha < 0.03125:
                    if verbose: print(f"  线搜索失败于 iter {iteration}，停止")
                    break
        else:
            # 无搜索，直接全量叠加
            delta_a = W @ dR_solved
            delta_a = np.nan_to_num(delta_a, nan=0.0, posinf=0.0, neginf=0.0)
            a = np.nan_to_num(a, nan=0.0, posinf=0.0, neginf=0.0)
            a += delta_a
            a = np.clip(a, -peak0, peak0)
            pk = int(np.argmax(np.abs(a)))
            if abs(a[pk]) < peak0:
                a[pk] = np.sign(a[pk])*peak0 if a[pk] != 0 else peak0

    return best_a, best_err


# ═══════════════════════════════════════════════════════════
# 主测试：单一算法解决高 PGA 问题
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 70)
    print("稳定版 adjustspectra 验证：单一算法解决高 PGA 下发散")
    print("=" * 70)
    print()

    n, dt, zeta = 2000, 0.02, 0.05
    n_periods = 300
    Tg, alpha_max, PGA = 0.2, 0.16, 0.16

    # 1. 目标谱
    periods = default_periods(0.04, 6.0, n_periods, mode="mixed")
    target_sa = gb50011(periods, Tg, alpha_max, zeta=zeta)

    # 2. 初始信号
    nP_ext = n_periods + 2
    P_ext = np.empty(nP_ext)
    P_ext[0] = periods[0]*0.5
    P_ext[1:n_periods+1] = periods
    P_ext[n_periods+1] = periods[-1]*1.5
    SPAT_ext = np.empty(nP_ext)
    SPAT_ext[1:n_periods+1] = target_sa
    SPAT_ext[0] = target_sa[0]-(target_sa[1]-target_sa[0])/(periods[1]-periods[0])*periods[0]*0.5
    SPAT_ext[n_periods+1] = target_sa[-1]+(target_sa[-1]-target_sa[-2])/(periods[-1]-periods[-2])*periods[-1]*1.5

    acc = init_art_wave(n, dt, zeta, P_ext, SPAT_ext, nP_ext, seed=42)
    env = envelope(n, dt)
    acc *= env

    pk_env = float(np.max(np.abs(acc)))
    sa_env = compute_spectrum(acc, dt, periods, zeta)
    e_env = (sa_env - target_sa)/np.maximum(target_sa, 1e-30)
    aerror_env = float(np.sqrt(np.mean(e_env*e_env)))

    print(f"初始信号: PGA={pk_env:.4f}g, aerror={aerror_env:.2%}")
    print(f"目标 PGA: {PGA:.4f}g")
    print()

    # 降采样控制点
    P_ctrl, SPAT_ctrl = downsample_control_points(periods, target_sa, max_ctrl=50)
    nP_ctrl = len(P_ctrl)
    print(f"控制周期数: {nP_ctrl}")
    print()

    # ═══════════════════════════════════════════════════════════
    # 测试 1：原始 adjustspectra（旧小波，无渐进 PGA）
    # ═══════════════════════════════════════════════════════════
    print("[1/5] 原始 adjustspectra（旧小波，无渐进 PGA，向后兼容）")
    t0 = time.time()
    acc1, err1 = adjustspectra_stable(acc.copy(), n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl,
                                       tol=0.05, max_iter=50,
                                       target_peak=None,  # 保持原有行为
                                       line_search=False,
                                       use_new_wavelet=False,
                                       damping=0.0,
                                       verbose=False)
    t1 = time.time()-t0
    pk1 = float(np.max(np.abs(acc1)))
    sa1 = compute_spectrum(acc1, dt, periods, zeta)
    e1 = (sa1-target_sa)/np.maximum(target_sa, 1e-30)
    aerror1 = float(np.sqrt(np.mean(e1*e1)))
    merror1 = float(np.max(np.abs(e1)))
    print(f"      PGA={pk1:.4f}g, aerror={aerror1:.2%}, merror={merror1:.2%}, time={t1:.1f}s")
    print()

    # ═══════════════════════════════════════════════════════════
    # 测试 2：稳定版（Atik小波 + 内嵌渐进PGA + 线搜索）
    # ═══════════════════════════════════════════════════════════
    print("[2/5] 稳定版 adjustspectra（Atik小波 + 内嵌渐进PGA + 线搜索）")
    t0 = time.time()
    acc2, err2 = adjustspectra_stable(acc.copy(), n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl,
                                       tol=0.05, max_iter=50,
                                       target_peak=PGA,
                                       peak_ramp_fraction=0.7,
                                       line_search=True,
                                       use_new_wavelet=True,
                                       damping=0.01,
                                       verbose=True)
    t2 = time.time()-t0
    pk2 = float(np.max(np.abs(acc2)))
    sa2 = compute_spectrum(acc2, dt, periods, zeta)
    e2 = (sa2-target_sa)/np.maximum(target_sa, 1e-30)
    aerror2 = float(np.sqrt(np.mean(e2*e2)))
    merror2 = float(np.max(np.abs(e2)))
    print(f"      PGA={pk2:.4f}g, aerror={aerror2:.2%}, merror={merror2:.2%}, time={t2:.1f}s")
    print()

    # ═══════════════════════════════════════════════════════════
    # 测试 3：对比——不用线搜索，只用渐进 PGA
    # ═══════════════════════════════════════════════════════════
    print("[3/5] 仅用渐进 PGA（无线搜索）")
    t0 = time.time()
    acc3, err3 = adjustspectra_stable(acc.copy(), n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl,
                                       tol=0.05, max_iter=50,
                                       target_peak=PGA,
                                       peak_ramp_fraction=0.7,
                                       line_search=False,
                                       use_new_wavelet=True,
                                       damping=0.01,
                                       verbose=False)
    t3 = time.time()-t0
    pk3 = float(np.max(np.abs(acc3)))
    sa3 = compute_spectrum(acc3, dt, periods, zeta)
    e3 = (sa3-target_sa)/np.maximum(target_sa, 1e-30)
    aerror3 = float(np.sqrt(np.mean(e3*e3)))
    merror3 = float(np.max(np.abs(e3)))
    print(f"      PGA={pk3:.4f}g, aerror={aerror3:.2%}, merror={merror3:.2%}, time={t3:.1f}s")
    print()

    # ═══════════════════════════════════════════════════════════
    # 测试 4：仅用线搜索（无渐进 PGA）
    # ═══════════════════════════════════════════════════════════
    print("[4/5] 仅用线搜索（无渐进 PGA，peak0=初始PGA）")
    t0 = time.time()
    acc4, err4 = adjustspectra_stable(acc.copy(), n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl,
                                       tol=0.05, max_iter=50,
                                       target_peak=None,
                                       line_search=True,
                                       use_new_wavelet=True,
                                       damping=0.01,
                                       verbose=False)
    t4 = time.time()-t0
    pk4 = float(np.max(np.abs(acc4)))
    sa4 = compute_spectrum(acc4, dt, periods, zeta)
    e4 = (sa4-target_sa)/np.maximum(target_sa, 1e-30)
    aerror4 = float(np.sqrt(np.mean(e4*e4)))
    merror4 = float(np.max(np.abs(e4)))
    print(f"      PGA={pk4:.4f}g, aerror={aerror4:.2%}, merror={merror4:.2%}, time={t4:.1f}s")
    print()

    # ═══════════════════════════════════════════════════════════
    # 测试 5：不同 peak_ramp_fraction
    # ═══════════════════════════════════════════════════════════
    print("[5/5] 不同 peak_ramp_fraction 对比")
    for frac in [0.5, 0.7, 0.9, 1.0]:
        t0 = time.time()
        acc_f, err_f = adjustspectra_stable(acc.copy(), n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl,
                                             tol=0.05, max_iter=50,
                                             target_peak=PGA,
                                             peak_ramp_fraction=frac,
                                             line_search=True,
                                             use_new_wavelet=True,
                                             damping=0.01,
                                             verbose=False)
        tf = time.time()-t0
        pkf = float(np.max(np.abs(acc_f)))
        saf = compute_spectrum(acc_f, dt, periods, zeta)
        ef = (saf-target_sa)/np.maximum(target_sa, 1e-30)
        aerrorf = float(np.sqrt(np.mean(ef*ef)))
        status = "✅" if aerrorf < 0.20 else "❌"
        print(f"      fraction={frac:.1f}: PGA={pkf:.4f}g, aerror={aerrorf:.2%}, time={tf:.1f}s {status}")
    print()

    # ═══════════════════════════════════════════════════════════
    # 汇总
    # ═══════════════════════════════════════════════════════════
    print("=" * 70)
    print("结果汇总")
    print("=" * 70)
    results = [
        ("原始 adjustspectra", aerror1, pk1),
        ("稳定版（渐进PGA+线搜索）", aerror2, pk2),
        ("仅用渐进 PGA", aerror3, pk3),
        ("仅用线搜索", aerror4, pk4),
    ]
    for name, ae, pk in results:
        status = "✅" if ae < 0.20 else "❌"
        print(f"{status} {name}: aerror={ae:.2%}, PGA={pk:.4f}g")
    print()
    print("关键结论：")
    print("- 原始 adjustspectra 保持低 PGA（peak0=初始值），无法达到目标 PGA")
    print("- 内嵌渐进 PGA 允许峰值在迭代中平滑提升")
    print("- 线搜索确保每次迭代误差下降，防止震荡发散")
    print("- 单一算法完成，无需切换到其他方法")
    print("=" * 70)
