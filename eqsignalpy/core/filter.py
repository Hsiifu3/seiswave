"""
滤波与基线校正模块

实现多项式去趋势（1~6阶）、双线性去趋势（移植 EQSignal C++ bilinearDetrend）、
Butterworth 带通/低通/高通滤波。

参考：
- EQSignal C++: eqs.h (bilinearDetrend, polydetrend)
- design.md: Filter 类设计
"""

import numpy as np
from scipy import signal


class Filter:
    """信号滤波与基线校正"""

    # ──────────────────── 去趋势 ────────────────────

    @staticmethod
    def detrend(acc: np.ndarray, dt: float, order: int = 2) -> np.ndarray:
        """多项式去趋势

        拟合 order 阶多项式并从信号中减去。

        Parameters
        ----------
        acc : np.ndarray
            加速度时程
        dt : float
            时间步长
        order : int
            多项式阶数 (1~6)

        Returns
        -------
        np.ndarray
            去趋势后的加速度
        """
        n = len(acc)
        t = np.arange(n) * dt
        coeffs = np.polyfit(t, acc, order)
        trend = np.polyval(coeffs, t)
        return acc - trend

    @staticmethod
    def bilinear_detrend(acc: np.ndarray) -> np.ndarray:
        """双线性去趋势

        移植自 EQSignal C++ bilinearDetrend：
        在所有可能的拐点位置搜索最优双线性拟合，
        使残差最小。

        Parameters
        ----------
        acc : np.ndarray
            加速度时程

        Returns
        -------
        np.ndarray
            去趋势后的加速度
        """
        a = acc.copy()
        n = len(a)
        if n < 3:
            return a

        err = np.zeros(n)

        # i=0: 单线性（从 a[0] 到 a[n-1]）
        slope2 = (a[n - 1] - a[0]) / (n - 1)
        baseline = a[0] + slope2 * np.arange(n)
        err[0] = np.sqrt(np.mean((baseline - a) ** 2))

        # 搜索最优拐点
        for i in range(1, n):
            slope1 = (a[i] - a[0]) / i if i > 0 else 0.0
            slope2_i = (a[n - 1] - a[i]) / (n - 1 - i) if i < n - 1 else 0.0

            e = 0.0
            for j in range(i):
                base = a[0] + slope1 * j
                e += (base - a[j]) ** 2
            for j in range(i, n):
                base = a[i] + slope2_i * (j - i)
                e += (base - a[j]) ** 2

            err[i] = np.sqrt(e / n)

        # 找最小误差的拐点
        I = int(np.argmin(err))

        # 减去双线性趋势
        a0 = a[0]
        ai = a[I]
        slope1 = (ai - a0) / I if I > 0 else 0.0
        slope2 = (a[n - 1] - ai) / (n - 1 - I) if I < n - 1 else 0.0

        result = a.copy()
        for j in range(I):
            result[j] -= a0 + slope1 * j
        for j in range(I, n):
            result[j] -= ai + slope2 * (j - I)

        return result

    # ──────────────────── 滤波 ────────────────────

    @staticmethod
    def butterworth(acc: np.ndarray, dt: float, ftype: str = 'bandpass',
                    order: int = 4, freqs=None) -> np.ndarray:
        """Butterworth 零相位滤波

        Parameters
        ----------
        acc : np.ndarray
            加速度时程
        dt : float
            时间步长
        ftype : str
            'bandpass', 'lowpass', 'highpass'
        order : int
            滤波器阶数
        freqs : float or tuple
            截止频率。bandpass 时为 (low, high)，
            lowpass/highpass 时为单个频率值

        Returns
        -------
        np.ndarray
            滤波后的加速度
        """
        nyq = 0.5 / dt

        if ftype == 'bandpass':
            if freqs is None:
                freqs = (0.1, 25.0)
            low, high = freqs
            wn = [low / nyq, high / nyq]
        elif ftype == 'lowpass':
            if freqs is None:
                freqs = 25.0
            freq = freqs if np.isscalar(freqs) else freqs[1]
            wn = freq / nyq
        elif ftype == 'highpass':
            if freqs is None:
                freqs = 0.1
            freq = freqs if np.isscalar(freqs) else freqs[0]
            wn = freq / nyq
        else:
            raise ValueError(f"未知的滤波类型: {ftype}")

        b, a = signal.butter(order, wn, btype=ftype)
        return signal.filtfilt(b, a, acc)

    @staticmethod
    def fft_filter(acc: np.ndarray, dt: float,
                   cutoff_low: float = 0.1,
                   cutoff_high: float = 25.0) -> np.ndarray:
        """频域带通滤波（矩形窗）

        Parameters
        ----------
        acc : np.ndarray
            加速度时程
        dt : float
            时间步长
        cutoff_low : float
            低截止频率 (Hz)
        cutoff_high : float
            高截止频率 (Hz)

        Returns
        -------
        np.ndarray
            滤波后的加速度
        """
        n = len(acc)
        fft_result = np.fft.fft(acc)
        freqs = np.fft.fftfreq(n, dt)

        mask = np.ones(n)
        mask[np.abs(freqs) < cutoff_low] = 0
        mask[np.abs(freqs) > cutoff_high] = 0

        return np.real(np.fft.ifft(fft_result * mask))
