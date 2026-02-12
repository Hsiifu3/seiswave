"""
地震信号处理核心类

融合 EQSignal C++ 的 API 设计，提供加速度/速度/位移积分、
PGA/持时/有效持时属性、归一化/缩放、裁剪、重采样等功能。

参考：
- EQSignal C++: EQSignal.h / EQSignal.cpp
- design.md: EQSignal 类设计
"""

import numpy as np
from scipy import integrate, signal as sp_signal


class EQSignal:
    """地震信号处理核心类"""

    def __init__(self, acc: np.ndarray, dt: float,
                 name: str = "", v0: float = 0.0, d0: float = 0.0):
        """
        Parameters
        ----------
        acc : np.ndarray
            加速度时程 (m/s² 或 g，由用户自行管理单位)
        dt : float
            时间步长 (s)
        name : str
            记录名称
        v0 : float
            初始速度
        d0 : float
            初始位移
        """
        self.acc = np.asarray(acc, dtype=np.float64)
        self.dt = dt
        self.name = name
        self.n = len(self.acc)
        self.v0 = v0
        self.d0 = d0

        self.vel = np.zeros(self.n)
        self.disp = np.zeros(self.n)

    # ──────────────────── I/O 便捷方法 ────────────────────

    @classmethod
    def from_at2(cls, filepath: str) -> 'EQSignal':
        """从 AT2 文件创建 EQSignal"""
        from .io import FileIO
        rec = FileIO.read_at2(filepath)
        return cls(rec.acc, rec.dt, name=rec.name)

    @classmethod
    def from_txt(cls, filepath: str, dt: float = None,
                 skip_rows: int = 0, single_col: bool = True) -> 'EQSignal':
        """从 txt 文件创建 EQSignal"""
        from .io import FileIO
        rec = FileIO.read_txt(filepath, dt=dt, skip_rows=skip_rows,
                              single_col=single_col)
        return cls(rec.acc, rec.dt, name=rec.name)

    @classmethod
    def batch_load(cls, directory: str, pattern: str = "*.AT2") -> list['EQSignal']:
        """批量加载目录下的地震动文件"""
        from .io import FileIO
        records = FileIO.batch_load(directory, pattern)
        return [cls(r.acc, r.dt, name=r.name) for r in records]

    def save_txt(self, filepath: str, two_col: bool = False):
        """保存为 txt 格式"""
        from .io import FileIO
        FileIO.write_txt(filepath, self.acc, self.dt, two_col=two_col)

    def save_at2(self, filepath: str, metadata: dict = None):
        """保存为 AT2 格式"""
        from .io import FileIO
        FileIO.write_at2(filepath, self.acc, self.dt, metadata=metadata)

    def save_csv(self, filepath: str):
        """保存为 CSV 格式"""
        from .io import FileIO
        FileIO.write_csv(filepath, time=self.time, acc=self.acc,
                         vel=self.vel, disp=self.disp)

    # ──────────────────── 信号处理 ────────────────────

    def a2vd(self, raw: bool = False) -> None:
        """从加速度积分计算速度和位移（梯形积分法）

        Parameters
        ----------
        raw : bool
            是否使用原始加速度（暂不支持，预留接口）
        """
        self.vel = integrate.cumulative_trapezoid(
            self.acc, dx=self.dt, initial=0.0
        ) + self.v0
        self.disp = integrate.cumulative_trapezoid(
            self.vel, dx=self.dt, initial=0.0
        ) + self.d0

    def baseline_correction(self, method: str = "poly", order: int = 2) -> None:
        """基线校正（就地修改）

        Parameters
        ----------
        method : str
            "poly" = 多项式去趋势, "bilinear" = 双线性去趋势
        order : int
            多项式阶数（仅 method="poly" 时有效）
        """
        from .filter import Filter
        if method == "poly":
            self.acc = Filter.detrend(self.acc, self.dt, order=order)
        elif method == "bilinear":
            self.acc = Filter.bilinear_detrend(self.acc)
        else:
            raise ValueError(f"未知的基线校正方法: {method}")
        self.a2vd()

    def filter(self, ftype: str = "bandpass", order: int = 4,
               f1: float = 0.1, f2: float = 25.0) -> None:
        """Butterworth 滤波（就地修改）

        Parameters
        ----------
        ftype : str
            "bandpass", "lowpass", "highpass"
        order : int
            滤波器阶数
        f1 : float
            低截止频率 (Hz)
        f2 : float
            高截止频率 (Hz)
        """
        from .filter import Filter
        if ftype == "bandpass":
            freqs = (f1, f2)
        elif ftype == "lowpass":
            freqs = f2
        elif ftype == "highpass":
            freqs = f1
        else:
            raise ValueError(f"未知的滤波类型: {ftype}")
        self.acc = Filter.butterworth(self.acc, self.dt, ftype=ftype,
                                      order=order, freqs=freqs)
        self.a2vd()

    def trim(self, i1: int, i2: int) -> None:
        """裁剪信号（就地修改）

        Parameters
        ----------
        i1 : int
            起始索引
        i2 : int
            结束索引（包含）
        """
        self.acc = self.acc[i1:i2 + 1].copy()
        self.n = len(self.acc)
        self.vel = np.zeros(self.n)
        self.disp = np.zeros(self.n)
        self.a2vd()

    def auto_trim(self, thd1: float = 0.02, thd2: float = 0.98) -> tuple:
        """基于 Arias 强度自动裁剪

        Parameters
        ----------
        thd1 : float
            起始 Arias 强度百分比阈值
        thd2 : float
            结束 Arias 强度百分比阈值

        Returns
        -------
        tuple[int, int]
            裁剪的起止索引
        """
        ia = self.arias_intensity()
        if ia[-1] == 0:
            return 0, self.n - 1

        ia_norm = ia / ia[-1]

        i1 = 0
        for i in range(self.n):
            if ia_norm[i] >= thd1:
                i1 = i
                break

        i2 = self.n - 1
        for i in range(self.n - 1, -1, -1):
            if ia_norm[i] <= thd2:
                i2 = i
                break

        self.trim(i1, i2)
        return i1, i2

    def normalize(self) -> None:
        """归一化到 PGA = 1.0（就地修改）"""
        pga = np.max(np.abs(self.acc))
        if pga > 0:
            self.acc = self.acc / pga
            self.a2vd()

    def scale(self, factor: float) -> None:
        """缩放加速度（就地修改）"""
        self.acc = self.acc * factor
        self.a2vd()

    def resample(self, new_dt: float) -> None:
        """重采样到新的时间步长（就地修改）

        Parameters
        ----------
        new_dt : float
            新的时间步长 (s)
        """
        new_n = int(round(self.n * self.dt / new_dt))
        self.acc = sp_signal.resample(self.acc, new_n)
        self.dt = new_dt
        self.n = new_n
        self.vel = np.zeros(self.n)
        self.disp = np.zeros(self.n)
        self.a2vd()

    # ──────────────────── 分析 ────────────────────

    def compute_response_spectrum(self, periods: np.ndarray = None,
                                  zeta: float = 0.05,
                                  method: str = "newmark") -> 'Spectra':
        """计算反应谱

        Parameters
        ----------
        periods : np.ndarray, optional
            周期数组，默认使用混合分布
        zeta : float
            阻尼比
        method : str
            "newmark", "freq", "mixed"

        Returns
        -------
        Spectra
        """
        from .spectrum import Spectra
        if periods is None:
            periods = Spectra.default_periods()
        return Spectra.compute(self.acc, self.dt, periods, zeta=zeta,
                               method=method)

    def compute_fft(self) -> tuple:
        """计算傅里叶振幅谱

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (频率数组, 振幅谱)
        """
        from .fft import FFT
        return FFT.amplitude_spectrum(self.acc, self.dt)

    def compute_psd(self, overlap: float = 0.5) -> tuple:
        """计算功率谱密度 (Welch 方法)

        Returns
        -------
        tuple[np.ndarray, np.ndarray]
            (频率数组, PSD)
        """
        from .fft import FFT
        return FFT.welch_psd(self.acc, self.dt, overlap=overlap)

    def arias_intensity(self) -> np.ndarray:
        """计算 Arias 强度

        Returns
        -------
        np.ndarray
            累积 Arias 强度时程
        """
        ia = np.cumsum(self.acc ** 2) * self.dt * np.pi / (2.0 * 9.81)
        return ia

    # ──────────────────── 属性 ────────────────────

    @property
    def pga(self) -> float:
        """峰值地面加速度"""
        return float(np.max(np.abs(self.acc)))

    @property
    def duration(self) -> float:
        """总持时 (s)"""
        return (self.n - 1) * self.dt

    @property
    def effective_duration(self) -> float:
        """有效持时 (s)，基于 5%-95% Arias 强度"""
        ia = self.arias_intensity()
        if ia[-1] == 0:
            return 0.0
        ia_norm = ia / ia[-1]

        i1 = np.searchsorted(ia_norm, 0.05)
        i2 = np.searchsorted(ia_norm, 0.95)
        return (i2 - i1) * self.dt

    @property
    def time(self) -> np.ndarray:
        """时间数组"""
        return np.arange(self.n) * self.dt

    # ──────────────────── 魔术方法 ────────────────────

    def __len__(self):
        return self.n

    def __str__(self):
        return (f"EQSignal(name='{self.name}', n={self.n}, dt={self.dt}, "
                f"duration={self.duration:.2f}s, pga={self.pga:.4f})")

    def __repr__(self):
        return self.__str__()
