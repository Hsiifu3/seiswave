"""
SeisWave 时域谱匹配算法升级原型
基于 Atik & Abrahamson (2010) 改进锥形余弦小波 + Levenberg-Marquardt 优化框架

参考文献:
Atik, L. A., & Abrahamson, N. A. (2010). An improved method for nonstationary
spectral matching. Earthquake Spectra, 26(3), 693-707.

Abrahamson, N. A. (1998). Non-stationary spectral matching. Seismological
Research Letters, 69(4), 336-336.
"""

import numpy as np
from numpy.fft import rfft, irfft, fft, ifft
from scipy.optimize import least_squares
import logging

logger = logging.getLogger(__name__)

# ── 导入现有模块做对比 ──
try:
    from .spectrum import Spectra
    from .generator import WaveGenerator
    from .code_spec import CodeSpectrum
except ImportError:
    # 支持独立运行（直接运行本文件做测试）
    import sys
    sys.path.insert(0, '/Users/yachiyo/Developer/seiswave/seiswave/core')
    from spectrum import Spectra
    from generator import WaveGenerator
    from code_spec import CodeSpectrum


# ═══════════════════════════════════════════════════════════
# Phase 1: Atik & Abrahamson (2010) 改进小波基
# ═══════════════════════════════════════════════════════════

