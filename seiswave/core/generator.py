"""
人工地震波生成模块

谱匹配算法（基于 EQSignal fitspectra / adjustspectra + initArtWave）：
1. initArtWave: 从目标反应谱估计功率谱，生成初始信号
2. adjustspectra (fm=1, 默认): 时域小波叠加 + 最小二乘迭代
   a. 计算反应谱 SPA（Newmark-β 带子步插值，C 加速）
   b. 构造小波函数 W_i（Gaussian-modulated cosine）
   c. 计算响应矩阵 M_ij = ra(W_j, P_i) / SPAT_i
   d. 最小二乘求解 dR，叠加 a += sum(dR_i * W_i)
3. fitspectra (fm=0, 备选): 频域迭代调整
   a. ratio = target / |SPA|，递减线性插值到 FFT 频率
   b. rsimple 符号修正
   c. af *= ratio（累积频域调整）
   d. IFFT → adjustpeak → 重新计算反应谱
4. 多 trial 取最优迭代结果

参考：EQSignal (Panchatantra/EQSignal) eqs.f90
"""

import numpy as np
import ctypes
import os
from typing import Optional, Callable

# ── 加载 C 加速库 ──
_c_lib = None
_c_lib_path = os.path.join(os.path.dirname(__file__), '_newmark.so')
if os.path.exists(_c_lib_path):
    try:
        _c_lib = ctypes.CDLL(_c_lib_path)
        _c_lib.newmark_spectrum.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.c_int,
            ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.c_int,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int),
        ]
        _c_lib.newmark_spectrum.restype = None
    except OSError:
        _c_lib = None


