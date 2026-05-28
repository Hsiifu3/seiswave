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
from concurrent.futures import ThreadPoolExecutor

try:
    from numba import jit
    HAS_NUMBA = True
except Exception:
    HAS_NUMBA = False

    def jit(*args, **kwargs):
        def _wrap(func):
            return func
        if args and callable(args[0]):
            return args[0]
        return _wrap


def _newmark_beta_task(args):
    return _newmark_beta_kernel(*args)


@jit(nopython=True, cache=True, nogil=True)
def _newmark_beta_kernel(acc, dt, period, zeta, out_ra=None, out_rv=None, out_rd=None):
    """Numba kernel for EQSignal-compatible Newmark-beta integration."""
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

    rl0 = 0.0
    rl1 = 0.0
    rl2 = 0.0
    al = 0.0

    if out_rd is None:
        rd = np.zeros(n)
    else:
        rd = out_rd
    if out_rv is None:
        rv = np.zeros(n)
    else:
        rv = out_rv
    if out_ra is None:
        ra = np.zeros(n)
    else:
        ra = out_ra

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
            rl0 = rc0
            rl1 = rc1
            rl2 = rc2

        rd[i] = rl0
        rv[i] = rl1
        ra[i] = rl2
        al = ac

    return ra, rv, rd


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
                zeta: float = 0.05, method: str = "mixed",
                parallel: bool = False, max_workers: int = None) -> 'Spectra':
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
            "mixed" = 短周期频域 + 长周期 Newmark（默认，优先 Fortran 加速）
        parallel : bool
            启用 Numba + 线程池并行计算长周期 Newmark 响应。
        max_workers : int
            并行线程数上限，None 时使用 ThreadPoolExecutor 默认值。

        Returns
        -------
        Spectra
            包含 sa, sv, sd, se 的反应谱对象
        """
        sp = Spectra(periods, zeta)
        acc = np.asarray(acc, dtype=np.float64)
        n_periods = len(periods)

        # Fortran 加速路径（mixed 方法）
        if method == "mixed":
            from .fortran_bridge import HAS_FORTRAN, spectrum_avd
            if HAS_FORTRAN:
                sp.sa, _, sp.sv, sp.sd, sp.se = spectrum_avd(
                    acc, dt, zeta, periods)
                return sp

        # Python / Numba 路径
        sp.sa = np.zeros(n_periods)
        sp.sv = np.zeros(n_periods)
        sp.sd = np.zeros(n_periods)
        sp.se = np.zeros(n_periods)

        threshold = 20.0 * dt
        pending = []

        for i, T in enumerate(periods):
            if method == "newmark":
                pending.append((i, float(T)))
                continue
            if method == "freq":
                ra, rv, rd = Spectra._freq_domain(acc, dt, T, zeta)
            elif method == "mixed":
                if T < threshold:
                    ra, rv, rd = Spectra._freq_domain(acc, dt, T, zeta)
                else:
                    pending.append((i, float(T)))
                    continue
            else:
                raise ValueError(f"未知的计算方法: {method}")

            abs_acc = -ra + acc[:len(ra)]
            sp.sa[i] = np.max(np.abs(abs_acc))
            sp.sv[i] = np.max(np.abs(rv))
            sp.sd[i] = np.max(np.abs(rd))
            omega = 2.0 * np.pi / T
            sp.se[i] = np.max(0.5 * omega**2 * rd**2)

        if pending:
            if parallel and HAS_NUMBA and len(pending) > 1:
                tasks = [(acc, dt, T, zeta) for _, T in pending]
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    results = list(executor.map(_newmark_beta_task, tasks))
                for (idx, T), (ra, rv, rd) in zip(pending, results):
                    abs_acc = -ra + acc[:len(ra)]
                    sp.sa[idx] = np.max(np.abs(abs_acc))
                    sp.sv[idx] = np.max(np.abs(rv))
                    sp.sd[idx] = np.max(np.abs(rd))
                    omega = 2.0 * np.pi / T
                    sp.se[idx] = np.max(0.5 * omega**2 * rd**2)
            else:
                n = len(acc)
                out_ra = np.zeros(n)
                out_rv = np.zeros(n)
                out_rd = np.zeros(n)
                for idx, T in pending:
                    ra, rv, rd = Spectra._newmark_beta(
                        acc, dt, T, zeta, out_ra, out_rv, out_rd)
                    abs_acc = -ra + acc[:len(ra)]
                    sp.sa[idx] = np.max(np.abs(abs_acc))
                    sp.sv[idx] = np.max(np.abs(rv))
                    sp.sd[idx] = np.max(np.abs(rd))
                    omega = 2.0 * np.pi / T
                    sp.se[idx] = np.max(0.5 * omega**2 * rd**2)

        return sp

    @staticmethod
    def _newmark_beta(acc: np.ndarray, dt: float, period: float,
                      zeta: float, out_ra=None, out_rv=None, out_rd=None) -> tuple:
        """Newmark-β 平均加速度法计算 SDOF 响应

        使用 γ=0.5, β=0.25（平均加速度法，无条件稳定）。
        复现 EQSignal newmark()：当 MPR*dt > T 时自动子步插值。

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
        out_ra, out_rv, out_rd : np.ndarray, optional
            预分配的输出数组，用于避免重复内存分配

        Returns
        -------
        tuple[np.ndarray, np.ndarray, np.ndarray]
            (相对加速度, 相对速度, 相对位移)
        """
        if HAS_NUMBA:
            return _newmark_beta_kernel(
                np.asarray(acc, dtype=np.float64), float(dt), float(period), float(zeta),
                out_ra, out_rv, out_rd
            )

        MPR = 20  # 与 EQSignal 一致

        omega = 2.0 * np.pi / period
        k = omega ** 2
        c = 2.0 * zeta * omega

        n = len(acc)

        # 子步插值（复现 EQSignal newmark）
        if dt * MPR > period:
            r = int(np.ceil(MPR * dt / period))
            sub_dt = dt / r
        else:
            r = 1
            sub_dt = dt

        # Newmark-β 参数（平均加速度法）
        beta = 0.25
        gamma = 0.5

        b1 = 1.0 / (beta * sub_dt ** 2)
        b2 = 1.0 / (beta * sub_dt)
        b3 = 1.0 / (2.0 * beta) - 1.0
        b4 = gamma / (beta * sub_dt)
        b5 = gamma / beta - 1.0
        b6 = 0.5 * sub_dt * (gamma / beta - 2.0)
        b7 = sub_dt * (1.0 - gamma)
        b8 = sub_dt * gamma

        keff = k + b1 + b4 * c
        kinv = 1.0 / keff

        # 状态变量：[位移, 速度, 加速度]
        rl = np.zeros(3)  # 上一步
        if out_rd is None:
            rd = np.zeros(n)
        else:
            rd = out_rd
        if out_rv is None:
            rv = np.zeros(n)
        else:
            rv = out_rv
        if out_ra is None:
            ra = np.zeros(n)
        else:
            ra = out_ra

        al = 0.0  # 上一步加速度（用于子步插值）

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

            # 记录每个原始时间步的结果
            rd[i] = rl[0]
            rv[i] = rl[1]
            ra[i] = rl[2]
            al = acc[i]

        return ra, rv, rd

    @staticmethod
    def _freq_domain(acc: np.ndarray, dt: float, period: float,
                     zeta: float) -> tuple:
        """频域法计算 SDOF 响应（与 Fortran rfreq 一致）

        通过 FFT 在频域应用 SDOF 传递函数，再 IFFT 回时域。
        返回值约定与 _newmark_beta 一致：
        - ra = ag - k*u - c*v（使得 abs_acc = -ra + ag = k*u + c*v）
        - rv, rd 为相对速度和位移（取负号，与 Fortran rnmk 一致）

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
            (ra, rv, rd) 与 _newmark_beta 同约定
        """
        n = len(acc)
        nfft = 1 << int(np.ceil(np.log2(n)))  # next power of 2

        omega_n = 2.0 * np.pi / period

        # FFT（使用 rfft，与 Fortran fftw r2c 一致）
        a0 = np.zeros(nfft)
        a0[:n] = acc
        af = np.fft.rfft(a0)

        fs = 1.0 / dt
        df = fs / nfft
        w = np.zeros(nfft // 2 + 1)
        w[1:] = 2.0 * np.pi * np.arange(1, nfft // 2 + 1) * df

        w0 = omega_n
        w0i2 = w0 * w0
        wj2 = w * w
        w0iwj = w0 * w

        # Fortran rfreq 传递函数（直接输出绝对加速度、相对速度、相对位移）
        denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
        denom[np.abs(denom) < 1e-30] = 1e-30 + 0j

        # 绝对加速度传递函数：(w0^2 + 2i*zeta*w0*wj) / denom
        raf = af * (w0i2 + 2.0j * zeta * w0iwj) / denom
        # 相对速度传递函数：-i*wj / denom
        rvf = af * (-1.0j * w) / denom
        # 相对位移传递函数：-1 / denom
        rdf = af * (-1.0) / denom

        ra_abs = np.fft.irfft(raf, nfft)[:n]
        rv_rel = np.fft.irfft(rvf, nfft)[:n]
        rd_rel = np.fft.irfft(rdf, nfft)[:n]

        # 转换为与 _newmark_beta 一致的约定：
        # _newmark_beta: ra = rc(3) = ag - k*u - c*v
        # abs_acc = -ra + ag = k*u + c*v = ra_abs（Fortran rnmk 的 -rc(3)+ac）
        # 所以 ra = ag - ra_abs
        # _newmark_beta: rv = rc(2), rd = rc(1)（相对值，不取负号）
        # Fortran rnmk: rv(i) = -rc(2), rd(i) = -rc(1)
        # 但 compute() 用的是 abs(rv) 和 abs(rd)，符号不影响谱值
        ra = acc[:n] - ra_abs  # 使得 -ra + acc = ra_abs
        rv = rv_rel
        rd = rd_rel

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
