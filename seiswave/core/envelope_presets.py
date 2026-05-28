"""
地震动包络参数预设模块

定义 Far-Field (FF)、Near-Field No-Pulse (NF)、Near-Field Pulse (NFP)
三类地震动的强度包络参数预设，基于 Saragoni & Hart (1974) 型分段幂-指数包络。

包络函数形式：
    上升段 (0 <= t <= t1):  E(t) = (t/t1)^n
    衰减段 (t > t1):        E(t) = exp(-(t-t1)/τ)

其中 τ 由 t2 和衰减阈值确定：τ = -(t2 - t1) / ln(threshold)
默认 threshold = 0.05，即 t2 时刻包络幅值为峰值的 5%。

参考：
- Saragoni, A. D., & Hart, G. C. (1974). Simulation of artificial earthquakes.
  Earthquake Engineering & Structural Dynamics, 2(3), 249-267.
- plan.md / spec.md: Feature-001 特殊地震动生成功能
"""

from dataclasses import dataclass, field, replace
from typing import Optional, Dict, Any
import numpy as np


# ──────────────────── 参数数据类 ────────────────────

@dataclass(frozen=True)
class EnvelopeParams:
    """地震动包络参数（不可变，通过 replace 创建变体）"""

    t1: float
    """峰值时间 (s)：包络达到最大值 1.0 的时间点"""

    t2: float
    """衰减特征时间 (s)：包络衰减到 threshold 的时间点，必须 > t1"""

    rise_power: float = 2.0
    """上升幂次 n：(t/t1)^n 控制上升陡峭度。
    n 越大上升越尖锐；远场通常 1.0-2.0，脉冲通常 3.0-6.0。"""

    decay_threshold: float = 0.05
    """衰减阈值 (0-1)：t2 时刻包络幅值相对于峰值的比例。默认 0.05。"""

    name: str = ""
    """参数集名称（可选，用于调试/日志）"""

    def __post_init__(self):
        if self.t1 <= 0:
            raise ValueError(f"t1 must be positive, got {self.t1}")
        if self.t2 <= self.t1:
            raise ValueError(f"t2 ({self.t2}) must be greater than t1 ({self.t1})")
        if self.rise_power <= 0:
            raise ValueError(f"rise_power must be positive, got {self.rise_power}")
        if not (0 < self.decay_threshold < 1):
            raise ValueError(
                f"decay_threshold must be in (0, 1), got {self.decay_threshold}"
            )

    @property
    def tau(self) -> float:
        """衰减时间常数 τ (s)"""
        return -(self.t2 - self.t1) / np.log(self.decay_threshold)

    def with_overrides(self, **kwargs) -> "EnvelopeParams":
        """返回一个参数被用户覆盖后的新实例（原实例不变）。"""
        # 过滤掉 None 值，只覆盖明确提供的参数
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean)


# ──────────────────── 预设参数常量 ────────────────────

# Far-Field: t1=2-5s, t2=15-40s, 衰减慢（rise_power 较小）
FARFIELD_DEFAULT = EnvelopeParams(
    t1=3.5,
    t2=27.5,
    rise_power=1.5,
    name="FarField",
)

# Near-Field No-Pulse: t1=0.5-2s, t2=10-25s
NEARFIELD_DEFAULT = EnvelopeParams(
    t1=1.25,
    t2=17.5,
    rise_power=2.5,
    name="NearField",
)

# Near-Field Pulse: t1=0.2-1s, t2=5-15s, 尖锐上升（rise_power 较大）
PULSE_DEFAULT = EnvelopeParams(
    t1=0.6,
    t2=10.0,
    rise_power=4.0,
    name="Pulse",
)


# ──────────────────── 包络生成器 ────────────────────

