"""
反应谱计算模块

实现 Newmark-β 法、频域法、混合法三种反应谱计算。
周期数组支持对数/线性/混合分布（同 EQSignal C++）。

参考：
- EQSignal C++: Spectra.h / Spectra.cpp
- MATLAB: Newmark.m
- design.md: Spectra 类设计
"""

import numpy as np


class Spectra:
    """反应谱计算与存储"""

    def __init__(self, periods: np.ndarray, zeta: float = 0.05):
        """
        Parameters
        ----------
        periods : np.ndarray
            周期数组 (s)
        zeta : float
            阻尼比
        """
        self.periods = np.asarray(periods, dtype=np.float64)
        self.zeta = zeta
        self.sa = None   # 加速度反应谱（绝对加速度峰值）
        self.sv = None   # 速度反应谱（相对速度峰值）
        self.sd = None   # 位移反应谱（相对位移峰值）
        self.se = None   # 能量谱

    @staticmethod
    def default_periods(p1: float = 0.04, p2: float = 10.0,
                        n: int = 200, mode: str = "mixed") -> np.ndarray:
        """生成默认周期数组

        Parameters
        ----------
        p1 : float
            最小周期
        p2 : float
            最大周期
        n : int
            总点数
        mode : str
            "log" = 对数分布, "linear" = 线性分布,
            "mixed" = 短周期对数 + 长周期线性（同 EQSignal C++）

        Returns
        -------
        np.ndarray
            周期数组
        """
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
                # 短周期对数 + 长周期线性（同 C++ Spectra 构造函数）
                n_short = n // 2
                n_long = n - n_short + 1
                p_short = np.logspace(np.log10(p1), 0.0, n_short)  # p1 ~ 1.0
                p_long = np.linspace(1.0, p2, n_long)
                return np.concatenate([p_short, p_long[1:]])
        else:
            raise ValueError(f"未知的周期分布模式: {mode}")

    @staticmethod
    def compute(acc: np.ndarray, dt: float, periods: np.ndarray,
                zeta: float = 0.05, method: str = "newmark") -> 'Spectra':
        """计算反应谱

        Parameters
        ----------
        acc : np.ndarray
            加速度时程
        dt : float
            时间步长 (s)
        periods : np.ndarray
            周期数组 (s)
        zeta : float
            阻尼比
        method : str
            "newmark" = Newmark-β 平均加速度法
            "freq" = 频域法
            "mixed" = 短周期频域 + 长周期 Newmark

        Returns
        -------
        Spectra
            包含 sa, sv, sd, se 的反应谱对象
        """
        sp = Spectra(periods, zeta)
        acc = np.asarray(acc, dtype=np.float64)
        n_periods = len(periods)

        sp.sa = np.zeros(n_periods)
        sp.sv = np.zeros(n_periods)
        sp.sd = np.zeros(n_periods)
        sp.se = np.zeros(n_periods)

        for i, T in enumerate(periods):
            if method == "newmark":
                ra, rv, rd = Spectra._newmark_beta(acc, dt, T, zeta)
            elif method == "freq":
                ra, rv, rd = Spectra._freq_domain(acc, dt, T, zeta)
            elif method == "mixed":
                # 短周期用频域（快），长周期用 Newmark（准）
                if T < 0.5:
                    ra, rv, rd = Spectra._freq_domain(acc, dt, T, zeta)
                else:
                    ra, rv, rd = Spectra._newmark_beta(acc, dt, T, zeta)
            else:
                raise ValueError(f"未知的计算方法: {method}")

            # 绝对加速度 = 相对加速度 + 地面加速度
            abs_acc = ra + acc[:len(ra)]
            sp.sa[i] = np.max(np.abs(abs_acc))
            sp.sv[i] = np.max(np.abs(rv))
            sp.sd[i] = np.max(np.abs(rd))

            omega = 2.0 * np.pi / T
            sp.se[i] = np.max(0.5 * omega**2 * rd**2)

        return sp

    @staticmethod
    def _newmark_beta(acc: np.ndarray, dt: float, period: float,
                      zeta: float) -> tuple:
        """Newmark-β 平均加速度法计算 SDOF 响应

        使用 γ=0.5, β=0.25（平均加速度法，无条件稳定）。
        同 EQSignal C++ rnmk() 和 MATLAB Newmark.m。

        Parameters
        ----------
        acc : np.ndarray
            地面加速度时程
        dt : float
            时间步长
        period : float
            SDOF 自振周期
        zeta : float
            阻尼比

        Returns
        -------
        tuple[np.ndarray, np.ndarray, np.ndarray]
            (相对加速度, 相对速度, 相对位移)
        """
        omega = 2.0 * np.pi / period
        k = omega ** 2       # 单位质量下的刚度
        c = 2.0 * zeta * omega  # 单位质量下的阻尼

        n = len(acc)
        rd = np.zeros(n)
        rv = np.zeros(n)
        ra = np.zeros(n)

        # 初始条件
        ra[0] = -acc[0] - c * rv[0] - k * rd[0]

        # Newmark-β 参数（平均加速度法）
        gamma = 0.5
        beta = 0.25

        a1 = 1.0 / (beta * dt ** 2)
        a2 = 1.0 / (beta * dt)
        a3 = (1.0 - 2.0 * beta) / (2.0 * beta)

        a4 = gamma / (beta * dt)
        a5 = 1.0 - gamma / beta
        a6 = (1.0 - gamma / (2.0 * beta)) * dt

        # 有效刚度
        keff = k + a1 + c * a4

        for i in range(1, n):
            # 有效荷载
            p_eff = (-acc[i]
                     + a1 * rd[i - 1] + a2 * rv[i - 1] + a3 * ra[i - 1]
                     + c * (a4 * rd[i - 1] + a5 * rv[i - 1] + a6 * ra[i - 1]))

            rd[i] = p_eff / keff
            ra[i] = a1 * (rd[i] - rd[i - 1]) - a2 * rv[i - 1] - a3 * ra[i - 1]
            rv[i] = a4 * (rd[i] - rd[i - 1]) + a5 * rv[i - 1] + a6 * ra[i - 1]

        return ra, rv, rd

    @staticmethod
    def _freq_domain(acc: np.ndarray, dt: float, period: float,
                     zeta: float) -> tuple:
        """频域法计算 SDOF 响应

        通过 FFT 在频域应用 SDOF 传递函数，再 IFFT 回时域。

        Parameters
        ----------
        acc : np.ndarray
            地面加速度时程
        dt : float
            时间步长
        period : float
            SDOF 自振周期
        zeta : float
            阻尼比

        Returns
        -------
        tuple[np.ndarray, np.ndarray, np.ndarray]
            (相对加速度, 相对速度, 相对位移)
        """
        n = len(acc)
        nfft = 1 << int(np.ceil(np.log2(n)))  # next power of 2

        omega_n = 2.0 * np.pi / period
        k = omega_n ** 2
        c_damp = 2.0 * zeta * omega_n

        # FFT
        acc_fft = np.fft.fft(acc, nfft)
        freqs = np.fft.fftfreq(nfft, dt)
        omega = 2.0 * np.pi * freqs

        # SDOF 传递函数 H(ω) = -1 / (k - ω² + 2iζω_n·ω)
        # 位移传递函数：X/Ag = -1 / (ω_n² - ω² + 2iζω_nω)
        denom = k - omega ** 2 + 2j * zeta * omega_n * omega
        # 避免除零
        denom[np.abs(denom) < 1e-30] = 1e-30

        H_d = -1.0 / denom
        H_v = 1j * omega * H_d
        H_a = -omega ** 2 * H_d

        rd_fft = acc_fft * H_d
        rv_fft = acc_fft * H_v
        ra_fft = acc_fft * H_a

        rd = np.real(np.fft.ifft(rd_fft))[:n]
        rv = np.real(np.fft.ifft(rv_fft))[:n]
        ra = np.real(np.fft.ifft(ra_fft))[:n]

        return ra, rv, rd

    def save_csv(self, filepath: str):
        """保存反应谱数据为 CSV"""
        from .io import FileIO
        data = {'period': self.periods}
        if self.sa is not None:
            data['sa'] = self.sa
        if self.sv is not None:
            data['sv'] = self.sv
        if self.sd is not None:
            data['sd'] = self.sd
        if self.se is not None:
            data['se'] = self.se
        FileIO.write_csv(filepath, **data)

    def __str__(self):
        return f"Spectra(n_periods={len(self.periods)}, zeta={self.zeta:.3f})"

    def __repr__(self):
        return self.__str__()
