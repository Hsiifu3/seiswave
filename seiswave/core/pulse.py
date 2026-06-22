"""
MP 脉冲小波生成模块

基于 Mavroeidis & Papageorgiou (2003) 解析脉冲模型，
生成脉冲型近场地震动的速度/加速度时程。

公式：
    v(t) = (A/2) * [1 + cos(2π(t-t₀)/Tp)] * cos(2π(t-t₀)/Tp + φ)
    有效区间: t₀ - Tp/2 ≤ t ≤ t₀ + Tp/2，区间外为 0
    加速度通过速度数值微分获得

参考：
- Mavroeidis, G. P., & Papageorgiou, A. S. (2003). A mathematical
  representation of near-fault ground motions. Bulletin of the
  Seismological Society of America, 93(3), 1099-1131.
- plan.md / spec.md: Feature-001 特殊地震动生成功能
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, Literal


# ──────────────────── 参数数据类 ────────────────────

@dataclass(frozen=True)
class PulseParams:
    """脉冲参数（不可变）"""

    Tp: float
    """脉冲周期 (s)，必须 > 0"""

    A: float
    """脉冲幅值 (cm/s)，必须 > 0"""

    phi: float
    """相位角 (rad)：0 = 对称脉冲，π/2 = 单向脉冲"""

    t0: float
    """脉冲中心时间 (s)，必须 ≥ 0"""

    gamma: float = 1.8
    """MP 振荡参数 γ：脉冲半周期数，γ>1。默认 1.8 = MP(2003) 165 条记录标定均值
    (Mavroeidis-Papageorgiou 2003;γ~N(1.8, 0.4), 左截断于 1)。"""

    def __post_init__(self):
        if self.Tp <= 0:
            raise ValueError(f"Tp must be positive, got {self.Tp}")
        if self.A <= 0:
            raise ValueError(f"A must be positive, got {self.A}")
        if self.t0 < 0:
            raise ValueError(f"t0 must be non-negative, got {self.t0}")
        if self.gamma < 1.0:
            raise ValueError(f"gamma must be >= 1.0, got {self.gamma}")

    def with_overrides(self, **kwargs) -> "PulseParams":
        """返回参数被覆盖后的新实例（原实例不变）。"""
        from dataclasses import replace
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean)


# ──────────────────── 脉冲参数计算器 ────────────────────

class PulseCalculator:
    """
    基于 Mavroeidis & Papageorgiou (2003) 经验公式计算脉冲参数。
    """

    @staticmethod
    def compute_period(Mw: float) -> float:
        """
        计算脉冲周期 Tp。

        Mavroeidis & Papageorgiou (2003) 原式（以 10 为底）：
            log10(Tp) = -2.9 + 0.5 * Mw
        直接采用原式，不做自然对数系数圆整。

        Parameters
        ----------
        Mw : float
            矩震级

        Returns
        -------
        float
            脉冲周期 Tp (s)

        Raises
        ------
        ValueError
            Mw < 5.5 时脉冲模型不适用
        """
        if Mw < 5.5:
            raise ValueError(
                f"脉冲模型不适用于 Mw < 5.5 (got {Mw})，请使用 NF 模式"
            )
        return float(10.0 ** (-2.9 + 0.5 * Mw))

    @classmethod
    def compute_params(
        cls,
        Mw: float,
        R: float,
        fault_type: Literal["strike_slip", "normal", "reverse"] = "strike_slip",
        phi: Optional[float] = None,
        t_total: float = 30.0,
        gamma: float = 1.8,
        Tp_override: Optional[float] = None,
        A_override: Optional[float] = None,
        phi_override: Optional[float] = None,
        t0_override: Optional[float] = None,
        gamma_override: Optional[float] = None,
    ) -> PulseParams:
        """
        计算脉冲参数 (Tp, A, φ, t₀)。

        参数计算基于以下文献经验关系：
        - Tp: Mavroeidis & Papageorgiou (2003), ln(Tp) = -6.68 + 1.15*Mw
        - A:  综合 Baker (2007) 脉冲记录 PGV 统计与 MP (2003) 幅值-震级关系
              ln(A) = -0.8 + 0.88*Mw - 0.8*ln(R) + fault_correction
              断层修正: strike_slip=0.0, normal=-0.15, reverse=+0.20
        - φ:  默认 0（对称脉冲），可覆盖为 π/2（单向脉冲）
        - t₀: 默认居中 (t_total / 2)，可用户覆盖

        Parameters
        ----------
        Mw : float
            矩震级
        R : float
            断层距 (km)
        fault_type : str
            断层类型，影响幅值统计修正
        phi : float, optional
            相位角 (rad)，默认 0.0（对称脉冲）
        t_total : float
            总持时 (s)，用于计算默认居中时间 t0
        Tp_override : float, optional
            用户覆盖的脉冲周期 (s)
        A_override : float, optional
            用户覆盖的脉冲幅值 (cm/s)
        phi_override : float, optional
            用户覆盖的相位角 (rad)
        t0_override : float, optional
            用户覆盖的脉冲中心时间 (s)

        Returns
        -------
        PulseParams
        """
        Tp = Tp_override if Tp_override is not None else cls.compute_period(Mw)

        if A_override is not None:
            A = A_override
        else:
            # 基于 Baker (2007) 脉冲记录 PGV 统计与 MP (2003) 的简化经验公式
            # 量级验证:
            #   Mw 7.0, R 5km, SS → A ≈ 59 cm/s
            #   Mw 7.5, R 3km, R  → A ≈ 152 cm/s
            #   Mw 6.5, R 10km, SS → A ≈ 22 cm/s
            fault_corr = {
                "strike_slip": 0.0,
                "normal": -0.15,
                "reverse": 0.20,
            }.get(fault_type, 0.0)
            ln_A = -0.8 + 0.88 * Mw - 0.8 * np.log(max(R, 0.1)) + fault_corr
            A = float(np.exp(ln_A))
            A = max(A, 10.0)  # 最小幅值 10 cm/s

        phi_eff = phi_override if phi_override is not None else (phi if phi is not None else 0.0)
        t0 = t0_override if t0_override is not None else (t_total / 2.0)
        gamma_eff = gamma_override if gamma_override is not None else gamma

        return PulseParams(Tp=Tp, A=A, phi=phi_eff, t0=t0, gamma=gamma_eff)


# ──────────────────── MP 脉冲小波生成器 ────────────────────

class PulseWavelet:
    """
    MP 脉冲小波生成器。

    生成 Mavroeidis & Papageorgiou (2003) 解析脉冲的速度/加速度时程。
    """

    @classmethod
    def generate(
        cls,
        params: PulseParams,
        dt: float,
        n: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        生成脉冲速度/加速度时程。

        Parameters
        ----------
        params : PulseParams
            脉冲参数
        dt : float
            时间步长 (s)，必须 > 0
        n : int
            采样点数，必须 > 0

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (velocity, acceleration) — 单位 cm/s, cm/s²

        Raises
        ------
        ValueError
            dt <= 0 或 n <= 0
        """
        if dt <= 0:
            raise ValueError(f"dt must be positive, got {dt}")
        if n <= 0:
            raise ValueError(f"n must be positive, got {n}")

        t = np.arange(n, dtype=np.float64) * dt
        v = cls.velocity(t, params)
        a = cls.acceleration(t, v, dt, params)
        return v, a

    @staticmethod
    def velocity(t: np.ndarray, params: PulseParams) -> np.ndarray:
        """
        脉冲速度时程（Mavroeidis & Papageorgiou 2003 完整式）。

        公式：
            v(t) = (A/2)·[1 + cos(2π(t-t₀)/(γ·Tp))]·cos(2π(t-t₀)/Tp + φ)

        有效区间: t₀ - γ·Tp/2 ≤ t ≤ t₀ + γ·Tp/2，区间外为 0。
        γ 为 MP 振荡参数（包络跨 γ 个载波周期）；γ=1 退化为单周期脉冲。

        Parameters
        ----------
        t : np.ndarray
            时间数组 (s)
        params : PulseParams
            脉冲参数

        Returns
        -------
        np.ndarray
            与 t 同形状的速度时程 (cm/s)
        """
        t = np.asarray(t, dtype=np.float64)
        v = np.zeros_like(t)

        Tp, A, phi, t0 = params.Tp, params.A, params.phi, params.t0
        gamma = params.gamma
        half = gamma * Tp / 2.0
        mask = (t >= t0 - half) & (t <= t0 + half)
        if not np.any(mask):
            return v

        tau = t[mask] - t0
        env = 1.0 + np.cos(2.0 * np.pi * tau / (gamma * Tp))
        carrier = np.cos(2.0 * np.pi * tau / Tp + phi)
        v[mask] = (A / 2.0) * env * carrier
        return v

    @staticmethod
    def acceleration(
        t: np.ndarray, v: np.ndarray, dt: float, params: "PulseParams | None" = None
    ) -> np.ndarray:
        """
        脉冲加速度时程。

        若提供 params，使用 MP (2003) 速度式的解析导数（精确）：
            a(t) = -(A/2)·[ ω_e·sin(ω_e·τ)·cos(ω_c·τ+φ)
                            + ω_c·(1+cos(ω_e·τ))·sin(ω_c·τ+φ) ]
            其中 ω_c = 2π/Tp, ω_e = 2π/(γ·Tp)
        否则回退到对速度的数值微分 (np.gradient)。

        Parameters
        ----------
        t : np.ndarray
            时间数组 (s)
        v : np.ndarray
            速度时程 (cm/s)，仅在数值微分回退时使用
        dt : float
            时间步长 (s)
        params : PulseParams, optional
            脉冲参数；提供则用解析式

        Returns
        -------
        np.ndarray
            加速度时程 (cm/s²)
        """
        t_arr = np.asarray(t, dtype=np.float64)

        if params is not None:
            Tp, A, phi, t0 = params.Tp, params.A, params.phi, params.t0
            gamma = params.gamma
            half = gamma * Tp / 2.0
            a = np.zeros_like(t_arr)
            mask = (t_arr >= t0 - half) & (t_arr <= t0 + half)
            if np.any(mask):
                tau = t_arr[mask] - t0
                wc = 2.0 * np.pi / Tp
                we = 2.0 * np.pi / (gamma * Tp)
                a[mask] = -(A / 2.0) * (
                    we * np.sin(we * tau) * np.cos(wc * tau + phi)
                    + wc * (1.0 + np.cos(we * tau)) * np.sin(wc * tau + phi)
                )
            return a

        v_arr = np.asarray(v, dtype=np.float64)
        if len(v_arr) != len(t_arr):
            raise ValueError(
                f"v 和 t 长度不一致: {len(v_arr)} vs {len(t_arr)}"
            )
        return np.gradient(v_arr, dt)

    @classmethod
    def generate_symmetric(
        cls,
        Tp: float,
        A: float,
        t0: float,
        dt: float,
        n: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        便捷方法：生成对称脉冲 (φ=0)。

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (velocity, acceleration)
        """
        params = PulseParams(Tp=Tp, A=A, phi=0.0, t0=t0)
        return cls.generate(params, dt, n)

    @classmethod
    def generate_one_sided(
        cls,
        Tp: float,
        A: float,
        t0: float,
        dt: float,
        n: int,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        便捷方法：生成单向脉冲 (φ=π/2)。

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (velocity, acceleration)
        """
        params = PulseParams(Tp=Tp, A=A, phi=np.pi / 2, t0=t0)
        return cls.generate(params, dt, n)

    @staticmethod
    def effective_duration(params: PulseParams) -> float:
        """
        返回脉冲有效持时 = γ·Tp (s)。

        有效区间为 [t0 - γ·Tp/2, t0 + γ·Tp/2]，长度为 γ·Tp。
        """
        return params.gamma * params.Tp

    @classmethod
    def peak_velocity(cls, v: np.ndarray) -> float:
        """速度时程峰值 (绝对值最大)"""
        return float(np.max(np.abs(v)))

    @classmethod
    def peak_acceleration(cls, a: np.ndarray) -> float:
        """加速度时程峰值 (绝对值最大)"""
        return float(np.max(np.abs(a)))


# ──────────────────── 便捷工厂函数 ────────────────────

def create_pulse(
    Mw: float,
    R: float,
    dt: float,
    n: int,
    fault_type: Literal["strike_slip", "normal", "reverse"] = "strike_slip",
    phi: Optional[float] = None,
    t_total: Optional[float] = None,
    Tp_override: Optional[float] = None,
    A_override: Optional[float] = None,
    phi_override: Optional[float] = None,
    t0_override: Optional[float] = None,
) -> Tuple[np.ndarray, np.ndarray, PulseParams]:
    """
    一站式脉冲生成：从震级/距离参数直接生成速度/加速度时程。

    Parameters
    ----------
    Mw : float
        矩震级
    R : float
        断层距 (km)
    dt : float
        时间步长 (s)
    n : int
        采样点数
    fault_type : str
        断层类型
    phi : float
        相位角 (rad)
    t_total : float, optional
        总持时 (s)，默认 n * dt

    Returns
    -------
    Tuple[np.ndarray, np.ndarray, PulseParams]
        (velocity, acceleration, params)
    """
    if t_total is None:
        t_total = n * dt
    params = PulseCalculator.compute_params(
        Mw=Mw, R=R, fault_type=fault_type, phi=phi, t_total=t_total,
        Tp_override=Tp_override, A_override=A_override,
        phi_override=phi_override, t0_override=t0_override,
    )
    v, a = PulseWavelet.generate(params, dt, n)
    return v, a, params


# ──────────────────── Baker (2007) 脉冲识别 ════════════════════

class BakerPulseDetector:
    """
    简化版 Baker (2007) 脉冲识别算法。

    识别策略：
    1. PGV 门槛：近场脉冲 PGV 通常 > 80 cm/s
    2. 若 PGV 低于门槛 → 直接判定为无脉冲
    3. 若 PGV 高于门槛 → 检查脉冲集中度（单峰 + 能量集中）

    参考：
    - Baker, J. W. (2007). Quantitative classification of near-fault
      ground motions using wavelet analysis. Bulletin of the Seismological
      Society of America, 97(5), 1486-1501.
    """

    # PGV 门槛：低于此值直接判定为无脉冲（工程典型脉冲 PGV > 100 cm/s）
    PGV_THRESHOLD_CM_S = 80.0

    # 脉冲集中度阈值
    CONCENTRATION_THRESHOLD = 0.35  # 适配合成 NFP 的脉冲集中度（残余分量速度累积较大）
    PGV_RATIO_THRESHOLD = 0.75      # 提高 PGV 比例门槛，确保脉冲确实主导峰值速度

    @classmethod
    def has_pulse(cls, vel: np.ndarray, dt: float) -> bool:
        """
        判断速度时程是否含显著脉冲。

        Parameters
        ----------
        vel : np.ndarray
            速度时程 (cm/s 或 m/s，单位一致即可)
        dt : float
            时间步长 (s)

        Returns
        -------
        bool
            True = 含显著脉冲，False = 无显著脉冲
        """
        metrics = cls.analyze(vel, dt)
        return bool(metrics["has_pulse"])

    @classmethod
    def analyze(cls, vel: np.ndarray, dt: float) -> dict:
        """
        分析速度时程的脉冲特征，返回完整指标。

        Returns
        -------
        dict
            {
                "has_pulse": bool,
                "pulse_period": float,      # 估计脉冲周期 (s)
                "pulse_amplitude": float,   # 脉冲幅值 (same unit as vel)
                "energy_ratio": float,      # 脉冲能量 / 总能量
                "pgv_ratio": float,         # 脉冲 PGV / 总 PGV
                "confidence": float,        # 置信度 0-1
            }
        """
        vel = np.asarray(vel, dtype=np.float64)
        n = len(vel)
        if n < 10:
            return cls._null_result()

        total_pgv = np.max(np.abs(vel))
        if total_pgv < cls.PGV_THRESHOLD_CM_S * 0.1:
            return cls._null_result()

        # 若 PGV 低于硬门槛，直接判定无脉冲
        if total_pgv < cls.PGV_THRESHOLD_CM_S:
            return {
                "has_pulse": False,
                "pulse_period": 0.0,
                "pulse_amplitude": float(total_pgv),
                "energy_ratio": 0.0,
                "pgv_ratio": 1.0,
                "confidence": 0.0,
            }

        # ── 脉冲集中度分析 ──
        # 找最大速度峰值位置
        idx_peak = int(np.argmax(np.abs(vel)))

        # 在多个窗口宽度上测试，找最佳集中度
        T_total = n * dt
        T_candidates = np.linspace(0.5, min(T_total / 3, 15.0), 30)

        best_conc = 0.0
        best_Tp = 0.0
        best_pgv_ratio = 0.0
        best_energy_ratio = 0.0

        for Tp in T_candidates:
            half_win = int(np.ceil(Tp / (2 * dt)))
            if half_win < 2:
                continue
            i1 = max(0, idx_peak - half_win)
            i2 = min(n, idx_peak + half_win + 1)
            if i2 - i1 < 4:
                continue

            window_vel = vel[i1:i2]
            window_pgv = np.max(np.abs(window_vel))
            window_energy = np.sum(window_vel ** 2) * dt
            total_energy = np.sum(vel ** 2) * dt + 1e-24

            # 集中度：窗口内累积绝对速度 / 总累积绝对速度
            cum_abs_window = np.sum(np.abs(window_vel)) * dt
            cum_abs_total = np.sum(np.abs(vel)) * dt + 1e-24
            concentration = cum_abs_window / cum_abs_total

            pgv_ratio = window_pgv / total_pgv if total_pgv > 0 else 0.0
            energy_ratio = window_energy / total_energy

            # 综合评分
            score = concentration * pgv_ratio

            if score > best_conc:
                best_conc = score
                best_Tp = Tp
                best_pgv_ratio = pgv_ratio
                best_energy_ratio = energy_ratio

        # 判定
        has_pulse = (
            best_conc > cls.CONCENTRATION_THRESHOLD
            and best_pgv_ratio > cls.PGV_RATIO_THRESHOLD
        )

        conf_conc = min(best_conc / cls.CONCENTRATION_THRESHOLD, 1.0)
        conf_pgv = min(best_pgv_ratio / cls.PGV_RATIO_THRESHOLD, 1.0)
        confidence = 0.5 * conf_conc + 0.5 * conf_pgv
        confidence = min(confidence, 1.0)

        return {
            "has_pulse": bool(has_pulse),
            "pulse_period": float(best_Tp),
            "pulse_amplitude": float(total_pgv),
            "energy_ratio": float(best_energy_ratio),
            "pgv_ratio": float(best_pgv_ratio),
            "confidence": float(confidence),
        }

    @classmethod
    def _null_result(cls) -> dict:
        return {
            "has_pulse": False,
            "pulse_period": 0.0,
            "pulse_amplitude": 0.0,
            "energy_ratio": 0.0,
            "pgv_ratio": 0.0,
            "confidence": 0.0,
        }