class EnvelopeGenerator:
    """
    基于 EnvelopeParams 生成包络函数并应用于时程。
    """

    def __init__(self, params: EnvelopeParams):
        self.params = params

    # ── 包络计算 ──

    def envelope(self, t: np.ndarray) -> np.ndarray:
        """
        计算包络函数 E(t)。

        Parameters
        ----------
        t : np.ndarray
            时间数组 (s)，可为任意形状。

        Returns
        -------
        np.ndarray
            与 t 同形状的包络值数组，范围 [0, 1]。
        """
        t = np.asarray(t, dtype=np.float64)
        p = self.params
        tau = p.tau

        E = np.zeros_like(t)

        # 上升段: 0 <= t <= t1
        rise_mask = (t >= 0) & (t <= p.t1)
        if np.any(rise_mask):
            E[rise_mask] = (t[rise_mask] / p.t1) ** p.rise_power

        # 衰减段: t > t1
        decay_mask = t > p.t1
        if np.any(decay_mask):
            E[decay_mask] = np.exp(-(t[decay_mask] - p.t1) / tau)

        return E

    def envelope_at(self, n: int, dt: float, t0: float = 0.0) -> np.ndarray:
        """
        生成长度为 n、时间步 dt 的包络数组。

        Parameters
        ----------
        n : int
            采样点数
        dt : float
            时间步长 (s)
        t0 : float
            起始时间偏移 (s)，默认 0

        Returns
        -------
        np.ndarray
            形状 (n,) 的包络数组
        """
        t = np.arange(n, dtype=np.float64) * dt + t0
        return self.envelope(t)

    # ── 应用包络 ──

    def apply(self, acc: np.ndarray, dt: float, t0: float = 0.0) -> np.ndarray:
        """
        将包络调制到加速度时程上（逐点相乘）。

        Parameters
        ----------
        acc : np.ndarray
            原始加速度时程
        dt : float
            时间步长 (s)
        t0 : float
            包络起始时间偏移 (s)，用于将包络峰值对齐到强震时段

        Returns
        -------
        np.ndarray
            调制后的加速度时程
        """
        acc = np.asarray(acc, dtype=np.float64)
        env = self.envelope_at(len(acc), dt, t0=t0)
        return acc * env

    def apply_with_normalize(
        self, acc: np.ndarray, dt: float, t0: float = 0.0, target_pga: float = None
    ) -> np.ndarray:
        """
        应用包络并可选归一化到目标 PGA。

        Parameters
        ----------
        acc : np.ndarray
            原始加速度时程
        dt : float
            时间步长 (s)
        t0 : float
            包络起始偏移 (s)
        target_pga : float, optional
            若提供，调制后将结果缩放到该 PGA

        Returns
        -------
        np.ndarray
            调制后（并可能缩放）的加速度时程
        """
        mod = self.apply(acc, dt, t0=t0)
        if target_pga is not None and target_pga > 0:
            pga = np.max(np.abs(mod))
            if pga > 0:
                mod = mod * (target_pga / pga)
        return mod

    # ── 分析属性 ──

    @property
    def peak_time(self) -> float:
        """包络峰值时间 = t1 (s)"""
        return self.params.t1

    @property
    def tau(self) -> float:
        """衰减时间常数 τ (s)"""
        return self.params.tau

    @property
    def effective_duration(self) -> float:
        """
        基于 5%-95% 能量累积的有效持时估计 (s)。
        数值积分计算包络平方的累积分布。
        """
        # 积分到 5*tau + t1 已足够覆盖衰减尾部
        t_max = self.params.t1 + 5 * self.params.tau
        n = max(10000, int(t_max / 0.001))
        dt = t_max / n
        t = np.arange(n) * dt
        E = self.envelope(t)
        energy = np.cumsum(E ** 2) * dt
        total = energy[-1]
        if total == 0:
            return 0.0
        i5 = np.searchsorted(energy, 0.05 * total)
        i95 = np.searchsorted(energy, 0.95 * total)
        return (i95 - i5) * dt

    def __repr__(self) -> str:
        p = self.params
        return (
            f"EnvelopeGenerator({p.name or 'custom'}: "
            f"t1={p.t1:.2f}s, t2={p.t2:.2f}s, "
            f"rise_power={p.rise_power:.1f}, tau={self.tau:.2f}s)"
        )


# ──────────────────── 便捷预设工厂 ────────────────────

