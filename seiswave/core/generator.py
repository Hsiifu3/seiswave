"""
人工地震波生成模块

移植 EQSignal C++ 的 fitSP 迭代谱拟合算法：
1. 生成初始白噪声，施加包络函数
2. 计算当前波的反应谱
3. 在频域调整振幅谱使反应谱逼近目标谱
4. 重复 2-3 直到收敛或达到最大迭代次数

参考：
- EQSignal C++: Spectra::fitSP(), fitspectrum()
- design.md: WaveGenerator 类设计
"""

import numpy as np
from typing import Optional, Callable


class WaveGenerator:
    """人工地震波生成器"""

    @staticmethod
    def generate(target_spectrum: np.ndarray, periods: np.ndarray,
                 n: int = 4096, dt: float = 0.02, zeta: float = 0.05,
                 pga: float = 1.0, tol: float = 0.05, max_iter: int = 50,
                 progress_callback: Optional[Callable] = None):
        """基于目标反应谱迭代生成人工地震波

        算法流程（移植自 EQSignal C++ fitSP）：
        1. 生成初始白噪声，施加包络函数
        2. 计算当前波的反应谱
        3. 在频域按 target/current 比值调整振幅谱
        4. 重复 2-3 直到收敛（最大偏差 ≤ tol）或达到最大迭代次数

        Parameters
        ----------
        target_spectrum : np.ndarray
            目标反应谱值（与 periods 对应的 Sa 值）
        periods : np.ndarray
            周期数组 (s)
        n : int
            输出波形点数
        dt : float
            时间步长 (s)
        zeta : float
            阻尼比
        pga : float
            目标 PGA
        tol : float
            收敛容差（最大相对偏差）
        max_iter : int
            最大迭代次数
        progress_callback : callable, optional
            进度回调 fn(iteration, max_error, mean_error)

        Returns
        -------
        EQSignal
            生成的人工地震波
        """
        from .signal import EQSignal
        from .spectrum import Spectra

        target_spectrum = np.asarray(target_spectrum, dtype=np.float64)
        periods = np.asarray(periods, dtype=np.float64)

        # Step 1: 生成初始白噪声 + 包络
        acc = np.random.randn(n)
        envelope = WaveGenerator._envelope(n, dt)
        acc *= envelope

        # 缩放到目标 PGA
        peak = np.max(np.abs(acc))
        if peak > 0:
            acc *= pga / peak

        nfft = 1 << int(np.ceil(np.log2(n)))

        # 构建周期到频率的映射（用于频域调整）
        freq_target = 1.0 / periods  # 目标频率点

        converged = False
        best_acc = acc.copy()
        best_error = float('inf')

        for iteration in range(max_iter):
            # Step 2: 计算当前波的反应谱
            sp = Spectra.compute(acc, dt, periods, zeta=zeta, method="newmark")
            current_sa = sp.sa

            # 计算误差
            errors = WaveGenerator.fit_error(current_sa, target_spectrum)
            max_err = errors['max_error']
            mean_err = errors['mean_error']

            if progress_callback:
                progress_callback(iteration + 1, max_err, mean_err)

            # 记录最优结果
            if max_err < best_error:
                best_error = max_err
                best_acc = acc.copy()

            # 检查收敛
            if max_err <= tol:
                converged = True
                break

            # Step 3: 频域调整
            acc = WaveGenerator._adjust_spectrum(
                acc, dt, periods, zeta, target_spectrum, current_sa, nfft
            )

            # 重新施加包络并缩放 PGA
            acc[:n] *= envelope
            peak = np.max(np.abs(acc[:n]))
            if peak > 0:
                acc[:n] *= pga / peak

        # 使用最优结果
        if not converged:
            acc = best_acc

        result = EQSignal(acc[:n], dt, name="artificial")
        result.a2vd()
        return result

    @staticmethod
    def _envelope(n: int, dt: float) -> np.ndarray:
        """时域包络函数（梯形包络）

        三段式：上升段（二次）→ 平稳段 → 衰减段（指数）

        Parameters
        ----------
        n : int
            数据点数
        dt : float
            时间步长

        Returns
        -------
        np.ndarray
            包络函数
        """
        t_total = (n - 1) * dt
        t_rise = t_total * 0.1     # 上升段 10%
        t_strong = t_total * 0.5   # 平稳段 50%
        t_decay = t_total - t_rise - t_strong  # 衰减段

        env = np.zeros(n)
        t = np.arange(n) * dt

        for i in range(n):
            ti = t[i]
            if ti <= t_rise:
                env[i] = (ti / t_rise) ** 2
            elif ti <= t_rise + t_strong:
                env[i] = 1.0
            else:
                decay_t = ti - t_rise - t_strong
                env[i] = np.exp(-3.0 * decay_t / t_decay)

        return env

    @staticmethod
    def _adjust_spectrum(acc: np.ndarray, dt: float,
                         periods: np.ndarray, zeta: float,
                         target: np.ndarray, current: np.ndarray,
                         nfft: int) -> np.ndarray:
        """频域谱调整

        对每个频率点，按 target_sa / current_sa 的比值调整振幅谱，
        保持相位不变。使用插值将周期点的调整比映射到所有频率。

        Parameters
        ----------
        acc : np.ndarray
            当前加速度时程
        dt : float
            时间步长
        periods : np.ndarray
            周期数组
        zeta : float
            阻尼比
        target : np.ndarray
            目标反应谱值
        current : np.ndarray
            当前反应谱值
        nfft : int
            FFT 点数

        Returns
        -------
        np.ndarray
            调整后的加速度时程
        """
        n = len(acc)

        # 计算调整比
        ratio = np.ones_like(target)
        for i in range(len(periods)):
            if current[i] > 1e-30:
                ratio[i] = target[i] / current[i]
            else:
                ratio[i] = 1.0

        # 限制单次调整幅度，避免振荡
        ratio = np.clip(ratio, 0.5, 2.0)

        # FFT
        acc_padded = np.zeros(nfft)
        acc_padded[:n] = acc
        af = np.fft.fft(acc_padded)

        # 频率数组
        freqs = np.fft.fftfreq(nfft, dt)
        freq_target = 1.0 / periods  # 周期对应的频率

        # 将调整比从周期点插值到所有频率点
        # 按频率排序
        sort_idx = np.argsort(freq_target)
        freq_sorted = freq_target[sort_idx]
        ratio_sorted = ratio[sort_idx]

        # 对正频率部分插值
        pos_mask = freqs > 0
        pos_freqs = np.abs(freqs[pos_mask])

        adjustment = np.interp(pos_freqs, freq_sorted, ratio_sorted,
                               left=ratio_sorted[0], right=ratio_sorted[-1])

        # 应用调整（保持相位）
        af_new = af.copy()
        pos_indices = np.where(pos_mask)[0]
        for idx, adj in zip(pos_indices, adjustment):
            af_new[idx] *= adj
            # 保持共轭对称
            conj_idx = nfft - idx
            if conj_idx < nfft:
                af_new[conj_idx] = np.conj(af_new[idx])

        # IFFT
        result = np.real(np.fft.ifft(af_new))[:n]
        return result

    @staticmethod
    def fit_error(actual: np.ndarray, target: np.ndarray) -> dict:
        """计算拟合误差

        同 EQSignal C++ Spectra::fitError()。

        Parameters
        ----------
        actual : np.ndarray
            实际反应谱值
        target : np.ndarray
            目标反应谱值

        Returns
        -------
        dict
            {
                'max_error': 最大相对偏差,
                'mean_error': 均方根相对偏差,
                'cv': 变异系数
            }
        """
        n = len(target)
        re = np.zeros(n)
        for i in range(n):
            if target[i] > 1e-30:
                re[i] = abs(actual[i] - target[i]) / target[i]

        e_max = float(np.max(re))
        e_mean = float(np.sqrt(np.mean(re ** 2)))

        # 变异系数
        r_mean = float(np.mean(re))
        if r_mean > 0:
            cv = float(np.sqrt(np.mean((re - r_mean) ** 2)) / r_mean)
        else:
            cv = 0.0

        return {
            'max_error': e_max,
            'mean_error': e_mean,
            'cv': cv,
        }
