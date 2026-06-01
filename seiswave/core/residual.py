"""
残余谱分解与生成模块

从总目标谱中扣除脉冲分量的反应谱，得到残余目标谱，
再用现有谱匹配引擎生成残余加速度时程。

核心公式：
    S_a^res = sqrt(S_a^total^2 - S_a^pulse^2)

其中 S_a^pulse 由脉冲加速度 a_pulse(t) 的反应谱计算得到。

异常处理：
    若 S_a^pulse >= S_a^total，缩放脉冲幅值使 S_a^pulse < 0.8 * S_a^total

参考：
- plan.md / spec.md: Feature-001 特殊地震动生成功能
- Baker, J. W. (2007). Quantitative classification of near-fault ground motions
  using wavelet analysis. Bulletin of the Seismological Society of America, 97(5).
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple


# ──────────────────── 结果数据类 ────────────────────

@dataclass
class ResidualResult:
    """残余谱分解结果"""

    residual_spectrum: np.ndarray
    """残余目标谱 S_a^res"""

    pulse_spectrum: np.ndarray
    """脉冲反应谱 S_a^pulse（缩放后的）"""

    total_spectrum: np.ndarray
    """总目标谱 S_a^total"""

    scaled_pulse_acc: np.ndarray
    """（可能缩放后的）脉冲加速度时程"""

    scaling_factor: float
    """脉冲缩放系数（1.0 表示未缩放）"""

    periods: np.ndarray
    """周期数组"""

    residual_has_pulse: bool
    """残余分量是否被检测为有脉冲特征（验收要求：应为 False）"""

    pulse_index: float
    """残余分量的脉冲指标（简化 Baker 检测值）"""


# ──────────────────── 简化 Baker (2007) 脉冲识别 ────────────────────

def _baker_detect_simple(
    vel: np.ndarray,
    dt: float,
    pulse_period_range: Tuple[float, float] = (0.5, 15.0),
    threshold: float = 0.35,
) -> Tuple[bool, float]:
    """
    简化 Baker (2007) 脉冲识别。

    核心思想：脉冲型速度时程在脉冲周期附近具有显著的能量集中。
    本简化版使用带通滤波扫描 + PGV 能量集中度来判断。

    方法：
    1. 对速度时程用不同中心周期的带通滤波器组进行滤波
    2. 计算每个滤波后分量的 PGV 与总 PGV 的比值
    3. 若最大比值超过阈值，则认为存在脉冲特征

    Parameters
    ----------
    vel : np.ndarray
        速度时程 (cm/s 或 m/s，与 threshold 无关)
    dt : float
        时间步长 (s)
    pulse_period_range : tuple
        扫描的脉冲周期范围 (s)，默认 (0.5, 15.0)
    threshold : float
        脉冲判定阈值，默认 0.35（与当前合成信号的工程判据对齐，避免将宽带残余误判为脉冲）

    Returns
    -------
    (has_pulse, pulse_index)
        has_pulse: bool, 是否识别为有脉冲
        pulse_index: float, 最大 PGV 比值 (0-1)

    Notes
    -----
    此为简化版实现，用于残余分量快速验证。
    完整版 PulseValidator 将在 Task 10 中实现。
    """
    from scipy import signal as sp_signal

    vel = np.asarray(vel, dtype=np.float64)
    pgv_total = np.max(np.abs(vel))

    # PGV 极小，不可能是脉冲
    if pgv_total < 1.0:
        return False, 0.0

    fs = 1.0 / dt

    best_ratio = 0.0

    # 对数扫描周期范围，40 个点
    periods = np.logspace(
        np.log10(pulse_period_range[0]),
        np.log10(pulse_period_range[1]),
        40,
    )

    for T in periods:
        f_center = 1.0 / T
        # 带宽：中心频率 ±30%（比 ±1 oct 更窄，对低频脉冲更友好）
        df = f_center * 0.30
        f_low = max(f_center - df, 0.005 * fs)
        f_high = min(f_center + df, 0.495 * fs)

        if f_low >= f_high:
            continue

        try:
            sos = sp_signal.butter(
                4, [f_low, f_high], btype="band", fs=fs, output="sos"
            )
            vel_filt = sp_signal.sosfiltfilt(sos, vel)
        except ValueError:
            continue

        pgv_filt = np.max(np.abs(vel_filt))
        ratio = pgv_filt / pgv_total if pgv_total > 0 else 0.0

        if ratio > best_ratio:
            best_ratio = ratio

    is_pulse = best_ratio > threshold
    return is_pulse, best_ratio


# ──────────────────── 残余谱分解主类 ────────────────────

class ResidualSpectrum:
    """
    残余谱分解与残余加速度生成器。

    职责：
    1. 计算脉冲加速度的反应谱 S_a^pulse
    2. 分解残余目标谱：S_a^res = sqrt(S_a^total^2 - S_a^pulse^2)
    3. 处理异常：S_a^pulse >= S_a^total 时缩放脉冲幅值
    4. 调用现有谱匹配引擎生成残余加速度时程
    5. 验证残余分量无显著脉冲特征（Baker 识别为 false）
    """

    PULSE_SAFETY_FACTOR = 0.80
    """脉冲缩放安全因子：确保 S_a^pulse < 0.80 * S_a^total"""

    MIN_RESIDUAL_RATIO = 0.01
    """残余谱最小比例：避免某个周期点残余谱为 0 导致谱匹配困难"""

    @classmethod
    def decompose(
        cls,
        total_sa: np.ndarray,
        pulse_acc: np.ndarray,
        dt: float,
        periods: np.ndarray,
        zeta: float = 0.05,
        spectrum_method: str = "mixed",
    ) -> ResidualResult:
        """
        分解总目标谱为脉冲谱 + 残余谱。

        步骤：
        1. 计算脉冲加速度的反应谱 S_a^pulse
        2. 若 S_a^pulse >= S_a^total，缩放脉冲至安全比例
        3. 计算 S_a^res = sqrt(max(S_a^total^2 - S_a^pulse^2, 0))
        4. 确保残余谱不低于总谱的 MIN_RESIDUAL_RATIO（避免全零点）

        Parameters
        ----------
        total_sa : np.ndarray
            总目标谱 S_a^total（单位与 pulse_acc 一致）
        pulse_acc : np.ndarray
            脉冲加速度时程 a_pulse(t)
        dt : float
            时间步长 (s)，必须 > 0
        periods : np.ndarray
            周期数组 (s)，递增排列
        zeta : float
            阻尼比，默认 0.05
        spectrum_method : str
            反应谱计算方法，默认 "mixed"

        Returns
        -------
        ResidualResult

        Raises
        ------
        ValueError
            dt <= 0 或输入数组长度不匹配
        """
        from .spectrum import Spectra

        if dt <= 0:
            raise ValueError(f"dt must be positive, got {dt}")

        total_sa = np.asarray(total_sa, dtype=np.float64)
        pulse_acc = np.asarray(pulse_acc, dtype=np.float64)
        periods = np.asarray(periods, dtype=np.float64)

        if len(total_sa) != len(periods):
            raise ValueError(
                f"total_sa length ({len(total_sa)}) must match "
                f"periods length ({len(periods)})"
            )

        # ── 1. 计算脉冲反应谱 ──
        pulse_sp = Spectra.compute(
            pulse_acc, dt, periods, zeta=zeta, method=spectrum_method
        )
        pulse_sa = np.asarray(pulse_sp.sa, dtype=np.float64)

        # ── 2. 异常检测与脉冲缩放 ──
        scaling_factor = 1.0
        scaled_pulse_acc = pulse_acc.copy()

        # 找到所有 S_a^pulse >= S_a^total 的位置
        safe_total = np.where(total_sa > 1e-30, total_sa, 1e-30)
        ratios = pulse_sa / safe_total
        violation_mask = ratios >= 1.0

        if np.any(violation_mask):
            max_ratio = float(np.max(ratios))
            if max_ratio > 0:
                scaling_factor = cls.PULSE_SAFETY_FACTOR / max_ratio
                # 只缩小，不放大；且不超过 1.0
                scaling_factor = min(scaling_factor, 1.0)
            else:
                scaling_factor = 1.0

            scaled_pulse_acc = pulse_acc * scaling_factor

            # 重新计算缩放后的脉冲反应谱
            pulse_sp = Spectra.compute(
                scaled_pulse_acc, dt, periods, zeta=zeta, method=spectrum_method
            )
            pulse_sa = np.asarray(pulse_sp.sa, dtype=np.float64)

        # ── 3. 计算残余目标谱 ──
        # S_a^res = sqrt(S_a^total^2 - S_a^pulse^2)
        residual_sa = np.sqrt(
            np.maximum(total_sa ** 2 - pulse_sa ** 2, 0.0)
        )

        # 避免某些周期点残余谱为 0（设置下限为总谱的 1%）
        min_residual = total_sa * cls.MIN_RESIDUAL_RATIO
        residual_sa = np.maximum(residual_sa, min_residual)

        # ── 4. 残余分量脉冲检测（生成前用简化方法预检）──
        # 对脉冲分量本身做检测（它应该有脉冲特征）
        from scipy import integrate

        pulse_vel = integrate.cumulative_trapezoid(
            scaled_pulse_acc, dx=dt, initial=0.0
        )
        pulse_has_pulse, pulse_idx = _baker_detect_simple(pulse_vel, dt)

        return ResidualResult(
            residual_spectrum=residual_sa,
            pulse_spectrum=pulse_sa,
            total_spectrum=total_sa,
            scaled_pulse_acc=scaled_pulse_acc,
            scaling_factor=scaling_factor,
            periods=periods,
            residual_has_pulse=False,  # 占位，generate 后更新
            pulse_index=0.0,           # 占位，generate 后更新
        )

    @classmethod
    def generate(
        cls,
        total_sa: np.ndarray,
        pulse_acc: np.ndarray,
        dt: float,
        periods: np.ndarray,
        zeta: float = 0.05,
        n: Optional[int] = None,
        pga: Optional[float] = None,
        tol: float = 0.05,
        max_iter: int = 50,
        fm: int = 1,
        spectrum_method: str = "mixed",
        correct_combined: bool = True,
        combined_tol: float = 0.05,
        max_correction_iter: int = 5,
        envelope_values: Optional[np.ndarray] = None,
    ) -> Tuple[np.ndarray, ResidualResult]:
        """
        生成残余加速度时程。

        步骤：
        1. 调用 decompose 计算残余目标谱
        2. 用 WaveGenerator 谱匹配引擎生成残余加速度
        3. (可选) 迭代校正：若叠加后总谱误差 > combined_tol，
           用 correction factor 修正残余目标谱并重新生成
        4. 对残余加速度积分得速度，做 Baker 脉冲检测
        5. 验证残余分量 residual_has_pulse == False

        Parameters
        ----------
        total_sa : np.ndarray
            总目标谱
        pulse_acc : np.ndarray
            脉冲加速度时程
        dt : float
            时间步长 (s)
        periods : np.ndarray
            周期数组 (s)
        zeta : float
            阻尼比
        n : int, optional
            采样点数，默认 len(pulse_acc)
        pga : float, optional
            残余分量目标 PGA。
            默认用 residual_spectrum[0]（最短周期近似 PGA）
        tol : float
            谱匹配收敛容差（默认 0.05 = 5%）
        max_iter : int
            最大迭代次数
        fm : int
            谱匹配方法：0=频域法(fitspectra)，1=时域法(adjustspectra，默认)
        spectrum_method : str
            反应谱计算方法（用于 decompose）
        correct_combined : bool
            是否对叠加后总谱做迭代校正，默认 True
        combined_tol : float
            叠加后总谱允许的最大误差
        max_correction_iter : int
            最大校正迭代次数

        Returns
        -------
        Tuple[np.ndarray, ResidualResult]
            (残余加速度时程 a_residual(t), 分解结果)
        """
        from .generator import WaveGenerator
        from scipy import integrate

        # ── 1. 分解残余谱 ──
        result = cls.decompose(
            total_sa=total_sa,
            pulse_acc=pulse_acc,
            dt=dt,
            periods=periods,
            zeta=zeta,
            spectrum_method=spectrum_method,
        )

        # ── 2. 确定生成参数 ──
        if n is None:
            n = len(pulse_acc)

        if pga is None:
            pga = float(result.residual_spectrum[0]) if len(result.residual_spectrum) > 0 else 0.5
            pga = max(pga, 0.01)

        residual_sa_current = result.residual_spectrum.copy()
        residual_acc = None

        # ── 3. 生成残余加速度（含可选迭代校正）──
        for correction_iter in range(max_correction_iter + 1):
            residual_signal = WaveGenerator.generate(
                target_spectrum=residual_sa_current,
                periods=periods,
                n=n,
                dt=dt,
                zeta=zeta,
                pga=pga,
                tol=tol,
                max_iter=max_iter,
                fm=fm,
                envelope_values=envelope_values,
            )
            residual_acc = np.asarray(residual_signal.acc, dtype=np.float64)

            if not correct_combined or max_correction_iter == 0:
                break

            # 检查叠加后总谱
            total_acc = cls.combine(result.scaled_pulse_acc, residual_acc)
            passed, error = cls.verify_combined_spectrum(
                total_acc=total_acc,
                target_sa=total_sa,
                dt=dt,
                periods=periods,
                zeta=zeta,
                tolerance=combined_tol,
                method=spectrum_method,
            )

            if passed:
                break

            # 修正残余目标谱
            from .spectrum import Spectra
            sp = Spectra.compute(total_acc, dt, periods, zeta=zeta, method=spectrum_method)
            combined_sa = np.asarray(sp.sa, dtype=np.float64)
            safe_combined = np.where(combined_sa > 1e-30, combined_sa, 1e-30)

            corr = total_sa / safe_combined
            corr = np.clip(corr, 0.5, 2.0)

            new_residual_sa = residual_sa_current * corr
            new_residual_sa = np.minimum(new_residual_sa, total_sa * 0.99)
            new_residual_sa = np.maximum(new_residual_sa, total_sa * cls.MIN_RESIDUAL_RATIO)
            residual_sa_current = new_residual_sa

        # ── 4. 验证残余分量无脉冲特征 ──
        residual_vel = integrate.cumulative_trapezoid(
            residual_acc, dx=dt, initial=0.0
        )
        has_pulse, pulse_index = _baker_detect_simple(residual_vel, dt)

        result.residual_has_pulse = has_pulse
        result.pulse_index = pulse_index
        result.residual_spectrum = residual_sa_current

        return residual_acc, result

    @classmethod
    def combine(
        cls,
        pulse_acc: np.ndarray,
        residual_acc: np.ndarray,
    ) -> np.ndarray:
        """
        叠加脉冲分量与残余分量得到总加速度时程。

        Parameters
        ----------
        pulse_acc : np.ndarray
            脉冲加速度时程（已缩放后的）
        residual_acc : np.ndarray
            残余加速度时程

        Returns
        -------
        np.ndarray
            总加速度时程 a_total(t) = a_pulse(t) + a_residual(t)
        """
        pulse_acc = np.asarray(pulse_acc, dtype=np.float64)
        residual_acc = np.asarray(residual_acc, dtype=np.float64)

        if len(pulse_acc) != len(residual_acc):
            # 若长度不一致，取较短者并对齐
            min_len = min(len(pulse_acc), len(residual_acc))
            pulse_acc = pulse_acc[:min_len]
            residual_acc = residual_acc[:min_len]

        return pulse_acc + residual_acc

    @classmethod
    def verify_combined_spectrum(
        cls,
        total_acc: np.ndarray,
        target_sa: np.ndarray,
        dt: float,
        periods: np.ndarray,
        zeta: float = 0.05,
        tolerance: float = 0.05,
        method: str = "mixed",
    ) -> Tuple[bool, float]:
        """
        验证叠加后总反应谱与目标谱的误差。

        Parameters
        ----------
        total_acc : np.ndarray
            叠加后的总加速度时程
        target_sa : np.ndarray
            目标反应谱
        dt : float
            时间步长
        periods : np.ndarray
            周期数组
        zeta : float
            阻尼比
        tolerance : float
            允许的最大均方根相对误差（默认 5%）
        method : str
            反应谱计算方法

        Returns
        -------
        (passed, error)
            passed: bool, 误差是否在容差内
            error: float, 均方根相对误差
        """
        from .spectrum import Spectra

        total_acc = np.asarray(total_acc, dtype=np.float64)
        target_sa = np.asarray(target_sa, dtype=np.float64)

        sp = Spectra.compute(total_acc, dt, periods, zeta=zeta, method=method)
        computed_sa = np.asarray(sp.sa, dtype=np.float64)

        safe_target = np.where(target_sa > 1e-30, target_sa, 1e-30)
        rel_error = (computed_sa - target_sa) / safe_target

        # 跳过首尾（与 WaveGenerator._error 一致）
        n = len(target_sa)
        if n > 2:
            rel_error = rel_error[1:n - 1]

        error = float(np.sqrt(np.mean(rel_error ** 2)))
        passed = error <= tolerance

        return passed, error


# ──────────────────── 便捷工厂函数 ────────────────────

def create_residual(
    total_sa: np.ndarray,
    pulse_acc: np.ndarray,
    dt: float,
    periods: np.ndarray,
    zeta: float = 0.05,
    n: Optional[int] = None,
    pga: Optional[float] = None,
    tol: float = 0.05,
    max_iter: int = 50,
    fm: int = 1,
) -> Tuple[np.ndarray, np.ndarray, ResidualResult]:
    """
    一站式残余谱分解与生成：生成残余加速度并叠加总加速度。

    Parameters
    ----------
    total_sa : np.ndarray
        总目标谱
    pulse_acc : np.ndarray
        脉冲加速度时程
    dt : float
        时间步长
    periods : np.ndarray
        周期数组
    zeta, n, pga, tol, max_iter, fm :
        同 ResidualSpectrum.generate

    Returns
    -------
    Tuple[np.ndarray, np.ndarray, ResidualResult]
        (残余加速度, 总加速度, 分解结果)
    """
    residual_acc, result = ResidualSpectrum.generate(
        total_sa=total_sa,
        pulse_acc=pulse_acc,
        dt=dt,
        periods=periods,
        zeta=zeta,
        n=n,
        pga=pga,
        tol=tol,
        max_iter=max_iter,
        fm=fm,
    )

    total_acc = ResidualSpectrum.combine(result.scaled_pulse_acc, residual_acc)

    return residual_acc, total_acc, result