class FarFieldEnvelope(EnvelopeGenerator):
    """
    远场地震动包络预设。

    特征：峰值时间较晚 (t1=2-5s)，衰减慢，适合远场长持时地震动。
    默认参数：t1=3.5s, t2=27.5s, rise_power=1.5。

    用户可覆盖任何参数：
        FarFieldEnvelope(t1=4.0, t2=30.0, rise_power=1.2)
    """

    def __init__(
        self,
        t1: Optional[float] = None,
        t2: Optional[float] = None,
        rise_power: Optional[float] = None,
        decay_threshold: Optional[float] = None,
    ):
        params = FARFIELD_DEFAULT.with_overrides(
            t1=t1, t2=t2, rise_power=rise_power, decay_threshold=decay_threshold
        )
        super().__init__(params)


class NearFieldEnvelope(EnvelopeGenerator):
    """
    近场无脉冲地震动包络预设。

    特征：峰值时间中等 (t1=0.5-2s)，衰减中等，高频成分相对丰富。
    默认参数：t1=1.25s, t2=17.5s, rise_power=2.5。

    用户可覆盖任何参数：
        NearFieldEnvelope(t1=1.5, t2=20.0, rise_power=2.0)
    """

    def __init__(
        self,
        t1: Optional[float] = None,
        t2: Optional[float] = None,
        rise_power: Optional[float] = None,
        decay_threshold: Optional[float] = None,
    ):
        params = NEARFIELD_DEFAULT.with_overrides(
            t1=t1, t2=t2, rise_power=rise_power, decay_threshold=decay_threshold
        )
        super().__init__(params)


class PulseEnvelope(EnvelopeGenerator):
    """
    近场脉冲地震动包络预设。

    特征：峰值时间极短 (t1=0.2-1s)，上升尖锐 (rise_power 大)，
    适合模拟脉冲型地震动的尖锐速度脉冲前导。
    默认参数：t1=0.6s, t2=10.0s, rise_power=4.0。

    用户可覆盖任何参数：
        PulseEnvelope(t1=0.8, t2=12.0, rise_power=5.0)
    """

    def __init__(
        self,
        t1: Optional[float] = None,
        t2: Optional[float] = None,
        rise_power: Optional[float] = None,
        decay_threshold: Optional[float] = None,
    ):
        params = PULSE_DEFAULT.with_overrides(
            t1=t1, t2=t2, rise_power=rise_power, decay_threshold=decay_threshold
        )
        super().__init__(params)


# ──────────────────── 统一入口（可选） ────────────────────

_ENVELOPE_REGISTRY: Dict[str, EnvelopeGenerator] = {
    "far_field": FarFieldEnvelope(),
    "near_field": NearFieldEnvelope(),
    "pulse": PulseEnvelope(),
}


def get_envelope(
    motion_type: str,
    t1: Optional[float] = None,
    t2: Optional[float] = None,
    rise_power: Optional[float] = None,
    decay_threshold: Optional[float] = None,
) -> EnvelopeGenerator:
    """
    通过字符串名称获取包络生成器（支持用户覆盖参数）。

    Parameters
    ----------
    motion_type : str
        "far_field" | "near_field" | "pulse" （不区分大小写）
    t1, t2, rise_power, decay_threshold : float, optional
        覆盖默认参数的值

    Returns
    -------
    EnvelopeGenerator

    Raises
    ------
    ValueError
        未知的 motion_type
    """
    key = motion_type.lower().strip()
    mapping = {
        "far_field": FarFieldEnvelope,
        "ff": FarFieldEnvelope,
        "near_field": NearFieldEnvelope,
        "nf": NearFieldEnvelope,
        "pulse": PulseEnvelope,
        "nfp": PulseEnvelope,
    }
    cls = mapping.get(key)
    if cls is None:
        raise ValueError(
            f"Unknown motion_type '{motion_type}'. "
            f"Supported: {list(mapping.keys())}"
        )
    return cls(
        t1=t1, t2=t2, rise_power=rise_power, decay_threshold=decay_threshold
    )
