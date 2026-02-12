"""
FFT / PSD 模块

傅里叶振幅谱和 Welch 功率谱密度。

参考：
- EQSignal C++: EQSignal::calcFFT(), EQSignal::calcPSD()
- design.md: fft.py 设计
"""

import numpy as np
from scipy import signal


class FFT:
    """频域分析工具"""

    @staticmethod
    def amplitude_spectrum(acc: np.ndarray, dt: float) -> tuple:
        """计算傅里叶振幅谱

        同 EQSignal C++ calcFFT()：
        - 零填充到 2 的幂次
        - 振幅 = 2 * |FFT| / N（单边谱）

        Parameters
        ----------
        acc : np.ndarray
            加速度时程
        dt : float
            时间步长 (s)

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (频率数组 Hz, 振幅谱)
        """
        n = len(acc)
        nfft = 1 << int(np.ceil(np.log2(n)))  # next power of 2

        # 零填充 FFT
        af = np.fft.fft(acc, nfft)

        # 单边振幅谱
        n_half = nfft // 2 + 1
        fn = 0.5 / dt  # Nyquist frequency
        freqs = np.linspace(0.0, fn, n_half)
        ampf = 2.0 * np.abs(af[:n_half]) / nfft

        return freqs, ampf

    @staticmethod
    def welch_psd(acc: np.ndarray, dt: float,
                  overlap: float = 0.5,
                  window: bool = True) -> tuple:
        """Welch 功率谱密度

        Parameters
        ----------
        acc : np.ndarray
            加速度时程
        dt : float
            时间步长 (s)
        overlap : float
            重叠比例 (0~1)
        window : bool
            是否使用 Hanning 窗

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (频率数组 Hz, PSD)
        """
        n = len(acc)
        nfft = 1 << int(np.ceil(np.log2(n)))
        nperseg = nfft // 2  # 同 C++ 的 npsd = nfft/NS (NS=2)

        if nperseg > n:
            nperseg = n

        noverlap = int(nperseg * overlap)
        win = 'hann' if window else 'boxcar'

        fs = 1.0 / dt
        freqs, psd = signal.welch(acc, fs=fs, window=win,
                                   nperseg=nperseg, noverlap=noverlap,
                                   nfft=nperseg)

        return freqs, psd

    @staticmethod
    def phase_spectrum(acc: np.ndarray, dt: float) -> tuple:
        """计算相位谱

        Parameters
        ----------
        acc : np.ndarray
            加速度时程
        dt : float
            时间步长 (s)

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (频率数组 Hz, 相位角 rad)
        """
        n = len(acc)
        nfft = 1 << int(np.ceil(np.log2(n)))

        af = np.fft.fft(acc, nfft)

        n_half = nfft // 2 + 1
        fn = 0.5 / dt
        freqs = np.linspace(0.0, fn, n_half)
        phase = np.angle(af[:n_half])

        return freqs, phase
