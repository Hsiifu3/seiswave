"""
简化版 GMPE 目标谱接口

基于 Abrahamson, Silva & Kamai (2014) NGA-West2 GMPE 的简化实现，
用于 SeisWave 特殊地震动生成功能的远场/近场目标谱计算。

参考：
- Abrahamson, N. A., Silva, W. J., & Kamai, R. (2014). Summary of the ASK14 ground
  motion relation for active crustal regions. Earthquake Spectra, 30(3), 1025-1055.
- FEMA P695: ATC-63 Project, Quantification of Building Seismic Performance Factors.

实现说明：
本模块为**简化版** GMPE，保留 ASK14 的核心物理项（震级、距离、场地、断层类型），
使用简化的系数集。工程精度量级正确，但不用于取代完整 GMPE 进行设计校核。
"""

from dataclasses import dataclass, field
from typing import Optional, Tuple, Literal
from enum import Enum
import numpy as np


# ──────────────────── 常量与枚举 ────────────────────

class FaultType(str, Enum):
    """断层类型"""
    STRIKE_SLIP = "strike_slip"
    NORMAL = "normal"
    REVERSE = "reverse"


class MotionType(str, Enum):
    """地震动类型（用于近场/远场参数调整）"""
    FAR_FIELD = "far_field"       # 远场
    NEAR_FIELD = "near_field"     # 近场（无脉冲）
    NEAR_FIELD_PULSE = "near_field_pulse"  # 近场脉冲


# ──────────────────── 参数数据类 ────────────────────

@dataclass
class GMPEParams:
    """GMPE 计算参数"""
    Mw: float
    """矩震级"""
    R: float
    """断层距 (km)"""
    Vs30: float
    """场地剪切波速 (m/s)"""
    fault_type: FaultType = FaultType.STRIKE_SLIP
    """断层类型"""
    motion_type: MotionType = MotionType.FAR_FIELD
    """地震动类型（影响近场/远场距离衰减调整）"""
    Ztor: float = 0.0
    """断层顶部埋深 (km)，默认 0"""
    dip: float = 90.0
    """断层倾角 (°)，默认 90°（走滑）"""
    hw: bool = False
    """是否位于断层上盘 (hanging wall)，默认 False"""

    def __post_init__(self):
        if not (4.5 <= self.Mw <= 8.5):
            raise ValueError(f"Mw 应在 4.5-8.5 范围内，得到 {self.Mw}")
        if self.R < 0:
            raise ValueError(f"R 必须 >= 0，得到 {self.R}")
        if not (150 <= self.Vs30 <= 2000):
            raise ValueError(f"Vs30 应在 150-2000 m/s 范围内，得到 {self.Vs30}")
        if not (0 <= self.dip <= 90):
            raise ValueError(f"dip 应在 0-90° 范围内，得到 {self.dip}")


# ──────────────────── 简化 ASK14 系数表 ────────────────────

# 选取 ASK14 中 8 个代表性周期点的系数（简化插值基础）
# 系数来源：ASK14 Table 2 关键周期点
_ASK14_PERIOD_TABLE = np.array([
    0.01, 0.05, 0.10, 0.20, 0.50, 1.00, 2.00, 5.00, 10.00
])

# 简化系数：a1(截距), b1(震级线性), b2(震级二次), c1(距离), c2(距离对数),
# Vlin(场地线性阈值), b(Vs30系数), c(断层类型系数)
_ASK14_COEFFS = {
    # period: (a1, b1, b2, c1, c2, Vlin, b, c_fault)
    0.01: (0.35,  0.60, -0.050, -0.60, -0.0020,  660.0, -0.50,  0.10),
    0.05: (0.40,  0.60, -0.050, -0.60, -0.0020,  660.0, -0.50,  0.10),
    0.10: (0.30,  0.60, -0.050, -0.55, -0.0020,  760.0, -0.60,  0.10),
    0.20: (0.10,  0.55, -0.050, -0.50, -0.0020,  760.0, -0.60,  0.08),
    0.50: (-0.30, 0.50, -0.045, -0.45, -0.0020,  800.0, -0.70,  0.06),
    1.00: (-0.80, 0.45, -0.040, -0.40, -0.0015,  800.0, -0.80,  0.04),
    2.00: (-1.40, 0.40, -0.035, -0.35, -0.0010,  800.0, -0.90,  0.02),
    5.00: (-2.50, 0.35, -0.030, -0.30, -0.0010,  800.0, -1.00,  0.00),
    10.0: (-3.20, 0.30, -0.025, -0.25, -0.0005,  800.0, -1.10,  0.00),
}

