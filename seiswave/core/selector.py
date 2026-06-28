"""
地震波选取引擎

三步筛选 + 反应谱匹配排序 + 贪心组合。

参考：
- GB 50011-2010 第 5.1.2 条
- MATLAB: SelectWave_0802g.m
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Callable

from .peer_db import PeerRecord, PeerDatabase
from .code_spec import CodeSpectrum


@dataclass
class SelectionConfig:
    """选波配置"""
    target_sa: np.ndarray               # 目标反应谱 (g)
    periods: np.ndarray                 # 周期数组 (s)
    T_main: list[float]                 # 结构主周期 [T1, T2, T3]
    zeta: float = 0.05
    duration_factor: float = 5.0        # 有效持时 ≥ factor × max(T_main)
    spectral_tol: float = 0.30          # 主周期点偏差容限
    n_select: int = 5                   # 选取天然波数量
    scale_range: tuple = (0.5, 4.0)     # PGA 缩放系数范围
    mean_sa_ratio: float = 0.80         # 平均谱 ≥ ratio × 目标谱
    isolation: bool = False             # 隔震模式
    T_isolation: list = field(default_factory=list)  # 隔震周期点


@dataclass
class SelectionResult:
    """单条波的选取结果"""
    record: PeerRecord
    scale_factor: float = 1.0           # PGA 缩放系数
    match_error: float = 0.0            # 反应谱匹配误差 (RMSE)
    deviations: dict = field(default_factory=dict)  # 各主周期点偏差
    passed_duration: bool = False
    passed_spectrum: bool = False


class WaveSelector:
    """地震波选取引擎"""

    def __init__(self, config: SelectionConfig):
        self.config = config
        # 预计算主周期在 periods 数组中的索引
        self._T_indices = np.array([
            np.argmin(np.abs(config.periods - T)) for T in config.T_main
        ])
        # 隔震周期索引
        if config.isolation and config.T_isolation:
            self._T_iso_indices = np.array([
                np.argmin(np.abs(config.periods - T))
                for T in config.T_isolation
            ])
        else:
            self._T_iso_indices = np.array([], dtype=int)

    def select(self, database: PeerDatabase,
               progress_cb: Callable = None) -> list[SelectionResult]:
        """自动选波主流程

        1. 获取水平分量（需已有反应谱缓存）
        2. 有效持时筛选
        3. 最优缩放 + 主周期偏差筛选
        4. 按匹配误差排序
        5. 贪心选出最优 N 条组合

        Parameters
        ----------
        database : PeerDatabase
            已建立索引并预计算反应谱的数据库
        progress_cb : fn(current, total)

        Returns
        -------
        list[SelectionResult]
            选中的 N 条波
        """
        cfg = self.config
        candidates = database.get_horizontal()
        total = len(candidates)

        # 确保有反应谱
        n_with_sa = sum(1 for r in candidates if r.sa is not None)
        if n_with_sa == 0:
            raise RuntimeError("数据库中无反应谱数据，请先调用 precompute_spectra()")

        # 需要将数据库的 periods 映射到 config.periods
        db_periods = database.spectra_periods
        if db_periods is None:
            raise RuntimeError("数据库未设置 spectra_periods")

        # 建立周期映射：config.periods → db_periods 的最近邻索引
        period_map = np.array([
            np.argmin(np.abs(db_periods - p)) for p in cfg.periods
        ])

        # 目标谱在主周期点的值
        target_at_T = cfg.target_sa[self._T_indices]

        # 隔震周期点目标谱值
        if cfg.isolation and len(self._T_iso_indices) > 0:
            target_at_Tiso = cfg.target_sa[self._T_iso_indices]
        else:
            target_at_Tiso = None

        # Step 1 & 2: 筛选
        passed = []
        for idx, rec in enumerate(candidates):
            if progress_cb and idx % 50 == 0:
                progress_cb(idx, total)

            if rec.sa is None:
                continue

            # 有效持时检查
            T1 = max(cfg.T_main)
            required_dur = cfg.duration_factor * T1
            if rec.eff_duration < required_dur:
                continue

            # 提取该记录在 config.periods 对应的反应谱
            rec_sa = rec.sa[period_map]

            # 最优缩放系数
            scale = self._optimal_scale(rec_sa, cfg.target_sa)

            # 缩放范围检查
            if not (cfg.scale_range[0] <= scale <= cfg.scale_range[1]):
                continue

            # 缩放后的谱
            scaled_sa = rec_sa * scale

            # 主周期偏差检查
            scaled_at_T = scaled_sa[self._T_indices]
            devs = {}
            all_pass = True
            for i, T in enumerate(cfg.T_main):
                if target_at_T[i] > 0:
                    dev = abs(scaled_at_T[i] - target_at_T[i]) / target_at_T[i]
                else:
                    dev = 0.0
                devs[T] = dev
                if dev > cfg.spectral_tol:
                    all_pass = False

            # 隔震周期偏差检查
            if cfg.isolation and target_at_Tiso is not None:
                scaled_at_Tiso = scaled_sa[self._T_iso_indices]
                for i, T in enumerate(cfg.T_isolation):
                    if target_at_Tiso[i] > 0:
                        dev = abs(scaled_at_Tiso[i] - target_at_Tiso[i]) / target_at_Tiso[i]
                    else:
                        dev = 0.0
                    devs[T] = dev
                    if dev > cfg.spectral_tol:
                        all_pass = False

            if not all_pass:
                continue

            # 匹配误差（T ≥ 0.1s 部分，避免短周期噪声）
            mask = (cfg.target_sa > 0) & (cfg.periods >= 0.1)
            if np.sum(mask) > 0:
                err = np.sqrt(np.mean(
                    ((scaled_sa[mask] - cfg.target_sa[mask]) / cfg.target_sa[mask]) ** 2
                ))
            else:
                err = 999.0

            passed.append(SelectionResult(
                record=rec,
                scale_factor=scale,
                match_error=err,
                deviations=devs,
                passed_duration=True,
                passed_spectrum=True,
            ))

        if progress_cb:
            progress_cb(total, total)

        # Step 3: 按误差排序
        passed.sort(key=lambda r: r.match_error)

        # Step 4: 贪心组合
        if len(passed) <= cfg.n_select:
            return passed

        return self._greedy_combination(passed, cfg.n_select,
                                         period_map, db_periods)

    def _optimal_scale(self, rec_sa: np.ndarray,
                       target_sa: np.ndarray) -> float:
        """加权最小二乘法求最优缩放系数

        主周期点权重高，确保缩放后主周期匹配好。
        """
        cfg = self.config
        mask = (target_sa > 0) & (rec_sa > 0) & (cfg.periods >= 0.1)
        if np.sum(mask) < 3:
            return 0.0

        r = rec_sa[mask]
        t = target_sa[mask]
        p = cfg.periods[mask]

        # 权重：主周期附近权重高
        w = np.ones_like(p)
        for T in cfg.T_main:
            w += 5.0 * np.exp(-((p - T) / (0.3 * T)) ** 2)
        # 隔震周期也加权
        if cfg.isolation and cfg.T_isolation:
            for T in cfg.T_isolation:
                w += 5.0 * np.exp(-((p - T) / (0.3 * T)) ** 2)

        # 加权最小二乘: minimize sum(w * (scale*r - t)^2 / t^2)
        scale = np.sum(w * r * t / t ** 2) / np.sum(w * r ** 2 / t ** 2)
        return max(scale, 0.0)

    def _greedy_combination(self, candidates: list[SelectionResult],
                            n: int, period_map: np.ndarray,
                            db_periods: np.ndarray) -> list[SelectionResult]:
        """贪心组合：确保 N 条波的平均谱满足规范要求

        逐条加入使组合平均谱最优的波。
        """
        cfg = self.config
        mask = (cfg.target_sa > 0) & (cfg.periods >= 0.1)
        selected = []
        sa_sum = np.zeros(len(cfg.periods))
        used = set()
        used_rsns = set()
        used_events = set()  # 事件多样性:尽量不选同一地震事件

        # 合并主周期和隔震周期索引用于额外惩罚
        all_T_indices = self._T_indices
        if cfg.isolation and len(self._T_iso_indices) > 0:
            all_T_indices = np.concatenate([self._T_indices, self._T_iso_indices])

        for step in range(n):
            best_idx = -1            # 来自未用过事件的最优
            best_score = 1e30
            best_idx_any = -1        # 退路:允许同事件
            best_score_any = 1e30

            for i, cand in enumerate(candidates):
                if i in used:
                    continue

                # 避免同一 RSN 重复选取
                if cand.record.rsn in used_rsns:
                    continue

                rec_sa = cand.record.sa[period_map] * cand.scale_factor
                trial_sum = sa_sum + rec_sa
                trial_mean = trial_sum / (step + 1)

                # 评分：平均谱与目标谱的 RMSE（T ≥ 0.1s）
                err = np.sqrt(np.mean(
                    ((trial_mean[mask] - cfg.target_sa[mask]) / cfg.target_sa[mask]) ** 2
                ))

                # 惩罚平均谱低于目标谱的情况
                ratio_min = np.min(trial_mean[mask] / cfg.target_sa[mask])
                if ratio_min < cfg.mean_sa_ratio:
                    err += (cfg.mean_sa_ratio - ratio_min) * 2.0

                # 隔震模式：额外惩罚关键周期点偏差
                if cfg.isolation and len(all_T_indices) > 0:
                    t_vals = cfg.target_sa[all_T_indices]
                    m_vals = trial_mean[all_T_indices]
                    valid = t_vals > 0
                    if np.any(valid):
                        key_err = np.max(np.abs(m_vals[valid] - t_vals[valid]) / t_vals[valid])
                        err += key_err * 0.5

                if err < best_score_any:
                    best_score_any = err
                    best_idx_any = i

                # 事件多样性:优先未用过的事件(event 为空则不限制)
                ev = (getattr(cand.record, "event", "") or "").strip().upper()
                if ev and ev in used_events:
                    continue
                if err < best_score:
                    best_score = err
                    best_idx = i

            # 优先取不同事件的最优;若没有未用事件可选,退而取整体最优
            chosen = best_idx if best_idx >= 0 else best_idx_any
            if chosen < 0:
                break

            used.add(chosen)
            cand = candidates[chosen]
            used_rsns.add(cand.record.rsn)
            ev = (getattr(cand.record, "event", "") or "").strip().upper()
            if ev:
                used_events.add(ev)
            selected.append(cand)
            sa_sum += cand.record.sa[period_map] * cand.scale_factor

        return selected

    def mean_spectrum(self, results: list[SelectionResult],
                      database: PeerDatabase) -> np.ndarray:
        """计算选中波的平均反应谱"""
        cfg = self.config
        db_periods = database.spectra_periods
        period_map = np.array([
            np.argmin(np.abs(db_periods - p)) for p in cfg.periods
        ])

        sa_list = []
        for r in results:
            rec_sa = r.record.sa[period_map] * r.scale_factor
            sa_list.append(rec_sa)

        if not sa_list:
            return np.zeros(len(cfg.periods))
        return np.mean(sa_list, axis=0)

    def envelope_spectrum(self, results: list[SelectionResult],
                          database: PeerDatabase) -> np.ndarray:
        """计算选中波的包络反应谱"""
        cfg = self.config
        db_periods = database.spectra_periods
        period_map = np.array([
            np.argmin(np.abs(db_periods - p)) for p in cfg.periods
        ])

        sa_list = []
        for r in results:
            rec_sa = r.record.sa[period_map] * r.scale_factor
            sa_list.append(rec_sa)

        if not sa_list:
            return np.zeros(len(cfg.periods))
        return np.max(sa_list, axis=0)
