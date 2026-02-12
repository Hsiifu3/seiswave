"""
地震波选取引擎

实现三步筛选：有效持时 → 主周期偏差 → 底部剪力校核（可选）。

参考：
- MATLAB: SelectWave_0802g.m
- GB 50011-2010 第 5.1.2 条
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional, Callable

from .io import EQRecord
from .code_spec import CodeSpectrum


@dataclass
class SelectionCriteria:
    """选波参数"""
    Tg: float                                # 特征周期 (s)
    alpha_max: float                         # 地震影响系数最大值
    T_main: list[float]                      # 结构主要周期 [T1, T2, T3, ...]
    zeta: float = 0.05                       # 阻尼比
    duration_factor: float = 5.0             # 有效持时倍数（≥ factor × T1）
    duration_threshold: float = 0.1          # 有效持时阈值（PGA 的百分比）
    spectral_tol: float = 0.20               # 反应谱偏差容限（20%）
    isolation: bool = False                  # 是否隔震结构
    shear_check: bool = False                # 是否进行底部剪力校核
    shear_range: tuple = (0.65, 1.35)        # 底部剪力比范围
    mass: Optional[np.ndarray] = None        # 质量数组 (kg)，底部剪力校核用
    stiffness: Optional[np.ndarray] = None   # 层刚度数组 (N/m)，底部剪力校核用


@dataclass
class SelectionResult:
    """单条波的筛选结果"""
    record: EQRecord
    effective_duration: float                # 有效持时 (s)
    deviations: dict = field(default_factory=dict)  # 各主周期偏差 {T: deviation}
    shear_ratio: Optional[float] = None      # 底部剪力比
    passed_duration: bool = False
    passed_spectral: bool = False
    passed_shear: bool = True                # 默认通过（不校核时）
    passed: bool = False


class WaveSelector:
    """地震波选取引擎"""

    def __init__(self, criteria: SelectionCriteria):
        self.criteria = criteria
        self.target_spectrum = None  # 缓存的目标规范谱值（在主周期点）
        self.results: list[SelectionResult] = []

    def select(self, records: list[EQRecord],
               progress_callback: Optional[Callable] = None) -> list[SelectionResult]:
        """执行三步筛选

        Parameters
        ----------
        records : list[EQRecord]
            待筛选的地震动记录
        progress_callback : callable, optional
            进度回调 fn(current, total, record_name)

        Returns
        -------
        list[SelectionResult]
            通过筛选的结果列表
        """
        c = self.criteria

        # 预计算目标规范谱在主周期点的值
        T_main = np.array(c.T_main)
        self.target_spectrum = CodeSpectrum.gb50011(
            T_main, c.Tg, c.alpha_max, zeta=c.zeta, isolation=c.isolation
        )

        self.results = []
        total = len(records)

        for idx, rec in enumerate(records):
            if progress_callback:
                progress_callback(idx + 1, total, rec.name)

            result = SelectionResult(record=rec, effective_duration=0.0)

            # Step 1: 有效持时
            ok, dur = self._check_duration(rec)
            result.effective_duration = dur
            result.passed_duration = ok
            if not ok:
                self.results.append(result)
                continue

            # Step 2: 主周期偏差
            ok, devs = self._check_spectral_deviation(rec)
            result.deviations = devs
            result.passed_spectral = ok
            if not ok:
                self.results.append(result)
                continue

            # Step 3: 底部剪力校核（可选）
            if c.shear_check and c.mass is not None and c.stiffness is not None:
                ok, ratio = self._check_base_shear(rec)
                result.shear_ratio = ratio
                result.passed_shear = ok
                if not ok:
                    self.results.append(result)
                    continue

            result.passed = True
            self.results.append(result)

        return [r for r in self.results if r.passed]

    # ──────────────────── Step 1: 有效持时 ────────────────────

    def _check_duration(self, rec: EQRecord) -> tuple[bool, float]:
        """有效持时检查

        有效持时定义：首次超过 PGA×threshold 到最后一次超过 PGA×threshold 的时间段。
        要求：有效持时 ≥ duration_factor × T1

        Returns
        -------
        (passed, effective_duration)
        """
        c = self.criteria
        acc = rec.acc
        pga = np.max(np.abs(acc))

        if pga == 0:
            return False, 0.0

        # 归一化后找超过阈值的时刻
        threshold = c.duration_threshold * pga
        above = np.where(np.abs(acc) >= threshold)[0]

        if len(above) == 0:
            return False, 0.0

        duration = (above[-1] - above[0]) * rec.dt
        T1 = max(c.T_main)  # 最大主周期
        required = c.duration_factor * T1

        return duration >= required, duration

    # ──────────────────── Step 2: 主周期偏差 ────────────────────

    def _check_spectral_deviation(self, rec: EQRecord) -> tuple[bool, dict]:
        """主周期点反应谱偏差校核

        对每个主周期 Ti，计算归一化加速度反应谱值与规范谱值的偏差。
        要求：所有主周期点偏差 ≤ spectral_tol

        Returns
        -------
        (passed, {T: deviation})
        """
        c = self.criteria
        T_main = np.array(c.T_main)

        # 归一化加速度记录
        acc = rec.acc / np.max(np.abs(rec.acc))

        # 计算各主周期点的加速度反应谱值（Newmark-β）
        sa_values = np.array([
            self._sdof_peak_acc(acc, rec.dt, T, c.zeta)
            for T in T_main
        ])

        # 计算偏差
        deviations = {}
        all_pass = True
        for i, T in enumerate(T_main):
            target = self.target_spectrum[i]
            if target > 0:
                dev = abs(sa_values[i] - target) / target
            else:
                dev = 0.0
            deviations[T] = dev
            if dev > c.spectral_tol:
                all_pass = False

        return all_pass, deviations

    # ──────────────────── Step 3: 底部剪力校核 ────────────────────

    def _check_base_shear(self, rec: EQRecord) -> tuple[bool, float]:
        """底部剪力校核

        时程分析底部剪力 vs SRSS 振型分解法底部剪力。
        要求：比值在 shear_range 范围内。

        Returns
        -------
        (passed, shear_ratio)
        """
        c = self.criteria
        m = np.asarray(c.mass, dtype=np.float64)
        k = np.asarray(c.stiffness, dtype=np.float64)
        cn = len(m)

        # 构建质量矩阵和刚度矩阵
        M = np.diag(m)
        K = self._form_stiffness_matrix(k, cn)

        # 特征值分析
        eigenvalues, eigenvectors = np.linalg.eig(np.linalg.solve(M, K))
        idx = np.argsort(eigenvalues)
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        periods = 2.0 * np.pi / np.sqrt(np.abs(eigenvalues))
        periods = np.sort(periods)[::-1]  # 降序

        # 振型归一化（顶层为1）
        for i in range(cn):
            eigenvectors[:, i] /= eigenvectors[-1, i]

        # 振型参与系数
        G = m * 9.81  # 重力
        gamma = np.zeros(cn)
        for i in range(cn):
            phi = eigenvectors[:, i]
            gamma[i] = np.sum(phi * G) / np.sum(phi ** 2 * G)

        # SRSS 底部剪力
        alpha_modes = CodeSpectrum.gb50011(
            periods, c.Tg, c.alpha_max, zeta=c.zeta, isolation=c.isolation
        )
        S = np.zeros(cn)
        for i in range(cn):
            S[i] = np.sum(alpha_modes[i] * gamma[i] * eigenvectors[:, i] * G)
        Fv_RS = np.sqrt(np.sum(S ** 2))

        # 时程分析底部剪力
        acc_scaled = rec.acc / np.max(np.abs(rec.acc)) * 2.0  # 归一化后缩放
        Fv_THA = self._time_history_base_shear(acc_scaled, rec.dt, M, K, k, cn, c.zeta)

        if Fv_RS > 0:
            ratio = Fv_THA / Fv_RS
        else:
            ratio = 0.0

        lo, hi = c.shear_range
        return lo < ratio < hi, ratio

    # ──────────────────── 辅助方法 ────────────────────

    @staticmethod
    def _sdof_peak_acc(acc: np.ndarray, dt: float, period: float,
                       zeta: float) -> float:
        """Newmark-β 法计算 SDOF 系统峰值绝对加速度

        移植自 MATLAB SelectWave_0802g.m 的 Newmark 线性加速度法。
        """
        omega = 2.0 * np.pi / period
        k = omega ** 2
        c = 2.0 * zeta * omega
        n = len(acc)

        # 增量形式的 Newmark-β（线性加速度法）
        dis = 0.0
        vel = 0.0
        acc_r = 0.0  # 相对加速度
        peak_abs = 0.0

        keff = k + 2.0 * c / dt + 4.0 / (dt ** 2)

        for i in range(n - 1):
            da = acc[i + 1] - acc[i]
            dp = (-da + (4.0 / dt) * vel + 2.0 * acc_r + 2.0 * c * vel)
            ddis = dp / keff
            dvel = 2.0 / dt * ddis - 2.0 * vel
            dacc = 4.0 / (dt ** 2) * ddis - (4.0 / dt) * vel - 2.0 * acc_r

            dis += ddis
            vel += dvel
            acc_r += dacc

            abs_acc = abs(acc_r + acc[i + 1])
            if abs_acc > peak_abs:
                peak_abs = abs_acc

        # 也检查第一个时刻
        abs_acc_0 = abs(acc[0])
        if abs_acc_0 > peak_abs:
            peak_abs = abs_acc_0

        return peak_abs

    @staticmethod
    def _form_stiffness_matrix(k: np.ndarray, cn: int) -> np.ndarray:
        """构建层间刚度矩阵"""
        K = np.zeros((cn, cn))
        for i in range(cn - 1):
            K[i, i] = k[i] + k[i + 1]
            K[i, i + 1] = -k[i + 1]
            K[i + 1, i] = -k[i + 1]
        K[cn - 1, cn - 1] = k[cn - 1]
        return K

    @staticmethod
    def _time_history_base_shear(acc: np.ndarray, dt: float,
                                  M: np.ndarray, K: np.ndarray,
                                  k_story: np.ndarray, cn: int,
                                  zeta: float) -> float:
        """多自由度时程分析，返回底层最大剪力"""
        # Rayleigh 阻尼
        eigenvalues, _ = np.linalg.eig(np.linalg.solve(M, K))
        w = np.sort(np.sqrt(np.abs(eigenvalues)))
        w1, w2 = w[0], w[1]
        a0 = 2.0 * w1 * w2 * (zeta * w2 - zeta * w1) / (w2 ** 2 - w1 ** 2)
        a1 = 2.0 * (zeta * w2 - zeta * w1) / (w2 ** 2 - w1 ** 2)
        C = a0 * M + a1 * K

        n = len(acc)
        ones = np.ones(cn)

        # Newmark-β 时程分析
        dis = np.zeros(cn)
        vel = np.zeros(cn)
        acc_r = np.zeros(cn)

        Keff = K + 2.0 * C / dt + M * 4.0 / (dt ** 2)
        Keff_inv = np.linalg.inv(Keff)

        max_base_shear = 0.0

        for i in range(n - 1):
            da = acc[i + 1] - acc[i]
            dp = (-M @ ones * da + (4.0 / dt) * M @ vel + 2.0 * M @ acc_r
                  + 2.0 * C @ vel)
            ddis = Keff_inv @ dp
            dvel = 2.0 / dt * ddis - 2.0 * vel
            dacc = 4.0 / (dt ** 2) * ddis - (4.0 / dt) * vel - 2.0 * acc_r

            dis += ddis
            vel += dvel
            acc_r += dacc

            # 层间位移 → 层间剪力
            inter_dis = np.zeros(cn)
            inter_dis[0] = dis[0]
            for j in range(1, cn):
                inter_dis[j] = dis[j] - dis[j - 1]

            base_shear = abs(k_story[0] * inter_dis[0])
            if base_shear > max_base_shear:
                max_base_shear = base_shear

        return max_base_shear

    # ──────────────────── 报告与导出 ────────────────────

    def get_passed(self) -> list[SelectionResult]:
        """获取通过筛选的结果"""
        return [r for r in self.results if r.passed]

    def summary(self) -> dict:
        """生成筛选摘要"""
        total = len(self.results)
        passed_dur = sum(1 for r in self.results if r.passed_duration)
        passed_spec = sum(1 for r in self.results if r.passed_spectral)
        passed_all = sum(1 for r in self.results if r.passed)

        return {
            "total": total,
            "passed_duration": passed_dur,
            "passed_spectral": passed_spec,
            "passed_all": passed_all,
            "passed_names": [r.record.name for r in self.results if r.passed],
        }