# 总标准差（简化，不分 tau/phi）
_ASK14_SIGMA = {
    0.01: 0.60, 0.05: 0.60, 0.10: 0.65, 0.20: 0.70,
    0.50: 0.75, 1.00: 0.80, 2.00: 0.85, 5.00: 0.90, 10.0: 0.95,
}

# 断层类型系数（ASK14 表 2 的简化）
_FAULT_COEFF_DELTA = {
    FaultType.STRIKE_SLIP: 0.0,
    FaultType.NORMAL: -0.15,
    FaultType.REVERSE: 0.10,
}

# ──────────────────── 核心计算 ────────────────────

def _interp_coeffs(period: float) -> Tuple[float, ...]:
    """线性插值获取指定周期的简化系数"""
    periods = _ASK14_PERIOD_TABLE
    if period <= periods[0]:
        return _ASK14_COEFFS[periods[0]]
    if period >= periods[-1]:
        return _ASK14_COEFFS[periods[-1]]

    # 找到左右边界
    idx = np.searchsorted(periods, period)
    T_left = periods[idx - 1]
    T_right = periods[idx]
    w = (period - T_left) / (T_right - T_left)

    c_left = _ASK14_COEFFS[T_left]
    c_right = _ASK14_COEFFS[T_right]
    return tuple(c_left[i] + w * (c_right[i] - c_left[i]) for i in range(len(c_left)))


def _interp_sigma(period: float) -> float:
    """线性插值获取指定周期的总标准差"""
    periods = _ASK14_PERIOD_TABLE
    sigmas = np.array([_ASK14_SIGMA[p] for p in periods])
    return np.interp(period, periods, sigmas)


def _site_term(Vs30: float, Vlin: float, b: float, period: float) -> float:
    """
    简化场地效应项（ASK14 式 5 的简化）。

    对 Vs30 >= Vlin：使用对数线性衰减
    对 Vs30 < Vlin：使用线性过渡（简化处理）
    """
    if Vs30 >= Vlin:
        return b * np.log(Vs30 / Vlin)
    else:
        # 简化：低波速场地放大，线性过渡到参考值
        # ASK14 原始公式较为复杂，这里用线性近似保持工程量级
        ratio = Vs30 / Vlin
        # 在极软场地（Vs30 -> 0）时，中长周期有约 0.3-0.5 的放大
        soft_amp = max(0.0, 0.3 - 0.05 * np.log(period + 0.01))
        return b * np.log(ratio) + soft_amp * (1.0 - ratio)


def _fault_term(fault_type: FaultType, Mw: float) -> float:
    """
    断层类型项（ASK14 表 2 的简化）。

    基于震级进行轻微调整：大震中断层类型效应更显著。
    """
    base = _FAULT_COEFF_DELTA[fault_type]
    # 大震时效应略增强
    scale = 1.0 + 0.05 * max(0.0, Mw - 6.5)
    return base * scale


def _distance_term(R: float, c1: float, c2: float, Mw: float,
                   motion_type: MotionType) -> float:
    """
    距离衰减项（简化版）。

    区分近场/远场：
    - 远场 (FF)：c4 较大，R_eff 更大，距离衰减更强（Sa 更小）
    - 近场 (NF/NFP)：c4 较小，R_eff 更接近真实 R，近场能量更集中
    """
    if motion_type == MotionType.FAR_FIELD:
        c4 = 5.0  # 远场饱和距离大，使 R_eff 更大、Sa 更小
    elif motion_type == MotionType.NEAR_FIELD:
        c4 = 1.0  # 近场饱和距离小
    else:  # NEAR_FIELD_PULSE
        c4 = 1.0  # 脉冲近场与 NF 相同，额外放大由 pulse_amp 处理
    R_eff = np.sqrt(R**2 + c4**2)
    return c1 * np.log(R_eff) + c2 * R_eff


