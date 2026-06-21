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
            mask3 = periods > Tg
            alpha[mask3] = eta2 * alpha_max * (Tg / periods[mask3]) ** gamma
        else:
            mask3 = (periods > Tg) & (periods <= 5.0 * Tg)
            alpha[mask3] = eta2 * alpha_max * (Tg / periods[mask3]) ** gamma

            # 第四段直线下降。GB50011 仅定义至 6s，但目标谱若在 6s 处归零会出现
            # 断崖、破坏匹配；故沿用规范公式延伸至全部 T>5Tg，并由末尾 clip 限于 ≥0，
            # 实现 6s 之后的平滑延续（工程常用做法，§5.1.5 注 5 之外的连续化处理）。
            mask4 = periods > 5.0 * Tg
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
    def eurocode8(
        periods: np.ndarray,
        ag: float,
        soil_type: str = "B",
        spectrum_type: int = 1,
        zeta: float = 0.05,
    ) -> np.ndarray:
        """
        Eurocode 8 弹性反应谱。
        Eurocode 8 elastic response spectrum (EN 1998-1).

        Parameters
        ----------
        periods : np.ndarray
            周期数组 (s)
        ag : float
            设计地面加速度 (g)
        soil_type : str
            场地类别 A/B/C/D/E
        spectrum_type : int
            谱类型 1 或 2
        zeta : float
            阻尼比

        Returns
        -------
        np.ndarray
            弹性反应谱 Se/g
        """
        # EC8 Table 3.2 / 3.3
        params = {
            1: {
                "A": (1.0, 0.15, 0.4, 2.0),
                "B": (1.2, 0.15, 0.5, 2.0),
                "C": (1.15, 0.20, 0.6, 2.0),
                "D": (1.35, 0.20, 0.8, 2.0),
                "E": (1.4, 0.15, 0.5, 2.0),
            },
            2: {
                "A": (1.0, 0.05, 0.25, 1.2),
                "B": (1.35, 0.05, 0.25, 1.2),
                "C": (1.5, 0.10, 0.25, 1.2),
                "D": (1.8, 0.10, 0.30, 1.2),
                "E": (1.6, 0.05, 0.25, 1.2),
            },
        }

        if spectrum_type not in params:
            raise ValueError(f"无效的谱类型: {spectrum_type}, 可选 1 或 2")
        if soil_type not in params[spectrum_type]:
            raise ValueError(f"无效的场地类别: {soil_type}, 可选 A/B/C/D/E")

        S, TB, TC, TD = params[spectrum_type][soil_type]

        # 阻尼修正系数
        eta = max(0.55, np.sqrt(10.0 / (5.0 + zeta * 100.0)))

        periods = np.asarray(periods, dtype=np.float64)
        se = np.zeros_like(periods)

        m1 = periods < TB
        se[m1] = ag * S * (1.0 + periods[m1] / TB * (eta * 2.5 - 1.0))

        m2 = (periods >= TB) & (periods <= TC)
        se[m2] = ag * S * eta * 2.5

        m3 = (periods > TC) & (periods <= TD)
        se[m3] = ag * S * eta * 2.5 * (TC / periods[m3])

        m4 = periods > TD
        se[m4] = ag * S * eta * 2.5 * (TC * TD / periods[m4] ** 2)

        np.clip(se, 0.0, None, out=se)
        return se

    @staticmethod
    def asce7(
        periods: np.ndarray,
        sds: float,
        sd1: float,
        tl: float = 8.0,
    ) -> np.ndarray:
        """
        ASCE 7 设计反应谱。
        ASCE 7 design response spectrum.

        Parameters
        ----------
        periods : np.ndarray
            周期数组 (s)
        sds : float
            短周期设计谱加速度参数
        sd1 : float
            1s 周期设计谱加速度参数
        tl : float
            长周期转换周期 (s)

        Returns
        -------
        np.ndarray
            设计反应谱 Sa (g)
        """
        periods = np.asarray(periods, dtype=np.float64)
        sa = np.zeros_like(periods)

        t0 = 0.2 * sd1 / sds
        ts = sd1 / sds

        m1 = periods < t0
        sa[m1] = sds * (0.4 + 0.6 * periods[m1] / t0)

        m2 = (periods >= t0) & (periods <= ts)
        sa[m2] = sds

        m3 = (periods > ts) & (periods <= tl)
        sa[m3] = sd1 / periods[m3]

        m4 = periods > tl
        sa[m4] = sd1 * tl / periods[m4] ** 2

        np.clip(sa, 0.0, None, out=sa)
        return sa

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

    # GB/T 51408 隔震设计特征周期增量表 (s)
    # Site class -> Tg increment for isolation per GB/T 51408
    GB51408_TG_INCREMENT = {
        "I0": 0.05,
        "I1": 0.05,
        "II": 0.05,
        "III": 0.05,
        "IV": 0.05,
    }

    @staticmethod
    def gb51408(
        periods: np.ndarray,
        intensity: float,
        group: int,
        site_class: str,
        level: str = "rare",
        zeta: float = 0.05,
    ) -> np.ndarray:
        """
        GB/T 51408 建筑隔震设计标准反应谱。
        GB/T 51408 seismic isolation design spectrum.

        基于 GB 50011 隔震三段式谱，特征周期 Tg 按 51408 规定增加。
        Based on GB 50011 3-segment isolation spectrum with Tg adjustment
        per GB/T 51408.

        Parameters
        ----------
        periods : np.ndarray
            周期数组 (s) / Period array (s)
        intensity : float
            抗震设防烈度 / Seismic intensity (6, 7, 7.5, 8, 8.5, 9)
        group : int
            设计地震分组 / Design earthquake group (1, 2, 3)
        site_class : str
            场地类别 / Site class (I0, I1, II, III, IV)
        level : str
            地震水准 / Seismic level (默认 rare)
        zeta : float
            阻尼比 / Damping ratio

        Returns
        -------
        np.ndarray
            地震影响系数数组 / Influence coefficient array
        """
        params = CodeSpectrum.get_params(intensity, group, site_class, level)
        increment = CodeSpectrum.GB51408_TG_INCREMENT.get(site_class, 0.05)
        Tg_iso = params["Tg"] + increment
        return CodeSpectrum.gb50011(
            periods, Tg_iso, params["alpha_max"], zeta=zeta, isolation=True
        )

    @staticmethod
    def from_custom(
        custom_periods: np.ndarray,
        custom_sa: np.ndarray,
        periods: np.ndarray,
        interp_mode: str = "linear",
    ) -> np.ndarray:
        """
        自定义谱插值到任意周期点。
        Interpolate a custom spectrum onto arbitrary periods.

        Parameters
        ----------
        custom_periods : array_like
            自定义周期点 / Custom period points
        custom_sa : array_like
            自定义谱加速度 / Custom spectral acceleration
        periods : array_like
            目标周期数组 / Target period array
        interp_mode : str
            插值方式 'linear' 或 'log' / Interpolation mode

        Returns
        -------
        np.ndarray
            插值后的谱加速度 / Interpolated spectral acceleration
        """
        custom_periods = np.asarray(custom_periods, dtype=np.float64)
        custom_sa = np.asarray(custom_sa, dtype=np.float64)
        periods = np.asarray(periods, dtype=np.float64)

        if interp_mode == "linear":
            return np.interp(periods, custom_periods, custom_sa)
        elif interp_mode == "log":
            # 对数-对数空间插值，跳过零值周期
            mask_src = custom_periods > 0
            mask_dst = periods > 0
            result = np.zeros_like(periods)
            result[mask_dst] = np.exp(
                np.interp(
                    np.log(periods[mask_dst]),
                    np.log(custom_periods[mask_src]),
                    np.log(np.maximum(custom_sa[mask_src], 1e-30)),
                )
            )
            return result
        else:
            raise ValueError(
                f"不支持的插值方式: '{interp_mode}', 可选 'linear' 或 'log'"
            )

    @staticmethod
    def from_csv(filepath: str) -> tuple:
        """
        从 CSV/TXT 文件读取自定义谱。
        Read custom spectrum from CSV/TXT file.

        支持逗号、空格、制表符分隔，跳过 # 注释行和空行。
        Supports comma/space/tab delimiters, skips # comments and blank lines.

        Parameters
        ----------
        filepath : str
            文件路径 / File path

        Returns
        -------
        tuple
            (periods, sa) — 两个 numpy 数组 / Two numpy arrays
        """
        periods_list = []
        sa_list = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # 尝试多种分隔符: 逗号 > 制表符 > 空格
                if "," in line:
                    parts = line.split(",")
                elif "\t" in line:
                    parts = line.split("\t")
                else:
                    parts = line.split()
                if len(parts) < 2:
                    continue
                periods_list.append(float(parts[0].strip()))
                sa_list.append(float(parts[1].strip()))
        return (np.array(periods_list), np.array(sa_list))