class WaveGenerator:
    """人工地震波生成器"""

    MPR = 20  # 短/长周期分界：T < MPR*dt 用频域法

    @staticmethod
    def generate(target_spectrum: np.ndarray, periods: np.ndarray,
                 n: int = 4096, dt: float = 0.02, zeta: float = 0.05,
                 pga: float = 1.0, tol: float = 0.05, max_iter: int = 50,
                 fm: int = 1,
                 progress_callback: Optional[Callable] = None):
        """基于目标反应谱迭代生成人工地震波

        Parameters
        ----------
        target_spectrum : np.ndarray
            目标反应谱值（Sa，单位与 pga 一致，通常为 g）
        periods : np.ndarray
            周期数组 (s)，递增排列
        pga : float
            目标 PGA (g)
        tol : float
            收敛容差（均方根相对偏差）
        max_iter : int
            最大迭代次数
        fm : int
            谱匹配方法：0=频域法(fitspectra)，1=时域法(adjustspectra，默认)
        progress_callback : callable, optional
            进度回调 fn(iteration, max_error, mean_error)
        """
        from .signal import EQSignal as EQSig
        from .fortran_bridge import HAS_FORTRAN

        target_spectrum = np.asarray(target_spectrum, dtype=np.float64)
        periods = np.asarray(periods, dtype=np.float64)

        valid = periods > 0
        ctrl_periods = periods[valid]
        ctrl_target = target_spectrum[valid].copy()
        nP_orig = len(ctrl_periods)

        peak0 = pga

        # ── Fortran 快速路径 ──
        if HAS_FORTRAN:
            return WaveGenerator._generate_fortran(
                ctrl_periods, ctrl_target, nP_orig, n, dt, zeta, peak0,
                tol, max_iter, fm, progress_callback)

        # ── Python 回退路径 ──
        return WaveGenerator._generate_python(
            ctrl_periods, ctrl_target, nP_orig, n, dt, zeta, peak0,
            tol, max_iter, fm, progress_callback)

    @staticmethod
    def _generate_fortran(ctrl_periods, ctrl_target, nP_orig, n, dt, zeta,
                          peak0, tol, max_iter, fm, progress_callback):
        """Fortran 加速生成路径

        优化策略（参考 EQSignal 原始项目）：
        - 控制点降采样到 ≤50 个（对数分布），避免 O(nP²) 爆炸
        - 直接调用 fitspectrum 总入口，不在 Python 层重复扩展谱
        - 不预缩放 PGA，让 Fortran 内部 adjustpeak 处理
        """
        from .signal import EQSignal as EQSig
        from .fortran_bridge import _eqs, spectrum_mixed

        MAX_CTRL = 50  # adjustspectra 的 O(nP²) 限制

        # 降采样控制点（对数分布）
        if nP_orig > MAX_CTRL:
            idx = np.unique(np.round(np.linspace(0, nP_orig - 1, MAX_CTRL)).astype(int))
            P = np.ascontiguousarray(ctrl_periods[idx], dtype=np.float64)
            SPAT = np.ascontiguousarray(ctrl_target[idx], dtype=np.float64)
        else:
            P = np.ascontiguousarray(ctrl_periods, dtype=np.float64)
            SPAT = np.ascontiguousarray(ctrl_target, dtype=np.float64)

        n_trials = 3
        global_best_acc = None
        global_best_error = float('inf')

        for trial in range(n_trials):
            # 初始信号（Fortran initartwave 自动处理谱估计）
            acc = _eqs.eqs.initartwave(n, dt, zeta, P, SPAT)

            # 缩放初始波到目标 PGA（fitspectrum 内部 adjustpeak 会维持此值）
            pk = np.max(np.abs(acc[:n]))
            if pk > 0 and peak0 > 0:
                acc = acc * (peak0 / pk)

            # 直接调用 fitspectrum（内部处理扩展谱 + 迭代 + adjustpeak）
            acc = _eqs.eqs.fitspectrum(acc, dt, zeta, P, SPAT,
                                        tol, max_iter, fm, 1)

            # 计算误差（用原始完整控制点验证）
            spa, _ = spectrum_mixed(acc[:n], dt, zeta, ctrl_periods)
            e = (np.abs(spa) - ctrl_target) / np.maximum(ctrl_target, 1e-30)
            aerror = float(np.sqrt(np.mean(e * e)))

            if progress_callback:
                merror = float(np.max(np.abs(e)))
                progress_callback(max_iter * (trial + 1), merror, aerror)

            if aerror < global_best_error:
                global_best_error = aerror
                global_best_acc = acc[:n].copy()

        acc = global_best_acc if global_best_acc is not None else acc[:n]
        result = EQSig(acc, dt, name="artificial")
        result.a2vd()
        return result

    @staticmethod
    def _generate_python(ctrl_periods, ctrl_target, nP_orig, n, dt, zeta,
                         peak0, tol, max_iter, fm, progress_callback):
        """Python 回退生成路径"""
        from .signal import EQSignal as EQSig

        if fm == 0:
            # ── 频域法：扩展目标谱（两端各加一个点），复现 fitspectrum ──
            nP = nP_orig + 2
            P = np.empty(nP)
            P[0] = ctrl_periods[0] * 0.5
            P[1:nP_orig+1] = ctrl_periods
            P[nP_orig+1] = ctrl_periods[-1] * 1.5

            SPAT = np.empty(nP)
            SPAT[1:nP_orig+1] = ctrl_target
            if nP_orig >= 2:
                SPAT[0] = ctrl_target[0] - (ctrl_target[1] - ctrl_target[0]) / \
                          (ctrl_periods[1] - ctrl_periods[0]) * ctrl_periods[0] * 0.5
                SPAT[nP_orig+1] = ctrl_target[-1] + (ctrl_target[-1] - ctrl_target[-2]) / \
                                  (ctrl_periods[-1] - ctrl_periods[-2]) * ctrl_periods[-1] * 0.5
            else:
                SPAT[0] = ctrl_target[0]
                SPAT[nP_orig+1] = ctrl_target[0]
        else:
            # ── 时域法：直接使用原始周期 ──
            nP = nP_orig
            P = ctrl_periods
            SPAT = ctrl_target

        # ── 多 trial 取最优 ──
        n_trials = 3
        global_best_acc = None
        global_best_error = float('inf')

        for trial in range(n_trials):
            # 初始信号：从目标谱估计功率谱（复现 initArtWave）
            # initArtWave 需要扩展谱
            nP_ext = nP_orig + 2
            P_ext = np.empty(nP_ext)
            P_ext[0] = ctrl_periods[0] * 0.5
            P_ext[1:nP_orig+1] = ctrl_periods
            P_ext[nP_orig+1] = ctrl_periods[-1] * 1.5
            SPAT_ext = np.empty(nP_ext)
            SPAT_ext[1:nP_orig+1] = ctrl_target
            if nP_orig >= 2:
                SPAT_ext[0] = ctrl_target[0] - (ctrl_target[1] - ctrl_target[0]) / \
                              (ctrl_periods[1] - ctrl_periods[0]) * ctrl_periods[0] * 0.5
                SPAT_ext[nP_orig+1] = ctrl_target[-1] + (ctrl_target[-1] - ctrl_target[-2]) / \
                                      (ctrl_periods[-1] - ctrl_periods[-2]) * ctrl_periods[-1] * 0.5
            else:
                SPAT_ext[0] = ctrl_target[0]
                SPAT_ext[nP_orig+1] = ctrl_target[0]

            acc = WaveGenerator._init_art_wave(n, dt, zeta, P_ext, SPAT_ext,
                                                nP_ext, seed=trial * 37 + 13)
            # 缩放到目标 PGA
            pk = np.max(np.abs(acc))
            if pk > 0:
                acc *= peak0 / pk

            # 包络调制
            envelope = WaveGenerator._envelope(n, dt)
            acc *= envelope
            pk = np.max(np.abs(acc))
            if pk > 0:
                acc *= peak0 / pk

            # 谱匹配迭代
            if fm == 0:
                acc, best_aerror = WaveGenerator._fitspectra(
                    acc, n, dt, zeta, P, nP, SPAT, tol, max_iter, peak0,
                    progress_callback if trial == 0 else None
                )
            else:
                acc, best_aerror = WaveGenerator._adjustspectra(
                    acc, n, dt, zeta, P, nP, SPAT, tol, max_iter,
                    progress_callback if trial == 0 else None
                )

            if best_aerror < global_best_error:
                global_best_error = best_aerror
                global_best_acc = acc.copy()

        acc = global_best_acc if global_best_acc is not None else acc
        result = EQSig(acc[:n], dt, name="artificial")
        result.a2vd()
        return result

    @staticmethod
    def _init_art_wave(n, dt, zeta, P, SPT, nP, seed=42):
        """从目标反应谱估计功率谱并生成初始信号（复现 initArtWave）

        使用 Vanmarcke (1975) 近似将 Sa 转换为功率谱密度，
        然后用随机相位合成时域信号。
        """
        nfft = WaveGenerator._nextpow2(n)
        fs = 1.0 / dt
        df = fs / nfft
        TWO_PI = 2.0 * np.pi
        PI = np.pi

        # 频率轴（复现 EQSignal fftfreqs，全谱）
        f = np.zeros(nfft)
        f[1:nfft//2] = np.arange(1, nfft//2) * df
        f[nfft//2:] = np.arange(-(nfft//2), 0) * df

        # Pf: 周期数组（递减），对应 f[1:nfft//2]
        # EQSignal: Pf(1) = 100*Pf(2), Pf(2:Nfft/2) = 1/f(2:Nfft/2)
        # Fortran 1-based: Pf has Nfft/2 elements
        # f(1)=0, f(2)=df, ..., f(Nfft/2)=(Nfft/2-1)*df
        n_pf = nfft // 2
        Pf = np.zeros(n_pf)
        # Pf[1:n_pf] corresponds to Fortran Pf(2:Nfft/2) = 1/f(2:Nfft/2)
        # f[1]..f[nfft//2-1] in Python = f(2)..f(Nfft/2) in Fortran
        pos_f = f[1:nfft//2]  # nfft//2-1 elements
        Pf[1:n_pf] = 1.0 / pos_f
        Pf[0] = 100.0 * Pf[1] if n_pf > 1 else 1e6

        # 找频率范围（Pf 递减）
        IPf1 = WaveGenerator._decrfindfirst(Pf, P[-1])
        IPf2 = WaveGenerator._decrfindlast(Pf, P[0])
        NPf = IPf2 - IPf1 + 1

        # 插值目标谱到 FFT 频率（递减线性插值）
        SPTf = np.zeros(nfft // 2)
        SPTf[IPf1:IPf2+1] = WaveGenerator._decrlininterp_core(
            P, SPT[:int(nP)], Pf[IPf1:IPf2+1])

        # 构造频域信号
        rng = np.random.default_rng(seed=seed)
        af = np.zeros(nfft, dtype=complex)

        for k in range(IPf1, IPf2 + 1):
            phi = rng.uniform(0, TWO_PI)
            # Pf[k] = 1/f[k]，对应频率 f[k]（Fortran: Pf(k) -> f(k) -> af(k)）
            wk = TWO_PI * f[k]
            if abs(wk) < 1e-30:
                continue
            # Vanmarcke (1975) 功率谱密度估计
            log_arg = (-PI / wk / dt / n) * np.log(1.0 - 0.85)
            if log_arg > 0 and log_arg < 1:
                Saw = (zeta / PI / wk) * SPTf[k]**2 / np.log(1.0 / log_arg)
            else:
                Saw = (zeta / PI / wk) * SPTf[k]**2
            Saw = max(Saw, 0.0)
            Ak = 2.0 * np.sqrt(Saw * TWO_PI * fs * nfft / 2)
            # 正频率
            af[k] = Ak * (np.cos(phi) + 1j * np.sin(phi))
            # 负频率（共轭对称）
            af[nfft - k] = Ak * (np.cos(phi) - 1j * np.sin(phi))

        # IFFT (EQSignal: fftw_plan_dft_1d BACKWARD, then /Nfft)
        a0 = np.fft.ifft(af)
        a = np.real(a0[:n])

        return a

    @staticmethod
    def _nextpow2(n):
        """不小于 n 的 2 的整数次幂"""
        p = 1
        while p < n:
            p *= 2
        return p

    @staticmethod
    def _decrfindfirst(a, x):
        """找到递减数组 a 中第一个 <= x 的位置"""
        for i in range(len(a)):
            if a[i] <= x:
                return i
        return len(a) - 1

    @staticmethod
    def _decrfindlast(a, x):
        """找到递减数组 a 中最后一个 >= x 的位置"""
        for i in range(len(a) - 1, -1, -1):
            if a[i] >= x:
                return i
        return 0

    @staticmethod
    def _decrlininterp_core(x, y, xi):
        """递减线性插值（复现 decrlininterp）

        x, xi 均为递减数组。从 x 的最小端开始，逐段插值。
        """
        n = len(x)
        ni = len(xi)
        yi = np.zeros(ni)

        # 从最小值端开始（x[n-1] 是最小的）
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
        # 处理剩余点（外推）
        while j < ni:
            yi[j] = yp
            j += 1
        return yi

    @staticmethod
    def _rsimple(pe0, p0, phi, t, zeta):
        """SDOF 对单频激励的响应符号（复现 EQSignal rsimple）"""
        TWO_PI = 2.0 * np.pi
        we = TWO_PI / pe0
        w = TWO_PI / p0

        we2 = we * we
        w2 = w * w
        we3 = we2 * we
        w3 = w2 * w
        we4 = we3 * we
        w4 = w3 * w

        zeta2 = zeta * zeta
        zeta3 = zeta2 * zeta
        zeta4 = zeta3 * zeta

        sinphi = np.sin(phi)
        cosphi = np.cos(phi)

        denom = (8.0*w2*we2*zeta4
                 + (2.0*we4 - 12.0*w2*we2 + 2.0*w4)*zeta2
                 - 2.0*we4 + 4.0*w2*we2 - 2.0*w4)

        if abs(denom) < 1e-30:
            return np.cos(we * t + phi)

        wd_sq = 4.0*w2 - 4.0*w2*zeta2
        wd = np.sqrt(max(wd_sq, 0.0))

        exp_neg = np.exp(-w * zeta * t)
        exp_pos = np.exp(w * zeta * t)

        sin_wet = np.sin(we * t + phi)
        cos_wet = np.cos(we * t + phi)
        sin_wdt = np.sin(wd * t / 2.0)
        cos_wdt = np.cos(wd * t / 2.0)

        inner = ((4.0*w*we3*zeta - 4.0*w*we3*zeta3) * exp_pos * sin_wet
                 + ((2.0*we4 - 2.0*w2*we2)*zeta2 - 2.0*we4 + 2.0*w2*we2)
                 * exp_pos * cos_wet
                 + wd * (4.0*cosphi*w*we2*zeta3
                         + 2.0*sinphi*we3*zeta2
                         + (cosphi*w3 - 3.0*cosphi*w*we2)*zeta
                         - sinphi*we3 + sinphi*w2*we) * sin_wdt
                 + (8.0*cosphi*w2*we2*zeta4
                    + 4.0*sinphi*w*we3*zeta3
                    + (2.0*cosphi*w4 - 10.0*cosphi*w2*we2)*zeta2
                    - 4.0*sinphi*w*we3*zeta
                    + 2.0*cosphi*w2*we2 - 2.0*cosphi*w4) * cos_wdt)

        return cos_wet - exp_neg * inner / denom

    @staticmethod
    def _fitspectra(acc, n, dt, zeta, P, nP, SPAT, tol, max_iter, peak0,
                    progress_callback):
        """频域迭代谱匹配算法（精确复现 EQSignal fitspectra）

        关键：af 在迭代间累积调整，不重新 FFT。

        Returns (best_acc, best_aerror)
        """
        TWO_PI = 2.0 * np.pi
        nfft = WaveGenerator._nextpow2(n) * 4
        iNfft = 1.0 / nfft

        # 频率轴（复现 EQSignal fftfreqs，全谱）
        fs = 1.0 / dt
        df = fs / nfft
        f = np.zeros(nfft)
        f[1:nfft//2] = np.arange(1, nfft//2) * df
        f[nfft//2] = fs / 2.0  # Nyquist
        f[nfft//2+1:] = np.arange(-(nfft//2) + 1, 0) * df

        # Pf: 周期数组（递减）
        # EQSignal: Pf(2:Nfft/2) = 1/f(2:Nfft/2), Pf(1) = 2*Pf(2)
        # Fortran 1-based → Python 0-based
        n_pf = nfft // 2
        Pf = np.zeros(n_pf)
        pos_f = f[1:nfft//2]  # f[1]..f[nfft//2-1], nfft//2-1 elements
        Pf[1:n_pf] = 1.0 / pos_f
        Pf[0] = 2.0 * Pf[1] if n_pf > 1 else 1e6

        # 找频率范围
        IPf1 = WaveGenerator._decrfindfirst(Pf, P[nP - 1])
        IPf2 = WaveGenerator._decrfindlast(Pf, P[0])
        NPf = IPf2 - IPf1 + 1

        # 初始 FFT（使用 r2c 等效：只存正频率部分）
        a0 = np.zeros(nfft)
        a0[:n] = acc
        # 使用 rfft（等效于 FFTW r2c）
        af = np.fft.rfft(a0)
        # af 的索引：af[0]=DC, af[1]=f[1], ..., af[nfft//2]=Nyquist
        # Pf[k] 对应 af[k]（Fortran 中 Pf(k) 和 af(k) 共享索引）

        a = acc.copy()

        # 初始反应谱
        SPA, SPI = WaveGenerator._spamixed(a, dt, zeta, P, nP)
        aerror, merror = WaveGenerator._error(np.abs(SPA), SPAT, nP)

        if aerror <= tol and merror <= 3.0 * tol:
            return a, aerror

        R = SPAT / np.maximum(np.abs(SPA), 1e-30)
        Rf = np.ones(nfft // 2)
        Rf[IPf1:IPf2+1] = WaveGenerator._decrlininterp_core(
            P, R[:int(nP)], Pf[IPf1:IPf2+1])

        minerr = aerror
        best = a.copy()

        iteration = 1
        while (aerror > tol or merror > 3.0 * tol) and iteration <= max_iter:
            # ── rsimple 符号修正（复现 EQSignal fitspectra）──
            j = IPf2
            for i in range(1, nP - 1):
                p0 = P[i]
                t_peak = dt * SPI[i] - dt
                dp = min(p0 - P[i - 1], P[i + 1] - p0)

                while Pf[j] < p0 + 0.5 * dp and j > IPf1:
                    pe0 = Pf[j]
                    # Pf[j] 对应 af[j]
                    phi = np.arctan2(np.imag(af[j]), np.real(af[j]))
                    ra = WaveGenerator._rsimple(pe0, p0, phi, t_peak, zeta)
                    if np.sign(ra) * np.sign(SPA[i]) < 0.0:
                        Rf[j] = 1.0 / Rf[j]
                    j -= 1

            # ── 频域调整（累积在 af 上）──
            af[IPf1:IPf2+1] *= Rf[IPf1:IPf2+1]

            # ── IFFT ──
            a0 = np.fft.irfft(af, nfft)
            a = a0[:n] * 1.0  # rfft/irfft 已归一化

            # ── adjustpeak ──
            a = WaveGenerator._adjust_peak(a, peak0)

            # ── 重新计算反应谱 ──
            SPA, SPI = WaveGenerator._spamixed(a, dt, zeta, P, nP)
            aerror, merror = WaveGenerator._error(np.abs(SPA), SPAT, nP)

            # ── 更新 ratio 和插值（为下次迭代准备）──
            R = SPAT / np.maximum(np.abs(SPA), 1e-30)
            Rf = np.ones(nfft // 2)
            Rf[IPf1:IPf2+1] = WaveGenerator._decrlininterp_core(
                P, R[:int(nP)], Pf[IPf1:IPf2+1])

            if progress_callback:
                progress_callback(iteration, merror, aerror)

            if aerror < minerr:
                minerr = aerror
                best = a.copy()

            iteration += 1

        return best, minerr

    @staticmethod
    def _adjustspectra(acc, n, dt, zeta, P, nP, SPAT, tol, max_iter,
                       progress_callback):
        """时域小波叠加谱匹配算法（复现 EQSignal adjustspectra）

        通过在时域叠加 Gaussian-modulated cosine 小波函数，
        用最小二乘求解调整系数，逐步逼近目标谱。
        比频域法 (fitspectra) 更稳定。

        Returns (best_acc, best_aerror)
        """
        TWO_PI = 2.0 * np.pi
        peak0 = float(np.max(np.abs(acc)))
        a = acc.copy()

        SPA, SPI = WaveGenerator._spamixed(a, dt, zeta, P, nP)
        aerror, merror = WaveGenerator._errora(np.abs(SPA), SPAT, nP)

        if aerror <= tol and merror <= 3.0 * tol:
            return a, aerror

        minerr = aerror
        best = a.copy()
        iteration = 1

        # 预计算频域法所需常量
        nfft_freq = WaveGenerator._nextpow2(n) * 2
        nf = nfft_freq // 2 + 1
        fs = 1.0 / dt
        df_freq = fs / nfft_freq
        wj = np.zeros(nf)
        wj[1:] = TWO_PI * np.arange(1, nf) * df_freq
        wj2 = wj * wj

        # 预计算各周期的自然频率
        w0_arr = TWO_PI / P

        while (aerror > tol or merror > 3.0 * tol) and iteration <= max_iter:
            # dR = SPA * (SPAT/|SPA| - 1) / SPAT
            dR = SPA * (SPAT / np.maximum(np.abs(SPA), 1e-30) - 1.0) / \
                 np.maximum(SPAT, 1e-30)

            # 构造小波函数 W (n x nP)
            W = np.zeros((n, nP))
            for i in range(nP):
                W[:, i] = WaveGenerator._wfunc(n, dt, SPI[i], P[i], zeta)

            # 构造响应矩阵 M (nP x nP) — 全频域批量 FFT 优化
            # M 矩阵精度要求不高（最小二乘系数），全部用频域法
            M = np.zeros((nP, nP))
            spi_idx = SPI - 1  # 转为 0-based

            # 批量 FFT 所有小波
            W_padded = np.zeros((nP, nfft_freq))
            W_padded[:, :n] = W.T  # (nP, nfft_freq)
            Wf = np.fft.rfft(W_padded, axis=1)  # (nP, nf)

            # 预计算传递函数比值 H[i] = numer / denom，形状 (nf,)
            for i in range(nP):
                w0 = w0_arr[i]
                w0i2 = w0 * w0
                w0iwj = w0 * wj
                denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
                safe = np.abs(denom) > 1e-30
                H = np.ones(nf, dtype=complex)
                H[safe] = (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]
                # 应用传递函数到所有小波 (nP, nf)
                raf = Wf * H[np.newaxis, :]
                # 批量 IFFT
                ra_all = np.fft.irfft(raf, nfft_freq, axis=1)  # (nP, nfft_freq)
                si = spi_idx[i]
                if 0 <= si < n:
                    M[i, :] = ra_all[:, si] / max(SPAT[i], 1e-30)

            # 非对角元素衰减（向量化）
            diag_mask = np.eye(nP, dtype=bool)
            M[~diag_mask] *= 0.618

            # 最小二乘求解 M * dR_new = dR
            dR_solved, _, _, _ = np.linalg.lstsq(M, dR, rcond=None)

            # 叠加小波（向量化）
            a += W @ dR_solved

            # adjustpeak
            a = WaveGenerator._adjust_peak(a, peak0)

            # 重新计算反应谱
            SPA, SPI = WaveGenerator._spamixed(a, dt, zeta, P, nP)
            aerror, merror = WaveGenerator._errora(np.abs(SPA), SPAT, nP)

            if progress_callback:
                progress_callback(iteration, merror, aerror)

            if aerror < minerr:
                minerr = aerror
                best = a.copy()

            iteration += 1

        return best, minerr

    @staticmethod
    def _wfunc(n, dt, itm, P, zeta):
        """Gaussian-modulated cosine 小波函数（复现 EQSignal wfunc）

        Parameters
        ----------
        n : int
            信号长度
        dt : float
            时间步长
        itm : int
            峰值时刻索引（1-based）
        P : float
            目标周期
        zeta : float
            阻尼比
        """
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

    @staticmethod
    def _ramixed(acc, n, dt, zeta, P):
        """混合法计算单周期绝对加速度响应时程（复现 EQSignal ramixed）

        短周期用频域法，长周期用 Newmark-β 法。
        返回长度为 n 的响应时程数组。
        """
        threshold = WaveGenerator.MPR * dt
        if P < threshold:
            return WaveGenerator._rafreq(acc, n, dt, zeta, P)
        else:
            return WaveGenerator._ranmk(acc, n, dt, zeta, P)

    @staticmethod
    def _ramixed_batch(acc, n, dt, zeta, periods, nP):
        """批量计算所有周期的绝对加速度响应时程

        返回 (nP, n) 数组。频域周期共享一次 FFT。
        """
        TWO_PI = 2.0 * np.pi
        threshold = WaveGenerator.MPR * dt
        result = np.zeros((nP, n))

        # 分离短周期和长周期
        freq_idx = []
        time_idx = []
        for i in range(nP):
            if periods[i] < threshold:
                freq_idx.append(i)
            else:
                time_idx.append(i)

        # 频域法：共享一次 FFT
        if freq_idx:
            nfft = WaveGenerator._nextpow2(n) * 2
            a0 = np.zeros(nfft)
            a0[:n] = acc
            af = np.fft.rfft(a0)

            fs = 1.0 / dt
            df = fs / nfft
            w_arr = np.zeros(nfft // 2 + 1)
            w_arr[1:] = TWO_PI * np.arange(1, nfft // 2 + 1) * df
            wj2 = w_arr * w_arr
            IONE = 1j

            for i in freq_idx:
                w0 = TWO_PI / periods[i]
                w0i2 = w0 * w0
                w0iwj = w0 * w_arr
                denom = w0i2 - wj2 + 2.0 * zeta * w0iwj * IONE
                # 避免除零
                safe = np.abs(denom) > 1e-30
                raf = np.zeros(nfft // 2 + 1, dtype=complex)
                raf[safe] = af[safe] * (w0i2 + 2.0 * zeta * w0iwj[safe] * IONE) / denom[safe]
                raf[~safe] = af[~safe]
                ra = np.fft.irfft(raf, nfft)
                result[i, :] = ra[:n]

        # 时域法
        for i in time_idx:
            result[i, :] = WaveGenerator._ranmk(acc, n, dt, zeta, periods[i])

        return result

    @staticmethod
    def _rafreq(acc, n, dt, zeta, P):
        """频域法计算绝对加速度响应时程（复现 EQSignal rafreq）"""
        TWO_PI = 2.0 * np.pi
        nfft = WaveGenerator._nextpow2(n) * 2

        a0 = np.zeros(nfft)
        a0[:n] = acc
        af = np.fft.rfft(a0)

        fs = 1.0 / dt
        df = fs / nfft
        nf = nfft // 2 + 1
        wj = np.zeros(nf)
        wj[1:] = TWO_PI * np.arange(1, nf) * df
        wj2 = wj * wj

        w0 = TWO_PI / P
        w0i2 = w0 * w0
        w0iwj = w0 * wj

        denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
        safe = np.abs(denom) > 1e-30
        raf = af.copy()
        raf[safe] = af[safe] * (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]

        ra = np.fft.irfft(raf, nfft)
        return ra[:n]

    @staticmethod
    def _ranmk(acc, n, dt, zeta, P):
        """Newmark-β 法计算绝对加速度响应时程（复现 EQSignal ranmk）"""
        from .spectrum import Spectra
        ra_rel, rv, rd = Spectra._newmark_beta(acc, dt, P, zeta)
        # 绝对加速度 = 地面加速度 - 相对加速度
        abs_acc = np.zeros(n)
        nn = min(n, len(ra_rel))
        abs_acc[:nn] = -ra_rel[:nn] + acc[:nn]
        return abs_acc

    @staticmethod
    def _spafreq(acc, n, dt, zeta, periods, nP):
        """频域法反应谱（复现 EQSignal spafreq）

        用于短周期（T < MPR*dt），与频域迭代调整自洽。
        返回带符号的 SPA 和峰值位置 SPI（1-based）。
        向量化实现：传递函数计算无 Python 循环。
        """
        TWO_PI = 2.0 * np.pi
        nfft = WaveGenerator._nextpow2(n)

        # FFT
        a0 = np.zeros(nfft)
        a0[:n] = acc
        af = np.fft.rfft(a0)  # (nfft//2+1,)

        # 频率轴（角频率）
        fs = 1.0 / dt
        df = fs / nfft
        nf = nfft // 2 + 1
        wj = np.zeros(nf)
        wj[1:] = TWO_PI * np.arange(1, nf) * df
        wj2 = wj * wj

        spa = np.zeros(nP)
        spi = np.ones(nP, dtype=np.int32)

        # 向量化：对每个周期，批量计算传递函数
        w0_arr = TWO_PI / periods[:nP]  # (nP,)
        for i in range(nP):
            w0 = w0_arr[i]
            w0i2 = w0 * w0
            w0iwj = w0 * wj  # (nf,)
            denom = w0i2 - wj2 + 2.0j * zeta * w0iwj  # (nf,)
            safe = np.abs(denom) > 1e-30
            raf = af.copy()
            raf[safe] = af[safe] * (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]

            ra = np.fft.irfft(raf, nfft)
            ra_n = ra[:n]
            idx = np.argmax(np.abs(ra_n))
            spa[i] = ra_n[idx]
            spi[i] = idx + 1

        return spa, spi

    @staticmethod
    def _spamixed(acc, dt, zeta, periods, nP):
        """混合反应谱计算（复现 EQSignal spamixed）

        短周期（T < MPR*dt）用频域法（与频域迭代自洽），
        长周期用 Newmark-β 法（精度更高）。
        """
        n = len(acc)
        threshold = WaveGenerator.MPR * dt  # MPR=20

        # 找分界点：与 Fortran spamixed 一致，P(1:m) 包含第一个 >= threshold 的周期
        # Fortran: m=1; do while(P(m)<MPR*dt) m=m+1; spafreq(P(1:m))
        # 即 P(m) 是第一个 >= threshold 的，也归频域法处理
        m = 0
        while m < nP and periods[m] < threshold:
            m += 1
        # 包含第一个 >= threshold 的周期（如果存在）
        if m < nP:
            m += 1

        spa = np.zeros(nP, dtype=np.float64)
        spi = np.ones(nP, dtype=np.int32)

        # 短周期：频域法
        if m > 0:
            spa[:m], spi[:m] = WaveGenerator._spafreq(
                acc, n, dt, zeta, periods[:m], m)

        # 长周期：Newmark-β
        if m < nP:
            long_periods = periods[m:nP]
            n_long = nP - m

            acc_c = np.ascontiguousarray(acc, dtype=np.float64)
            long_p = np.ascontiguousarray(long_periods, dtype=np.float64)
            spa_long = np.zeros(n_long, dtype=np.float64)
            spi_long = np.zeros(n_long, dtype=np.int32)

            if _c_lib is not None:
                _c_lib.newmark_spectrum(
                    acc_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                    n, dt, zeta,
                    long_p.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                    n_long,
                    spa_long.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                    spi_long.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
                )
            else:
                from .spectrum import Spectra
                for i in range(n_long):
                    ra_rel, rv, rd = Spectra._newmark_beta(
                        acc_c, dt, long_periods[i], zeta)
                    abs_acc = -ra_rel + acc_c[:len(ra_rel)]
                    idx = np.argmax(np.abs(abs_acc))
                    spa_long[i] = abs_acc[idx]
                    spi_long[i] = idx + 1

            spa[m:nP] = spa_long
            spi[m:nP] = spi_long

        return spa, spi

    @staticmethod
    def _error(y, y0, n):
        """相对误差（复现 error）：跳过首尾，用于 fitspectra"""
        if n <= 2:
            e = np.where(np.abs(y0) > 1e-30, (y - y0) / y0, 0.0)
        else:
            e = (y[1:n-1] - y0[1:n-1]) / y0[1:n-1]
        aerror = float(np.sqrt(np.mean(e * e)))
        merror = float(np.max(np.abs(e)))
        return aerror, merror

    @staticmethod
    def _errora(y, y0, n):
        """相对误差（复现 errora）：包括所有元素，用于 adjustspectra"""
        e = (y[:n] - y0[:n]) / np.maximum(np.abs(y0[:n]), 1e-30)
        aerror = float(np.sqrt(np.mean(e * e)))
        merror = float(np.max(np.abs(e)))
        return aerror, merror

    @staticmethod
    def _adjust_peak(acc, peak0):
        """裁剪峰值（复现 EQSignal adjustpeak）"""
        result = acc.copy()
        pk = int(np.argmax(np.abs(result)))
        peak = result[pk]
        result = np.clip(result, -peak0, peak0)
        if abs(peak) < peak0:
            result[pk] = np.sign(peak) * peak0 if peak != 0 else peak0
        return result

    @staticmethod
    def _envelope(n, dt):
        """时域包络函数（Saragoni & Hart 型）"""
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

    @staticmethod
    def fit_error(actual, target):
        """计算拟合误差（复现 error，跳过首尾）"""
        n = len(target)
        if n <= 2:
            e = np.zeros(n)
            for i in range(n):
                if target[i] > 1e-30:
                    e[i] = (actual[i] - target[i]) / target[i]
        else:
            e = (actual[1:n-1] - target[1:n-1]) / target[1:n-1]
        e_max = float(np.max(np.abs(e))) if len(e) > 0 else 0.0
        e_mean = float(np.sqrt(np.mean(e ** 2))) if len(e) > 0 else 0.0
        return {'max_error': e_max, 'mean_error': e_mean}