def _magnitude_term(Mw: float, b1: float, b2: float) -> float:
    """
    震级项（ASK14 式 1 的简化）。

    包含线性项和二次项（震级饱和效应）。
    """
    return b1 * (Mw - 6.0) + b2 * (Mw - 6.0)**2


# ──────────────────── GMPEAdapter ────────────────────

class GMPEAdapter:
    """
    简化版 ASK14 GMPE 目标谱计算器。

    提供统一的 ``compute_spectrum`` 接口，输出周期-Sa 数组。
    支持远场/近场参数自动调整，以及用户自定义目标谱回退。
    """

    DEFAULT_PERIODS: np.ndarray = field(default_factory=lambda: np.array([]))
    """类属性：默认周期数组（在类体后初始化）"""

    @classmethod
    def default_periods(cls, n: int = 100) -> np.ndarray:
        """
        生成默认周期数组（对数均匀分布，0.1s - 10s）。

        工程常用范围，与典型人工波采样率(dt=0.02s, Nyquist=25Hz)兼容。
        避免 0.01s 等过短周期——dt=0.02s 时信号无法表达 100Hz 成分，
        强行匹配会导致谱失真。
        """
        return np.logspace(np.log10(0.1), np.log10(10.0), n)

    @classmethod
    def compute_spectrum(cls,
                         Mw: float,
                         R: float,
                         Vs30: float,
                         fault_type: FaultType = FaultType.STRIKE_SLIP,
                         motion_type: MotionType = MotionType.FAR_FIELD,
                         periods: Optional[np.ndarray] = None,
                         use_median: bool = True,
                         ) -> Tuple[np.ndarray, np.ndarray]:
        """
        计算简化 ASK14 目标谱。

        Parameters
        ----------
        Mw : float
            矩震级 (4.5 - 8.5)
        R : float
            断层距 (km)
        Vs30 : float
            场地剪切波速 (m/s)
        fault_type : FaultType
            断层类型，默认 STRIKE_SLIP
        motion_type : MotionType
            地震动类型，影响近场/远场距离衰减，默认 FAR_FIELD
        periods : np.ndarray, optional
            周期数组 (s)。若未提供，使用默认对数均匀分布 0.01-10s
        use_median : bool
            是否返回中位值（而非均值+1σ）。默认 True（中位值）。

        Returns
        -------
        Tuple[np.ndarray, np.ndarray]
            (periods, Sa) — Sa 单位为 g

        Raises
        ------
        ValueError
            参数超出合理范围
        """
        params = GMPEParams(
            Mw=Mw, R=R, Vs30=Vs30,
            fault_type=fault_type, motion_type=motion_type
        )

        if periods is None:
            periods = cls.default_periods()
        periods = np.asarray(periods, dtype=np.float64)
        if np.any(periods <= 0):
            raise ValueError("periods 必须全部 > 0")

        Sa = np.empty_like(periods)
        for i, T in enumerate(periods):
            a1, b1, b2, c1, c2, Vlin, b, c_fault = _interp_coeffs(T)
            sigma = _interp_sigma(T)

            f_mag = _magnitude_term(params.Mw, b1, b2)
            f_dist = _distance_term(params.R, c1, c2, params.Mw, params.motion_type)
            f_site = _site_term(params.Vs30, Vlin, b, T)
            f_fault = _fault_term(params.fault_type, params.Mw)

            ln_sa = a1 + f_mag + f_dist + f_site + f_fault

            # 近场脉冲额外调整：长周期放大
            if params.motion_type == MotionType.NEAR_FIELD_PULSE and T >= 0.5:
                pulse_amp = 0.15 * np.log(T / 0.5)  # 长周期脉冲放大
                ln_sa += pulse_amp

            if not use_median:
                ln_sa += sigma  # +1σ

            Sa[i] = np.exp(ln_sa)

        return periods, Sa

    @classmethod
    def compute_ff(cls,
                   Mw: float,
                   R: float,
                   Vs30: float = 760.0,
                   fault_type: FaultType = FaultType.STRIKE_SLIP,
                   periods: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """便捷方法：计算远场目标谱"""
        return cls.compute_spectrum(
            Mw, R, Vs30, fault_type=fault_type,
            motion_type=MotionType.FAR_FIELD, periods=periods
        )

    @classmethod
    def compute_nf(cls,
                     Mw: float,
                     R: float,
                     Vs30: float = 760.0,
                     fault_type: FaultType = FaultType.STRIKE_SLIP,
                     periods: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """便捷方法：计算近场（无脉冲）目标谱"""
        return cls.compute_spectrum(
            Mw, R, Vs30, fault_type=fault_type,
            motion_type=MotionType.NEAR_FIELD, periods=periods
        )

    @classmethod
    def compute_nfp(cls,
                    Mw: float,
                    R: float,
                    Vs30: float = 760.0,
                    fault_type: FaultType = FaultType.REVERSE,
                    periods: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
        """便捷方法：计算近场脉冲目标谱（长周期略放大）"""
        return cls.compute_spectrum(
            Mw, R, Vs30, fault_type=fault_type,
            motion_type=MotionType.NEAR_FIELD_PULSE, periods=periods
        )


# ──────────────────── 中国 GMPE：第五代区划图（GB18306-2015）────────────────────

# 俞言祥《新一代地震区划图地震动参数衰减关系的建立与特点分析》表4/表5。
# 模型（震级分段，界 M=6.5）：lg Y = A + B·M + C·lg(R + D·e^(E·M))
#   Y = aE（峰值加速度，gal）或 nE（拟速度平台值/2.5，cm/s）
#   M = 面波震级 Ms；R = 震中距(km)
# 由 aE/nE 构造 GB 设计谱：平台 αmax = 2.5·aE/g，特征周期 Tg = 2π·nE/aE。
# 每项系数 = (A_low, B_low, A_high, B_high, C, D, E)，D/E 在 aE 与 nE 间共用。
_GB18306_AE = {
    ("east_strong", "major"): (1.979, 0.671, 3.533, 0.432, -2.315, 2.088, 0.399),
    ("east_strong", "minor"): (1.176, 0.660, 2.753, 0.418, -2.004, 0.944, 0.447),
    ("moderate",    "major"): (2.417, 0.498, 3.706, 0.298, -2.079, 2.802, 0.295),
    ("moderate",    "minor"): (1.715, 0.471, 2.690, 0.321, -1.723, 1.295, 0.331),
    ("xinjiang",    "major"): (1.791, 0.720, 3.403, 0.472, -2.389, 1.772, 0.424),
    ("xinjiang",    "minor"): (0.983, 0.713, 2.610, 0.463, -2.118, 0.825, 0.465),
    ("tibet",       "major"): (2.387, 0.645, 3.807, 0.411, -2.416, 2.647, 0.366),
    ("tibet",       "minor"): (1.003, 0.609, 2.457, 0.388, -1.854, 0.612, 0.457),
}
_GB18306_NE = {
    ("east_strong", "major"): (-0.363, 0.791, 1.437, 0.513, -2.103, 2.088, 0.399),
    ("east_strong", "minor"): (-1.147, 0.788, 0.712, 0.502, -1.825, 0.944, 0.447),
    ("moderate",    "major"): (0.093, 0.621, 1.640, 0.382, -1.889, 2.802, 0.295),
    ("moderate",    "minor"): (-0.589, 0.601, 0.671, 0.407, -1.559, 1.295, 0.331),
    ("xinjiang",    "major"): (-0.547, 0.840, 1.310, 0.554, -2.181, 1.772, 0.424),
    ("xinjiang",    "minor"): (-1.351, 0.843, 0.569, 0.549, -1.945, 0.825, 0.465),
    ("tibet",       "major"): (-0.064, 0.766, 1.714, 0.491, -2.205, 2.647, 0.366),
    ("tibet",       "minor"): (-1.301, 0.741, 0.443, 0.474, -1.696, 0.612, 0.457),
}

# 分区名归一化（接受中文/英文/别名）
_GB18306_REGION_ALIASES = {
    "east_strong": "east_strong", "东部强震区": "east_strong", "east": "east_strong",
    "moderate": "moderate", "中强地震区": "moderate", "中强": "moderate",
    "xinjiang": "xinjiang", "新疆区": "xinjiang", "新疆": "xinjiang",
    "tibet": "tibet", "青藏区": "tibet", "青藏": "tibet",
}
_GB18306_AXIS_ALIASES = {
    "major": "major", "长轴": "major", "长": "major",
    "minor": "minor", "短轴": "minor", "短": "minor",
}

_G_CM_S2 = 980.665  # 1g = 980.665 cm/s²
_BETA_MAX = 2.5     # GB18306 动力放大系数（aE = 平台值/2.5）


class ChinaGMPEAdapter:
    """中国地震动衰减关系（第五代区划图 GB18306-2015，俞言祥分区模型）。

    产出与 GB50011/GB18306 设计谱一致的反应谱：由分区衰减得到峰值加速度 aE
    与速度参数 nE，构造平台 αmax=2.5·aE/g、特征周期 Tg=2π·nE/aE 的 GB 设计谱。
    适用：M=4.5~8.0（中强地震区 4.5~7.0），R=0~200km。
    """

    REGIONS = ("east_strong", "moderate", "xinjiang", "tibet")
    AXES = ("major", "minor")

    @staticmethod
    def _norm_region(region):
        return _GB18306_REGION_ALIASES.get(str(region), "east_strong")

    @staticmethod
    def _norm_axis(axis):
        return _GB18306_AXIS_ALIASES.get(str(axis), "major")

    @staticmethod
    def _attenuate(coef, M, R):
        """lg Y = A + B·M + C·lg(R + D·e^(E·M))，返回 Y（gal 或 cm/s）。"""
        a_lo, b_lo, a_hi, b_hi, c, d, e = coef
        A, B = (a_lo, b_lo) if M <= 6.5 else (a_hi, b_hi)
        lg_y = A + B * M + c * np.log10(R + d * np.exp(e * M))
        return 10.0 ** lg_y

    @classmethod
    def compute_params(cls, Mw, R, region="east_strong", axis="major"):
        """返回 (PGA_g, alpha_max_g, Tg_s) — GB 设计谱构造参数。"""
        region = cls._norm_region(region)
        axis = cls._norm_axis(axis)
        M = float(Mw)
        R = max(float(R), 0.0)
        aE = cls._attenuate(_GB18306_AE[(region, axis)], M, R)   # gal
        nE = cls._attenuate(_GB18306_NE[(region, axis)], M, R)   # cm/s
        pga_g = aE / _G_CM_S2
        alpha_max = _BETA_MAX * aE / _G_CM_S2                     # 平台 Sa/g
        Tg = (2.0 * np.pi * nE / aE) if aE > 1e-12 else 0.4
        return pga_g, alpha_max, Tg

    @classmethod
    def compute_spectrum(cls, Mw, R, region="east_strong", axis="major",
                         periods=None, zeta=0.05, **kwargs):
        """计算第五代区划情景 GB 设计谱，返回 (periods, Sa[g])。"""
        from .code_spec import CodeSpectrum
        pga_g, alpha_max, Tg = cls.compute_params(Mw, R, region, axis)
        if periods is None:
            periods = np.geomspace(0.01, 6.0, 300)
        periods = np.asarray(periods, dtype=np.float64)
        sa = CodeSpectrum.gb50011(periods, Tg, alpha_max, zeta=zeta)
        return periods, sa


# ──────────────────── 预设标准参数集（FEMA P695 典型场景） ────────────────────

@dataclass
class FEMAP695Scenario:
    """FEMA P695 典型分析场景"""
    name: str
    Mw: float
    R: float
    Vs30: float
    fault_type: FaultType
    motion_type: MotionType
    description: str = ""


FEMA_P695_SCENARIOS: list[FEMAP695Scenario] = [
    FEMAP695Scenario(
        name="FF_M7_R50_SS",
        Mw=7.0, R=50.0, Vs30=760.0,
        fault_type=FaultType.STRIKE_SLIP,
        motion_type=MotionType.FAR_FIELD,
        description="远场走滑断层，M7.0，R50km，Vs30=760m/s",
    ),
    FEMAP695Scenario(
        name="FF_M6.5_R30_SS",
        Mw=6.5, R=30.0, Vs30=520.0,
        fault_type=FaultType.STRIKE_SLIP,
        motion_type=MotionType.FAR_FIELD,
        description="远场走滑断层，M6.5，R30km，Vs30=520m/s (C类场地)",
    ),
    FEMAP695Scenario(
        name="NF_M7_R5_SS",
        Mw=7.0, R=5.0, Vs30=760.0,
        fault_type=FaultType.STRIKE_SLIP,
        motion_type=MotionType.NEAR_FIELD,
        description="近场走滑断层，M7.0，R5km，Vs30=760m/s",
    ),
    FEMAP695Scenario(
        name="NF_M6.5_R3_N",
        Mw=6.5, R=3.0, Vs30=760.0,
        fault_type=FaultType.NORMAL,
        motion_type=MotionType.NEAR_FIELD,
        description="近场正断层，M6.5，R3km，Vs30=760m/s",
    ),
    FEMAP695Scenario(
        name="NFP_M7.5_R3_R",
        Mw=7.5, R=3.0, Vs30=760.0,
        fault_type=FaultType.REVERSE,
        motion_type=MotionType.NEAR_FIELD_PULSE,
        description="近场脉冲逆断层，M7.5，R3km，Vs30=760m/s",
    ),
    FEMAP695Scenario(
        name="NFP_M7_R2_SS",
        Mw=7.0, R=2.0, Vs30=520.0,
        fault_type=FaultType.STRIKE_SLIP,
        motion_type=MotionType.NEAR_FIELD_PULSE,
        description="近场脉冲走滑断层，M7.0，R2km，Vs30=520m/s",
    ),
]


def get_fema_scenario(name: str) -> FEMAP695Scenario:
    """
    按名称获取 FEMA P695 预设场景。

    Parameters
    ----------
    name : str
        场景名称（如 "FF_M7_R50_SS"）

    Returns
    -------
    FEMAP695Scenario

    Raises
    ------
    ValueError
        未知场景名称
    """
    for s in FEMA_P695_SCENARIOS:
        if s.name == name:
            return s
    available = [s.name for s in FEMA_P695_SCENARIOS]
    raise ValueError(f"未知场景 '{name}'。可用场景: {available}")


def compute_fema_spectrum(name: str,
                          periods: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """
    计算指定 FEMA P695 场景的目标谱。

    Parameters
    ----------
    name : str
        场景名称
    periods : np.ndarray, optional
        周期数组，默认 0.01-10s 对数均匀 100 点

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        (periods, Sa)
    """
    scenario = get_fema_scenario(name)
    return GMPEAdapter.compute_spectrum(
        Mw=scenario.Mw,
        R=scenario.R,
        Vs30=scenario.Vs30,
        fault_type=scenario.fault_type,
        motion_type=scenario.motion_type,
        periods=periods,
    )


# ──────────────────── 自定义目标谱 ────────────────────

@dataclass
class CustomSpectrum:
    """
    用户自定义目标谱容器。

    当用户不想使用 GMPE，而是直接提供设计谱或规范谱时使用。
    """
    periods: np.ndarray
    """周期数组 (s)"""
    Sa: np.ndarray
    """谱加速度 (g 或其他一致单位)"""
    name: str = "custom"
    """谱名称"""

    def __post_init__(self):
        self.periods = np.asarray(self.periods, dtype=np.float64)
        self.Sa = np.asarray(self.Sa, dtype=np.float64)
        if len(self.periods) != len(self.Sa):
            raise ValueError("periods 和 Sa 长度必须相同")
        if len(self.periods) == 0:
            raise ValueError("periods 不能为空")
        if np.any(self.periods <= 0):
            raise ValueError("periods 必须全部 > 0")
        if np.any(self.Sa < 0):
            raise ValueError("Sa 必须 >= 0")

    def interpolate(self, target_periods: np.ndarray) -> np.ndarray:
        """
        将自定义谱插值到目标周期数组（对数线性插值）。

        Parameters
        ----------
        target_periods : np.ndarray
            目标周期数组 (s)

        Returns
        -------
        np.ndarray
            插值后的 Sa
        """
        target_periods = np.asarray(target_periods, dtype=np.float64)
        log_T = np.log(self.periods)
        log_Sa = np.log(self.Sa + 1e-12)  # 防止 log(0)
        log_target = np.log(target_periods)
        log_sa_interp = np.interp(log_target, log_T, log_Sa)
        return np.exp(log_sa_interp)


# ──────────────────── 统一入口（供 Generator 调用） ────────────────────

def get_target_spectrum(
    source: Literal["gmpe", "custom", "fema"],
    periods: Optional[np.ndarray] = None,
    *,
    Mw: Optional[float] = None,
    R: Optional[float] = None,
    Vs30: Optional[float] = None,
    fault_type: Optional[FaultType] = None,
    motion_type: Optional[MotionType] = None,
    custom_spec: Optional[CustomSpectrum] = None,
    fema_name: Optional[str] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    统一目标谱获取入口。

    根据 source 类型自动分发到 GMPE、自定义谱或 FEMA 预设。

    Parameters
    ----------
    source : {"gmpe", "custom", "fema"}
        目标谱来源类型
    periods : np.ndarray, optional
        目标周期数组。对 "gmpe" 和 "fema" 为可选（默认 0.01-10s），
        对 "custom" 若提供则用于插值，否则返回 custom_spec 原始周期。
    Mw, R, Vs30, fault_type, motion_type : optional
        GMPE 计算参数（source="gmpe" 时必填）
    custom_spec : CustomSpectrum, optional
        用户自定义谱（source="custom" 时必填）
    fema_name : str, optional
        FEMA 场景名称（source="fema" 时必填）

    Returns
    -------
    Tuple[np.ndarray, np.ndarray]
        (periods, Sa)

    Raises
    ------
    ValueError
        参数缺失或不一致
    """
    if source == "gmpe":
        if Mw is None or R is None or Vs30 is None:
            raise ValueError("source='gmpe' 时必须提供 Mw, R, Vs30")
        ft = fault_type or FaultType.STRIKE_SLIP
        mt = motion_type or MotionType.FAR_FIELD
        return GMPEAdapter.compute_spectrum(
            Mw=Mw, R=R, Vs30=Vs30,
            fault_type=ft, motion_type=mt, periods=periods
        )

    elif source == "custom":
        if custom_spec is None:
            raise ValueError("source='custom' 时必须提供 custom_spec")
        if periods is not None:
            Sa_interp = custom_spec.interpolate(periods)
            return periods, Sa_interp
        else:
            return custom_spec.periods, custom_spec.Sa

    elif source == "fema":
        if fema_name is None:
            raise ValueError("source='fema' 时必须提供 fema_name")
        return compute_fema_spectrum(fema_name, periods=periods)

    else:
        raise ValueError(f"未知的 source '{source}'，可选: gmpe, custom, fema")


# ──────────────────── 导出别名（兼容旧调用） ────────────────────

def compute_gmpe_spectrum(Mw: float, R: float, Vs30: float,
                          fault_type: str = "strike_slip",
                          motion_type: str = "far_field",
                          periods: Optional[np.ndarray] = None) -> Tuple[np.ndarray, np.ndarray]:
    """
    兼容旧接口的便捷函数（字符串参数）。

    Parameters
    ----------
    fault_type : str
        "strike_slip" | "normal" | "reverse"
    motion_type : str
        "far_field" | "near_field" | "near_field_pulse"
    """
    ft_map = {
        "strike_slip": FaultType.STRIKE_SLIP,
        "normal": FaultType.NORMAL,
        "reverse": FaultType.REVERSE,
    }
    mt_map = {
        "far_field": MotionType.FAR_FIELD,
        "near_field": MotionType.NEAR_FIELD,
        "near_field_pulse": MotionType.NEAR_FIELD_PULSE,
    }
    ft = ft_map.get(fault_type, FaultType.STRIKE_SLIP)
    mt = mt_map.get(motion_type, MotionType.FAR_FIELD)
    return GMPEAdapter.compute_spectrum(Mw, R, Vs30, fault_type=ft,
                                        motion_type=mt, periods=periods)
