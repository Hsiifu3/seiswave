"""
GB 50011 设计反应谱模块 / GB 50011 Design Response Spectrum Module.

参考 MATLAB: matlab_ref/选取地震波/8度0.2g硬土场地/alpha_standspectrum.m
参考 MATLAB: matlab_ref/步骤一/DiZhenYingXiangXiShu_alpha_GeZhen.m
"""

from __future__ import annotations

import numpy as np


class CodeSpectrum:
    """规范设计反应谱 / Code-based design response spectrum."""

    # 设计地震分组 x 场地类别 -> 特征周期 Tg (s)
    # Design earthquake group x site class -> characteristic period Tg (s)
    GB_TG = {
        1: {"I0": 0.20, "I1": 0.25, "II": 0.35, "III": 0.45, "IV": 0.65},
        2: {"I0": 0.25, "I1": 0.30, "II": 0.40, "III": 0.55, "IV": 0.75},
        3: {"I0": 0.30, "I1": 0.35, "II": 0.45, "III": 0.65, "IV": 0.90},
    }

    # 地震水准 x 抗震设防烈度 -> alpha_max
    # Seismic level x intensity -> alpha_max
    GB_ALPHA_MAX = {
        "frequent": {6: 0.04, 7: 0.08, 7.5: 0.12, 8: 0.16, 8.5: 0.24, 9: 0.32},
        "basic": {6: 0.12, 7: 0.23, 7.5: 0.34, 8: 0.45, 8.5: 0.68, 9: 0.90},
        "rare": {6: 0.28, 7: 0.50, 7.5: 0.72, 8: 0.90, 8.5: 1.20, 9: 1.40},
    }

    @staticmethod
    def gb50011(
        periods: np.ndarray,
        Tg: float,
        alpha_max: float,
        zeta: float = 0.05,
        isolation: bool = False,
    ) -> np.ndarray:
        """
        GB 50011 规范谱（抗震四段式 / 隔震三段式）。
        GB 50011 code spectrum (4 segments for regular / 3 segments for isolation).

        分段定义 / Segment definition:
        1) T < 0.1:        线性上升段 / linear rise
        2) 0.1 <= T <= Tg: 平台段 / plateau
        3) Tg < T <= 5Tg:  曲线下降段 / curved decay
        4) 5Tg < T <= 6.0: 直线下降段（仅抗震）/ linear decay (regular only)

        Parameters
        ----------
        periods : np.ndarray
            周期数组 (s) / Period array (s)
        Tg : float
            特征周期 (s) / Characteristic period (s)
        alpha_max : float
            地震影响系数最大值 / Maximum influence coefficient
        zeta : float
            阻尼比 / Damping ratio
        isolation : bool
            是否隔震谱 / Isolation spectrum flag

        Returns
        -------
        np.ndarray
            地震影响系数数组 / Influence coefficient array
        """
        periods = np.asarray(periods, dtype=np.float64)

        gamma = 0.9 + (0.05 - zeta) / (0.3 + 6.0 * zeta)
        eta1 = 0.02 + (0.05 - zeta) / (4.0 + 32.0 * zeta)
        eta2 = 1.0 + (0.05 - zeta) / (0.08 + 1.6 * zeta)

        eta1 = max(eta1, 0.0)
        eta2 = max(eta2, 0.55)

        alpha = np.zeros_like(periods, dtype=np.float64)

        mask1 = periods < 0.1
        alpha[mask1] = 0.45 * alpha_max + (periods[mask1] / 0.1) * (
            eta2 * alpha_max - 0.45 * alpha_max
        )

        mask2 = (periods >= 0.1) & (periods <= Tg)
        alpha[mask2] = eta2 * alpha_max

        if isolation:
            mask3 = (periods > Tg) & (periods <= 6.0)
            alpha[mask3] = eta2 * alpha_max * (Tg / periods[mask3]) ** gamma
        else:
            mask3 = (periods > Tg) & (periods <= 5.0 * Tg)
            alpha[mask3] = eta2 * alpha_max * (Tg / periods[mask3]) ** gamma

            mask4 = (periods > 5.0 * Tg) & (periods <= 6.0)
            alpha[mask4] = alpha_max * (
                eta2 * (0.2 ** gamma) - eta1 * (periods[mask4] - 5.0 * Tg)
            )

        np.clip(alpha, 0.0, None, out=alpha)
        return alpha

    @staticmethod
    def get_params(
        intensity: float,
        group: int,
        site_class: str,
        level: str,
    ) -> dict:
        """
        查表获取 Tg 与 alpha_max。
        Look up Tg and alpha_max from code tables.

        Parameters
        ----------
        intensity : float
            抗震设防烈度 / Seismic intensity (6, 7, 7.5, 8, 8.5, 9)
        group : int
            设计地震分组 / Design earthquake group (1, 2, 3)
        site_class : str
            场地类别 / Site class (I0, I1, II, III, IV)
        level : str
            地震水准 / Seismic level (frequent/basic/rare)

        Returns
        -------
        dict
            {"Tg": float, "alpha_max": float}
        """
        if group not in CodeSpectrum.GB_TG:
            raise KeyError(
                f"无效的分组: group={group}. 可选值: {list(CodeSpectrum.GB_TG.keys())}"
            )

        group_table = CodeSpectrum.GB_TG[group]
        if site_class not in group_table:
            raise KeyError(
                f"无效的场地类别: site_class='{site_class}'. 可选值: {list(group_table.keys())}"
            )

        if level not in CodeSpectrum.GB_ALPHA_MAX:
            raise KeyError(
                f"无效的地震水准: level='{level}'. 可选值: {list(CodeSpectrum.GB_ALPHA_MAX.keys())}"
            )

        level_table = CodeSpectrum.GB_ALPHA_MAX[level]
        if intensity not in level_table:
            raise KeyError(
                f"无效的设防烈度: intensity={intensity}. 可选值: {list(level_table.keys())}"
            )

        return {"Tg": group_table[site_class], "alpha_max": level_table[intensity]}

    @staticmethod
    def from_params(
        periods: np.ndarray,
        intensity: float,
        group: int,
        site_class: str,
        level: str,
        zeta: float = 0.05,
        isolation: bool = False,
    ) -> np.ndarray:
        """
        根据设防参数生成规范谱。
        Generate spectrum from seismic design parameters.

        Parameters
        ----------
        periods : np.ndarray
            周期数组 (s) / Period array (s)
        intensity : float
            抗震设防烈度 / Seismic intensity
        group : int
            设计地震分组 / Design earthquake group
        site_class : str
            场地类别 / Site class
        level : str
            地震水准 / Seismic level
        zeta : float
            阻尼比 / Damping ratio
        isolation : bool
            是否隔震谱 / Isolation spectrum flag

        Returns
        -------
        np.ndarray
            地震影响系数数组 / Influence coefficient array
        """
        params = CodeSpectrum.get_params(intensity, group, site_class, level)
        return CodeSpectrum.gb50011(
            periods,
            params["Tg"],
            params["alpha_max"],
            zeta=zeta,
            isolation=isolation,
        )