class AtikAbrahamsonWavelet:
    """
    Atik & Abrahamson (2010) 解析锥形余弦小波。

    相比传统 Gaussian-modulated cosine (_wfunc) 的改进：
    1. 解析形式，避免数值积分误差
    2. 内置基线修正，速度/位移末端归零
    3. 锥形(tapered)边界处理，频域泄漏更小
    4. 频域局部化更好，减少小波间干扰

    数学形式:
        w(t) = A · exp(-α|t-tp|) · cos(ωd(t-tp) + φ) · taper(t)

    其中基线修正相位 φ 和锥形 taper(t) 确保零漂移。
    """

    @staticmethod
    def wavelet(n, dt, itm, T, zeta, taper_cycles=3.0):
        """
        生成单个小波时程。

        Parameters
        ----------
        n : int
            信号长度
        dt : float
            时间步长
        itm : int
            峰值时刻索引（1-based，与 _wfunc 一致）
        T : float
            目标周期
        zeta : float
            阻尼比
        taper_cycles : float
            锥形宽度（周期数），默认 3T

        Returns
        -------
        np.ndarray
            小波时程 w(t)，长度 n
        """
        TWO_PI = 2.0 * np.pi
        tp = (itm - 1) * dt
        omega = TWO_PI / T
        omega_d = omega * np.sqrt(1.0 - zeta**2)

        # 衰减系数（与 _wfunc 的 gamma 不同，这里是指数衰减）
        # alpha = zeta * omega / sqrt(1-zeta^2) = zeta*omega_n / omega_d
        if abs(zeta) < 0.999 and abs(1.0 - zeta**2) > 1e-30:
            alpha = zeta * omega / np.sqrt(1.0 - zeta**2)
        else:
            alpha = zeta * omega

        t = np.arange(n) * dt

        # 关键修正：deltaT 偏移补偿 SDOF 相位滞后
        # 使小波峰值与 SDOF 响应峰值对齐（与旧小波 _wfunc 一致）
        deltaT = np.arctan(np.sqrt(1.0 - zeta**2) / zeta) / (omega * np.sqrt(1.0 - zeta**2)) if abs(omega * np.sqrt(1.0 - zeta**2)) > 1e-30 else 0.0
        tau = t - tp + deltaT

        # ── 1. 基础指数衰减余弦 ──
        w_base = np.cos(omega_d * tau) * np.exp(-alpha * np.abs(tau))

        # ── 2. 锥形处理（taper）──
        # 使用 Hann/cosine taper，在小波有效宽度外平滑衰减到零
        # taper_cycles * T 是小波有效宽度
        taper_width = taper_cycles * T
        taper = AtikAbrahamsonWavelet._cosine_taper(tau, taper_width)

        w_tapered = w_base * taper

        # ── 3. 解析基线修正 ──
        # 强制满足：∫w dt = 0（速度末端归零）
        #            ∫∫w dt dt = 0（位移末端归零）
        # 用线性修正 w_corrected = w - c0 - c1*t
        w_corrected = AtikAbrahamsonWavelet._baseline_correction(
            w_tapered, dt, n, order=2
        )

        # ── 4. 归一化 ──
        # 使小波峰值=1（与 _wfunc 一致，便于系数直接对应 PGA 调整量）
        peak = np.max(np.abs(w_corrected))
        if peak > 1e-30:
            w_corrected /= peak

        return w_corrected

    @staticmethod
    def _cosine_taper(tau, width):
        """
        Cosine taper 窗函数。

        Parameters
        ----------
        tau : np.ndarray
            相对峰值时间数组
        width : float
            半宽度（taper 从 |tau|=width 处开始衰减）

        Returns
        -------
        np.ndarray
            taper 值，范围 [0, 1]
        """
        taper = np.ones_like(tau, dtype=np.float64)

        # 过渡区：width 到 2*width 之间用 cosine 衰减
        w2 = 2.0 * width
        mask_rise = (np.abs(tau) > width) & (np.abs(tau) <= w2)
        mask_zero = np.abs(tau) > w2

        if np.any(mask_rise):
            # cosine 过渡: 1 -> 0
            x = (np.abs(tau[mask_rise]) - width) / width  # 0 -> 1
            taper[mask_rise] = 0.5 * (1.0 + np.cos(np.pi * x))

        taper[mask_zero] = 0.0

        return taper

    @staticmethod
    def _baseline_correction(w, dt, n, order=2):
        """
        多项式基线修正。

        通过最小二乘拟合低阶多项式，强制满足速度/位移末端归零。
        order=1: 线性修正（强制速度末端归零）
        order=2: 二次修正（强制速度和位移末端归零）

        Parameters
        ----------
        w : np.ndarray
            原始小波
        dt : float
            时间步长
        n : int
            信号长度
        order : int
            修正多项式阶数 (1 or 2)

        Returns
        -------
        np.ndarray
            修正后的小波
        """
        t = np.arange(n) * dt

        if order == 1:
            # 一阶修正: w_corr = w - c0
            # 约束: ∫w_corr dt = 0  =>  c0 = mean(w) * (n*dt) / (n*dt) = mean(w) 不太对
            # 实际上用积分约束: sum(w)*dt = 0 => 减去均值
            c0 = np.mean(w)
            return w - c0

        elif order == 2:
            # 二阶修正: w_corr = w - (c0 + c1*t)
            # 约束:
            #   (1) ∫w_corr dt = 0     =>  sum(w - c0 - c1*t)*dt = 0
            #   (2) ∫∫w_corr dt dt = 0  =>  double integral = 0
            #
            # 数值实现：用累积和近似积分
            # v[n] = sum(w[0:n])*dt = 0 (末端速度)
            # d[n] = sum(v[0:n])*dt = 0 (末端位移)
            # 最小二乘求解 c0, c1 使得末端速度和位移最小

            # 构建约束矩阵
            # v_end = sum(w - c0 - c1*t)*dt = sum(w)*dt - c0*n*dt - c1*sum(t)*dt
            # d_end = sum(cumsum(w - c0 - c1*t)*dt)*dt
            #       = sum(cumsum(w)*dt)*dt - c0*sum(cumsum(1)*dt)*dt - c1*sum(cumsum(t)*dt)*dt

            v_raw = np.cumsum(w) * dt
            d_raw = np.cumsum(v_raw) * dt

            # 常数项和线性项的累积
            ones = np.ones(n)
            v_1 = np.cumsum(ones) * dt  # = t + dt
            d_1 = np.cumsum(v_1) * dt

            v_t = np.cumsum(t) * dt
            d_t = np.cumsum(v_t) * dt

            # 约束方程 A * [c0, c1]^T = b
            # 约束1: v_end = 0
            # 约束2: d_end = 0
            A = np.array([
                [v_1[-1], v_t[-1]],
                [d_1[-1], d_t[-1]]
            ])
            b = np.array([v_raw[-1], d_raw[-1]])

            # 求解
            try:
                coeffs = np.linalg.solve(A, b)
            except np.linalg.LinAlgError:
                # 矩阵奇异，回退到一阶修正
                coeffs = np.array([np.mean(w), 0.0])

            c0, c1 = coeffs
            return w - c0 - c1 * t

        else:
            raise ValueError(f"不支持的修正阶数: {order}")

    @staticmethod
    def wavelet_response(w, dt, T, zeta, method="mixed"):
        """
        计算单个小波在周期 T、阻尼 zeta 下的反应谱值。

        Parameters
        ----------
        w : np.ndarray
            小波时程
        dt : float
            时间步长
        T : float
            目标周期
        zeta : float
            阻尼比
        method : str
            响应计算方法: "newmark", "freq", "mixed"

        Returns
        -------
        float
            绝对加速度响应峰值（反应谱值）
        """
        n = len(w)
        threshold = 20.0 * dt

        if method == "mixed":
            if T < threshold:
                method = "freq"
            else:
                method = "newmark"

        if method == "newmark":
            ra_rel, rv, rd = Spectra._newmark_beta(w, dt, T, zeta)
            abs_acc = -ra_rel + w[:len(ra_rel)]
            return float(np.max(np.abs(abs_acc)))

        elif method == "freq":
            nfft = 1 << int(np.ceil(np.log2(n))) * 2
            a0 = np.zeros(nfft)
            a0[:n] = w
            wf = rfft(a0)

            fs = 1.0 / dt
            df = fs / nfft
            omega = 2.0 * np.pi / T
            wj = np.zeros(nfft // 2 + 1)
            wj[1:] = 2.0 * np.pi * np.arange(1, nfft // 2 + 1) * df
            wj2 = wj * wj
            omega2 = omega * omega
            omegawj = omega * wj

            denom = omega2 - wj2 + 2.0j * zeta * omegawj
            safe = np.abs(denom) > 1e-30
            raf = np.zeros(nfft // 2 + 1, dtype=complex)
            raf[safe] = wf[safe] * (omega2 + 2.0j * zeta * omegawj[safe]) / denom[safe]

            ra = irfft(raf, nfft)[:n]
            return float(np.max(np.abs(ra)))

        else:
            raise ValueError(f"未知方法: {method}")


# ═══════════════════════════════════════════════════════════
# Phase 2: Levenberg-Marquardt 优化框架
# ═══════════════════════════════════════════════════════════

class LMSpectralMatcher:
    """
    基于 Levenberg-Marquardt 的时域谱匹配优化器。

    将谱匹配形式化为非线性最小二乘问题：
        min ‖ S_a(T_i; a + Σ c_j·w_j) - S_target(T_i) ‖²_w

    决策变量：小波振幅系数 c_j
    约束：总振幅调整不超过原始信号的 K 倍
    """

    def __init__(self, acc, dt, zeta, periods, target_sa,
                 max_iter=50, K=2.0, n_wavelets=None,
                 use_atik_wavelet=True, taper_cycles=3.0,
                 progress_callback=None):
        """
        Parameters
        ----------
        acc : np.ndarray
            初始加速度时程
        dt : float
            时间步长
        zeta : float
            阻尼比
        periods : np.ndarray
            控制周期数组
        target_sa : np.ndarray
            目标反应谱
        max_iter : int
            最大迭代次数
        K : float
            振幅调整上限倍数
        n_wavelets : int or None
            小波数量（默认等于控制周期数）
        use_atik_wavelet : bool
            使用 Atik-Abrahamson 小波（True）或传统 _wfunc（False）
        taper_cycles : float
            Atik 小波锥形宽度
        progress_callback : callable or None
            进度回调函数(iteration, merror, aerror)
        """
        self.acc0 = np.asarray(acc, dtype=np.float64).copy()
        self.n = len(self.acc0)
        self.dt = float(dt)
        self.zeta = float(zeta)
        self.periods = np.asarray(periods, dtype=np.float64)
        self.target_sa = np.asarray(target_sa, dtype=np.float64)
        self.nP = len(self.periods)
        self.max_iter = max_iter
        self.K = K
        self.use_atik = use_atik_wavelet
        self.taper_cycles = taper_cycles
        self.progress_callback = progress_callback

        # 小波数量
        if n_wavelets is None:
            self.n_wavelets = self.nP
        else:
            self.n_wavelets = min(n_wavelets, self.nP)

        # 预计算小波（固定小波基，只优化系数）
        self.wavelets = self._precompute_wavelets()

        # 权重：短周期平台段权重更高
        self.weights = self._compute_weights()

        # 峰值约束
        self.peak0 = float(np.max(np.abs(self.acc0)))
        self.max_peak = self.peak0 * self.K

    def _precompute_wavelets(self):
        """预计算所有小波基函数。"""
        wavelets = []

        # 为每个控制周期生成一个小波
        # 峰值时刻：用当前 acc0 在该周期下的反应谱峰值时刻
        # 先用 acc0 粗略估算峰值时刻
        spa, spi = WaveGenerator._spamixed(self.acc0, self.dt, self.zeta,
                                            self.periods, self.nP)

        for i in range(self.n_wavelets):
            itm = int(spi[i])
            T = self.periods[i]

            if self.use_atik:
                w = AtikAbrahamsonWavelet.wavelet(
                    self.n, self.dt, itm, T, self.zeta,
                    taper_cycles=self.taper_cycles
                )
            else:
                w = WaveGenerator._wfunc(self.n, self.dt, itm, T, self.zeta)

            wavelets.append(w)

        return np.array(wavelets)  # (n_wavelets, n)

    def _compute_weights(self):
        """计算控制点权重：短周期平台段权重更高。"""
        weights = np.ones(self.nP, dtype=np.float64)

        # 找到平台段（谱值接近最大值的区域）
        max_sa = np.max(self.target_sa)
        if max_sa > 1e-30:
            plateau_threshold = 0.8 * max_sa
            plateau_mask = self.target_sa >= plateau_threshold
            weights[plateau_mask] *= 2.0  # 平台段权重翻倍

        # 短周期额外加权（T < 0.5s）
        short_mask = self.periods < 0.5
        weights[short_mask] *= 1.5

        return weights

    def _residual(self, coeffs, return_full=False):
        """
        计算残差向量。

        Parameters
        ----------
        coeffs : np.ndarray
            小波系数数组 (n_wavelets,)
        return_full : bool
            是否返回完整信息（用于雅可比近似）

        Returns
        -------
        np.ndarray or tuple
            残差向量 (nP,) 或 (残差, 当前加速度, 当前反应谱)
        """
        # 合成加速度
        delta_a = self.wavelets.T @ coeffs  # (n,)
        acc = self.acc0 + delta_a

        # 峰值约束（软约束：clip）
        acc = np.clip(acc, -self.max_peak, self.max_peak)

        # 计算反应谱
        spa, _ = WaveGenerator._spamixed(acc, self.dt, self.zeta,
                                           self.periods, self.nP)

        # 残差: (SPA_current - SPA_target) / SPA_target
        denom = np.maximum(np.abs(self.target_sa), 1e-30)
        residual = (np.abs(spa) - self.target_sa) / denom

        # 加权
        residual = residual * self.weights

        if return_full:
            return residual, acc, spa
        return residual

    def match(self, method='lm', verbose=False):
        """
        执行谱匹配优化。

        Parameters
        ----------
        method : str
            'lm' = Levenberg-Marquardt (scipy.optimize.least_squares)
            'trf' = Trust Region Reflective (带边界约束)
        verbose : bool
            是否打印迭代信息

        Returns
        -------
        np.ndarray
            匹配后的加速度时程
        dict
            结果信息 {'aerror': float, 'merror': float, 'niter': int}
        """
        x0 = np.zeros(self.n_wavelets, dtype=np.float64)

        # 边界约束：系数范围 [-peak0, peak0]
        # 即每个小波的调整量不超过原始峰值
        bounds = (-self.peak0, self.peak0)

        if method == 'lm':
            # LM 方法不支持边界，用 soft constraint 在 residual 中处理
            result = least_squares(
                self._residual,
                x0,
                method='lm',
                max_nfev=self.max_iter * self.nP,
                ftol=1e-6,
                xtol=1e-6,
                gtol=1e-6,
                verbose=2 if verbose else 0,
            )
        elif method == 'trf':
            result = least_squares(
                self._residual,
                x0,
                method='trf',
                bounds=bounds,
                max_nfev=self.max_iter * self.nP,
                ftol=1e-6,
                xtol=1e-6,
                gtol=1e-6,
                verbose=2 if verbose else 0,
            )
        else:
            raise ValueError(f"未知优化方法: {method}")

        # 最终合成
        _, acc_final, spa_final = self._residual(result.x, return_full=True)

        # 误差计算
        e = (np.abs(spa_final) - self.target_sa) / np.maximum(self.target_sa, 1e-30)
        aerror = float(np.sqrt(np.mean(e * e)))
        merror = float(np.max(np.abs(e)))

        info = {
            'aerror': aerror,
            'merror': merror,
            'niter': result.nfev,
            'success': result.success,
            'status': result.status,
        }

        return acc_final, info


# ═══════════════════════════════════════════════════════════
# 渐进 PGA 策略
# ═══════════════════════════════════════════════════════════

class ProgressivePGAMatcher:
    """
    渐进 PGA 谱匹配策略。

    分阶段匹配：0.5 → 0.75 → 1.0 倍目标 PGA
    每阶段以上一阶段结果为初始值，避免高 PGA 下发散。
    """

    def __init__(self, matcher_class=LMSpectralMatcher, **matcher_kwargs):
        self.matcher_class = matcher_class
        self.matcher_kwargs = matcher_kwargs

    def match(self, target_pga, acc0, stages=None, method='lm'):
        """
        渐进 PGA 匹配。

        Parameters
        ----------
        target_pga : float
            目标 PGA
        acc0 : np.ndarray
            初始信号（通常已包络调制但 PGA 较低）
        stages : list or None
            阶段比例，默认 [0.5, 0.75, 1.0]
        method : str
            优化方法

        Returns
        -------
        np.ndarray
            最终加速度时程
        list[dict]
            每阶段的结果信息
        """
        if stages is None:
            stages = [0.5, 0.75, 1.0]

        acc = np.asarray(acc0, dtype=np.float64).copy()
        results = []

        for stage_ratio in stages:
            stage_pga = target_pga * stage_ratio

            # 先缩放到当前阶段目标 PGA
            pk = np.max(np.abs(acc))
            if pk > 1e-30:
                acc = acc * (stage_pga / pk)

            # 创建匹配器（更新初始信号）
            kwargs = self.matcher_kwargs.copy()
            kwargs['acc'] = acc
            matcher = self.matcher_class(**kwargs)

            # 执行匹配
            acc, info = matcher.match(method=method)
            info['stage_ratio'] = stage_ratio
            info['stage_pga'] = stage_pga
            results.append(info)

            if not info['success']:
                logger.warning(f"阶段 {stage_ratio} 优化未收敛: status={info['status']}")

        return acc, results


# ═══════════════════════════════════════════════════════════
# 验证与测试工具
# ═══════════════════════════════════════════════════════════

class WaveletValidator:
    """小波验证工具：频域对比、基线漂移检测。"""

    @staticmethod
    def compare_wavelets(n, dt, itm, T, zeta):
        """
        对比传统 _wfunc 和 Atik-Abrahamson 小波。

        Returns
        -------
        dict
            对比结果
        """
        w_old = WaveGenerator._wfunc(n, dt, itm, T, zeta)
        w_new = AtikAbrahamsonWavelet.wavelet(n, dt, itm, T, zeta)

        # 1. 时域对比
        t = np.arange(n) * dt

        # 2. 频域对比（FFT 幅值谱）
        nfft = (1 << int(np.ceil(np.log2(n)))) * 4
        f_old = rfft(w_old, n=nfft)
        f_new = rfft(w_new, n=nfft)

        freq = np.fft.rfftfreq(nfft, dt)

        # 3. 基线漂移检测
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

        drift_old = check_drift(w_old, dt)
        drift_new = check_drift(w_new, dt)

        # 4. 频域集中度（能量集中在目标周期附近的程度）
        f_target = 1.0 / T
        def spectral_concentration(freq, amp, f_target, bandwidth=0.2):
            """计算目标频率附近能量占比。"""
            total_energy = np.sum(amp**2)
            mask = np.abs(freq - f_target) < bandwidth * f_target
            band_energy = np.sum(amp[mask]**2)
            return float(band_energy / (total_energy + 1e-30))

        conc_old = spectral_concentration(freq, np.abs(f_old), f_target)
        conc_new = spectral_concentration(freq, np.abs(f_new), f_target)

        return {
            'T': T,
            'zeta': zeta,
            'drift_old': drift_old,
            'drift_new': drift_new,
            'spectral_concentration_old': conc_old,
            'spectral_concentration_new': conc_new,
        }

    @staticmethod
    def run_suite(n=2000, dt=0.02, zeta=0.05):
        """运行完整验证套件。"""
        results = []
        test_periods = [0.1, 0.2, 0.5, 1.0, 2.0, 3.0]

        for T in test_periods:
            itm = n // 2  # 峰值在信号中间
            result = WaveletValidator.compare_wavelets(n, dt, itm, T, zeta)
            results.append(result)

        return results


# ═══════════════════════════════════════════════════════════
# GB50011 规范谱测试
# ═══════════════════════════════════════════════════════════

def test_gb50011_prototype(Tg=0.2, alpha_max=0.16, PGA=0.16,
                           n=2000, dt=0.02, zeta=0.05,
                           n_periods=300, use_atik=True,
                           use_lm=True, progressive=True):
    """
    用 GB50011 规范谱测试原型算法。

    Parameters
    ----------
    Tg, alpha_max, PGA : float
        规范谱参数
    n, dt, zeta : int/float
        信号参数
    n_periods : int
        控制周期点数
    use_atik : bool
        使用 Atik 小波
    use_lm : bool
        使用 LM 优化（False 则使用传统 adjustspectra）
    progressive : bool
        使用渐进 PGA 策略

    Returns
    -------
    dict
        测试结果
    """
    # 1. 生成目标谱
    periods = CodeSpectrum.default_periods(0.04, 6.0, n_periods, mode="mixed")
    target_sa = CodeSpectrum.gb50011(periods, Tg, alpha_max, zeta=zeta)

    # 2. 生成初始信号（initArtWave + 包络）
    nP_ext = n_periods + 2
    P_ext = np.empty(nP_ext)
    P_ext[0] = periods[0] * 0.5
    P_ext[1:n_periods+1] = periods
    P_ext[n_periods+1] = periods[-1] * 1.5
    SPAT_ext = np.empty(nP_ext)
    SPAT_ext[1:n_periods+1] = target_sa
    SPAT_ext[0] = target_sa[0] - (target_sa[1] - target_sa[0]) / \
                  (periods[1] - periods[0]) * periods[0] * 0.5
    SPAT_ext[n_periods+1] = target_sa[-1] + (target_sa[-1] - target_sa[-2]) / \
                            (periods[-1] - periods[-2]) * periods[-1] * 1.5

    acc = WaveGenerator._init_art_wave(n, dt, zeta, P_ext, SPAT_ext, nP_ext, seed=42)
    envelope = WaveGenerator._envelope(n, dt)
    acc *= envelope

    # 记录包络后状态
    pk_envelope = float(np.max(np.abs(acc)))
    spec_envelope = Spectra.compute(acc, dt, periods, zeta=zeta, method="mixed")
    e_env = (np.abs(spec_envelope.sa) - target_sa) / np.maximum(target_sa, 1e-30)
    aerror_envelope = float(np.sqrt(np.mean(e_env * e_env)))

    # 3. 执行匹配
    if use_lm:
        if progressive:
            # 渐进 PGA
            matcher = ProgressivePGAMatcher(
                LMSpectralMatcher,
                dt=dt, zeta=zeta, periods=periods, target_sa=target_sa,
                max_iter=30, K=2.0, use_atik_wavelet=use_atik
            )
            acc_final, stage_results = matcher.match(
                target_pga=PGA, acc0=acc, stages=[0.5, 0.75, 1.0], method='lm'
            )
        else:
            # 直接匹配到目标 PGA
            pk = np.max(np.abs(acc))
            if pk > 1e-30:
                acc = acc * (PGA / pk)
            matcher = LMSpectralMatcher(
                acc, dt, zeta, periods, target_sa,
                max_iter=50, K=2.0, use_atik_wavelet=use_atik
            )
            acc_final, info = matcher.match(method='lm')
            stage_results = [info]
    else:
        # 传统方法对比
        P_ctrl, SPAT_ctrl = WaveGenerator._downsample_control_points(periods, target_sa, max_ctrl=50)
        nP_ctrl = len(P_ctrl)
        acc_final, _ = WaveGenerator._adjustspectra(
            acc, n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl,
            tol=0.05, max_iter=50, progress_callback=None
        )
        stage_results = []

    # 4. 最终验证
    pk_final = float(np.max(np.abs(acc_final)))
    spec_final = Spectra.compute(acc_final, dt, periods, zeta=zeta, method="mixed")
    e_final = (np.abs(spec_final.sa) - target_sa) / np.maximum(target_sa, 1e-30)
    aerror_final = float(np.sqrt(np.mean(e_final * e_final)))
    merror_final = float(np.max(np.abs(e_final)))

    return {
        'Tg': Tg,
        'alpha_max': alpha_max,
        'PGA_target': PGA,
        'PGA_envelope': pk_envelope,
        'PGA_final': pk_final,
        'aerror_envelope': aerror_envelope,
        'aerror_final': aerror_final,
        'merror_final': merror_final,
        'use_atik': use_atik,
        'use_lm': use_lm,
        'progressive': progressive,
        'stage_results': stage_results,
        'acc_final': acc_final,
        'spec_final': spec_final.sa,
        'target_sa': target_sa,
        'periods': periods,
    }


# ═══════════════════════════════════════════════════════════
# 主测试入口
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("SeisWave 时域谱匹配算法升级原型 - 验证测试")
    print("=" * 60)

    # ── Phase 1: 小波验证 ──
    print("\n### Phase 1: 小波基对比验证 ###\n")
    validator = WaveletValidator()
    wavelet_results = validator.run_suite(n=2000, dt=0.02, zeta=0.05)

    for r in wavelet_results:
        print(f"T={r['T']:.2f}s, zeta={r['zeta']:.2f}")
        print(f"  旧小波 - 速度末端漂移: {r['drift_old']['v_end']:.6f} "
              f"(ratio={r['drift_old']['v_end_ratio']:.4f})")
        print(f"  旧小波 - 位移末端漂移: {r['drift_old']['d_end']:.6f} "
              f"(ratio={r['drift_old']['d_end_ratio']:.4f})")
        print(f"  新小波 - 速度末端漂移: {r['drift_new']['v_end']:.6f} "
              f"(ratio={r['drift_new']['v_end_ratio']:.4f})")
        print(f"  新小波 - 位移末端漂移: {r['drift_new']['d_end']:.6f} "
              f"(ratio={r['drift_new']['d_end_ratio']:.4f})")
        print(f"  频域集中度: 旧={r['spectral_concentration_old']:.4f}, "
              f"新={r['spectral_concentration_new']:.4f}")
        print()

    # ── Phase 2: 谱匹配验证 ──
    print("\n### Phase 2: GB50011 规范谱匹配验证 ###\n")

    # 测试配置
    test_cases = [
        {'name': '传统小波+传统迭代', 'use_atik': False, 'use_lm': False, 'progressive': False},
        {'name': 'Atik小波+传统迭代', 'use_atik': True, 'use_lm': False, 'progressive': False},
        {'name': 'Atik小波+LM优化', 'use_atik': True, 'use_lm': True, 'progressive': False},
        {'name': 'Atik小波+LM+渐进PGA', 'use_atik': True, 'use_lm': True, 'progressive': True},
    ]

    all_results = []
    for case in test_cases:
        print(f"--- 测试: {case['name']} ---")
        try:
            result = test_gb50011_prototype(
                Tg=0.2, alpha_max=0.16, PGA=0.16,
                n=2000, dt=0.02, zeta=0.05,
                use_atik=case['use_atik'],
                use_lm=case['use_lm'],
                progressive=case['progressive']
            )
            print(f"  包络后 PGA: {result['PGA_envelope']:.4f}g, aerror: {result['aerror_envelope']:.2%}")
            print(f"  最终 PGA: {result['PGA_final']:.4f}g")
            print(f"  最终 mean_error: {result['aerror_final']:.2%}")
            print(f"  最终 max_error: {result['merror_final']:.2%}")
            if result['stage_results']:
                for sr in result['stage_results']:
                    if 'stage_ratio' in sr:
                        print(f"    阶段 {sr['stage_ratio']}: aerror={sr['aerror']:.2%}, "
                              f"success={sr['success']}, niter={sr['niter']}")
            all_results.append({**case, **result})
        except Exception as e:
            print(f"  错误: {e}")
            import traceback
            traceback.print_exc()
            all_results.append({**case, 'error': str(e)})
        print()

    # 保存结果摘要
    summary = []
    for r in all_results:
        if 'error' in r:
            summary.append({
                'name': r['name'],
                'error': r['error'],
            })
        else:
            summary.append({
                'name': r['name'],
                'PGA_envelope': r['PGA_envelope'],
                'PGA_final': r['PGA_final'],
                'aerror_envelope': r['aerror_envelope'],
                'aerror_final': r['aerror_final'],
                'merror_final': r['merror_final'],
            })

    print("\n### 结果摘要 ###")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    print("\n" + "=" * 60)
    print("验证完成")
    print("=" * 60)
