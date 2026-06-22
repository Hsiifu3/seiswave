"""
人工地震波生成模块

谱匹配算法（基于 EQSignal fitspectra / adjustspectra + initArtWave）：
1. initArtWave: 从目标反应谱估计功率谱，生成初始信号
2. adjustspectra (fm=1, 默认): 时域小波叠加 + 最小二乘迭代
   a. 计算反应谱 SPA（Newmark-β 带子步插值，C 加速）
   b. 构造小波函数 W_i（Gaussian-modulated cosine）
   c. 计算响应矩阵 M_ij = ra(W_j, P_i) / SPAT_i
   d. 最小二乘求解 dR，叠加 a += sum(dR_i * W_i)
3. fitspectra (fm=0, 备选): 频域迭代调整
   a. ratio = target / |SPA|，递减线性插值到 FFT 频率
   b. rsimple 符号修正
   c. af *= ratio（累积频域调整）
   d. IFFT → adjustpeak → 重新计算反应谱
4. 多 trial 取最优迭代结果

参考：EQSignal (Panchatantra/EQSignal) eqs.f90
"""

import numpy as np
import ctypes
import os
import logging
from typing import Optional, Callable

logger = logging.getLogger(__name__)

# ── 加载 C 加速库 ──
_c_lib = None
_c_lib_path = os.path.join(os.path.dirname(__file__), '_newmark.so')
if os.path.exists(_c_lib_path):
    try:
        _c_lib = ctypes.CDLL(_c_lib_path)
        _c_lib.newmark_spectrum.argtypes = [
            ctypes.POINTER(ctypes.c_double), ctypes.c_int,
            ctypes.c_double, ctypes.c_double,
            ctypes.POINTER(ctypes.c_double), ctypes.c_int,
            ctypes.POINTER(ctypes.c_double), ctypes.POINTER(ctypes.c_int),
        ]
        _c_lib.newmark_spectrum.restype = None
    except OSError:
        _c_lib = None


class WaveGenerator:
    """人工地震波生成器"""

    MPR = 20  # 短/长周期分界：T < MPR*dt 用频域法

    @staticmethod
    def generate(target_spectrum: Optional[np.ndarray] = None,
                 periods: Optional[np.ndarray] = None,
                 n: int = 4096, dt: float = 0.02, zeta: float = 0.05,
                 pga: float = 1.0, tol: float = 0.05, max_iter: int = 20,
                 fm: Optional[int] = None,
                 progress_callback: Optional[Callable] = None,
                 n_trials: int = 3,
                 type: Optional[str] = None,
                 Mw: Optional[float] = None,
                 R: Optional[float] = None,
                 Vs30: float = 760.0,
                 fault_type: str = "strike_slip",
                 use_atik: bool = True,
                 use_staged_peak: bool = False,
                 **kwargs):
        """统一入口：通用谱匹配 or 特殊地震动类型分发。

        - 兼容旧调用：`generate(target_spectrum, periods, ...)`
        - 新调用：`generate(type="FF"|"NF"|"NFP", Mw=..., R=..., ...)`
        """
        from .fortran_bridge import HAS_FORTRAN
        envelope_values = kwargs.pop("envelope_values", None)

        if type is not None:
            dispatch_fm = 0 if fm is None else fm
            type_upper = str(type).upper()
            if type_upper == "FF":
                return FarFieldGenerator.generate(
                    Mw=Mw, R=R, Vs30=Vs30, fault_type=fault_type,
                    n=n, dt=dt, zeta=zeta, tol=tol, max_iter=max_iter,
                    fm=dispatch_fm, progress_callback=progress_callback, **kwargs,
                )
            if type_upper == "NF":
                return NearFieldNoPulseGenerator.generate(
                    Mw=Mw, R=R, Vs30=Vs30, fault_type=fault_type,
                    n=n, dt=dt, zeta=zeta, tol=tol, max_iter=max_iter,
                    fm=dispatch_fm, progress_callback=progress_callback, **kwargs,
                )
            if type_upper == "NFP":
                return NearFieldPulseGenerator.generate(
                    Mw=Mw, R=R, Vs30=Vs30, fault_type=fault_type,
                    n=n, dt=dt, zeta=zeta, tol=tol, max_iter=max_iter,
                    fm=dispatch_fm, progress_callback=progress_callback, **kwargs,
                )
            raise ValueError(f"无效的地震动类型: {type}")

        if target_spectrum is None or periods is None:
            raise ValueError("target_spectrum 不能为空（或未提供 type）")

        general_fm = 1 if fm is None else fm
        target_spectrum = np.asarray(target_spectrum, dtype=np.float64)
        periods = np.asarray(periods, dtype=np.float64)

        valid = (periods > 0) & (target_spectrum > 1e-12)
        ctrl_periods = periods[valid]
        ctrl_target = target_spectrum[valid].copy()
        nP_orig = len(ctrl_periods)

        peak0 = pga

        # ── Fortran 快速路径（当前频域法有已知精度问题，暂禁用）──
        # if HAS_FORTRAN:
        #     return WaveGenerator._generate_fortran(
        #         ctrl_periods, ctrl_target, nP_orig, n, dt, zeta, peak0,
        #         tol, max_iter, general_fm, progress_callback)

        # ── Python 回退路径 ──
        return WaveGenerator._generate_python(
            ctrl_periods, ctrl_target, nP_orig, n, dt, zeta, peak0,
            tol, max_iter, general_fm, progress_callback,
            n_trials=n_trials, envelope_values=envelope_values,
            use_atik=use_atik, use_staged_peak=use_staged_peak)

    @staticmethod
    def _generate_fortran(ctrl_periods, ctrl_target, nP_orig, n, dt, zeta,
                          peak0, tol, max_iter, fm, progress_callback):
        """Fortran 加速生成路径。

        对 fm=1 的时域谱匹配，内部控制点可先降采样到较小规模，
        但最终误差仍使用完整目标谱验算，兼顾稳定性与展示一致性。
        """
        from .signal import EQSignal as EQSig
        from .fortran_bridge import _eqs, spectrum_mixed

        if fm == 1 and nP_orig > 50:
            P_ctrl, SPAT_ctrl = WaveGenerator._downsample_control_points(
                ctrl_periods, ctrl_target, max_ctrl=50
            )
            nP_ctrl = len(P_ctrl)
            logger.info("控制点降采样: %d → %d (fm=1)", nP_orig, nP_ctrl)
        else:
            P_ctrl = np.asarray(ctrl_periods, dtype=np.float64).copy()
            SPAT_ctrl = np.asarray(ctrl_target, dtype=np.float64).copy()
            nP_ctrl = nP_orig

        P = np.ascontiguousarray(P_ctrl, dtype=np.float64)
        SPAT = np.ascontiguousarray(SPAT_ctrl, dtype=np.float64)

        n_trials = 3
        global_best_acc = None
        global_best_error = float('inf')

        for trial in range(n_trials):
            # 初始信号（Fortran initartwave 自动处理谱估计）
            acc = _eqs.eqs.initartwave(n, dt, zeta, P, SPAT)

            # 缩放初始波到目标 PGA（fitspectrum 内部 adjustpeak 会维持此值）
            pk = np.max(np.abs(acc[:n]))
            if pk > 0 and peak0 > 0:
                acc = acc * (peak0 / pk)

            # 直接调用 fitspectrum（内部处理扩展谱 + 迭代 + adjustpeak）
            acc = _eqs.eqs.fitspectrum(acc, dt, zeta, P, SPAT,
                                        tol, max_iter, fm, 1)

            # 计算误差（用原始完整控制点验证）
            spa, _ = spectrum_mixed(acc[:n], dt, zeta, ctrl_periods)
            e = (np.abs(spa) - ctrl_target) / np.maximum(ctrl_target, 1e-30)
            aerror = float(np.sqrt(np.mean(e * e)))

            if progress_callback:
                merror = float(np.max(np.abs(e)))
                progress_callback(max_iter * (trial + 1), merror, aerror)

            if aerror < global_best_error:
                global_best_error = aerror
                global_best_acc = acc[:n].copy()

        acc = global_best_acc if global_best_acc is not None else acc[:n]
        result = EQSig(acc, dt, name="artificial")
        result.a2vd()
        return result

    @staticmethod
    def _generate_python(ctrl_periods, ctrl_target, nP_orig, n, dt, zeta,
                         peak0, tol, max_iter, fm, progress_callback,
                         n_trials=3, envelope_values=None, use_atik=True,
                         use_staged_peak=False):
        """Python 回退生成路径。"""
        from .signal import EQSignal as EQSig

        if fm == 0:
            # ── 频域法：扩展目标谱（两端各加一个点），复现 fitspectrum ──
            nP = nP_orig + 2
            P = np.empty(nP)
            P[0] = ctrl_periods[0] * 0.5
            P[1:nP_orig+1] = ctrl_periods
            P[nP_orig+1] = ctrl_periods[-1] * 1.5

            SPAT = np.empty(nP)
            SPAT[1:nP_orig+1] = ctrl_target
            if nP_orig >= 2:
                SPAT[0] = ctrl_target[0] - (ctrl_target[1] - ctrl_target[0]) / \
                          (ctrl_periods[1] - ctrl_periods[0]) * ctrl_periods[0] * 0.5
                SPAT[nP_orig+1] = ctrl_target[-1] + (ctrl_target[-1] - ctrl_target[-2]) / \
                                  (ctrl_periods[-1] - ctrl_periods[-2]) * ctrl_periods[-1] * 0.5
            else:
                SPAT[0] = ctrl_target[0]
                SPAT[nP_orig+1] = ctrl_target[0]

            P_ctrl = P
            SPAT_ctrl = SPAT
            nP_ctrl = nP
        else:
            # ── 时域法：内部控制点可降采样，最终误差仍用完整谱验算 ──
            if use_atik:
                # Atik 算法：仅用可表示控制点(T>=2*dt，即频率<=Nyquist)。
                # 超 Nyquist 周期(T<2*dt)在该 dt 下物理上无法匹配，纳入目标只会污染
                # 最小二乘修正方向、拖慢收敛(实测仅可表示255点 iter5→1.8% vs 全300点 4.0%)。
                repr_mask = ctrl_periods >= 2.0 * dt
                if (not np.all(repr_mask)) and int(np.count_nonzero(repr_mask)) >= 2:
                    P_ctrl = np.ascontiguousarray(ctrl_periods[repr_mask], dtype=np.float64)
                    SPAT_ctrl = np.ascontiguousarray(ctrl_target[repr_mask], dtype=np.float64)
                    logger.info("控制点剔除超 Nyquist (T<%.3fs): %d → %d",
                                2.0 * dt, nP_orig, len(P_ctrl))
                else:
                    P_ctrl = np.asarray(ctrl_periods, dtype=np.float64).copy()
                    SPAT_ctrl = np.asarray(ctrl_target, dtype=np.float64).copy()
                nP_ctrl = len(P_ctrl)
            elif nP_orig > 50:
                P_ctrl, SPAT_ctrl = WaveGenerator._downsample_control_points(
                    ctrl_periods, ctrl_target, max_ctrl=50
                )
                nP_ctrl = len(P_ctrl)
                logger.info("控制点降采样: %d → %d (fm=1)", nP_orig, nP_ctrl)
            else:
                P_ctrl = np.asarray(ctrl_periods, dtype=np.float64).copy()
                SPAT_ctrl = np.asarray(ctrl_target, dtype=np.float64).copy()
                nP_ctrl = nP_orig

            P = ctrl_periods
            SPAT = ctrl_target

        # ── 多 trial 取最优 ──
        global_best_acc = None
        global_best_error = float('inf')

        # 预判断 Fortran 可用性（仅时域法需要）
        # 当前实验：fm=1 强制走 Python 路径，验证两阶段增压策略
        use_fortran_adjust = False
        base_envelope = WaveGenerator._resolve_envelope(
            n, dt, envelope_values=envelope_values
        )

        for trial in range(n_trials):
            # 初始信号：从目标谱估计功率谱（复现 initArtWave）
            # initArtWave 需要扩展谱
            nP_ext = nP_orig + 2
            P_ext = np.empty(nP_ext)
            P_ext[0] = ctrl_periods[0] * 0.5
            P_ext[1:nP_orig+1] = ctrl_periods
            P_ext[nP_orig+1] = ctrl_periods[-1] * 1.5
            SPAT_ext = np.empty(nP_ext)
            SPAT_ext[1:nP_orig+1] = ctrl_target
            if nP_orig >= 2:
                SPAT_ext[0] = ctrl_target[0] - (ctrl_target[1] - ctrl_target[0]) / \
                              (ctrl_periods[1] - ctrl_periods[0]) * ctrl_periods[0] * 0.5
                SPAT_ext[nP_orig+1] = ctrl_target[-1] + (ctrl_target[-1] - ctrl_target[-2]) / \
                                      (ctrl_periods[-1] - ctrl_periods[-2]) * ctrl_periods[-1] * 0.5
            else:
                SPAT_ext[0] = ctrl_target[0]
                SPAT_ext[nP_orig+1] = ctrl_target[0]

            acc = WaveGenerator._init_art_wave(n, dt, zeta, P_ext, SPAT_ext,
                                                nP_ext, seed=trial * 37 + 13)

            # 包络调制
            acc *= base_envelope

            # fm=0 保持原有预缩放逻辑；fm=1 交给后续两阶段增压处理
            if fm == 0:
                pk = np.max(np.abs(acc))
                if pk > 0:
                    acc *= peak0 / pk

            # 谱匹配迭代
            if fm == 0:
                acc, best_aerror = WaveGenerator._fitspectra(
                    acc, n, dt, zeta, P, nP, SPAT, tol, max_iter, peak0,
                    progress_callback
                )
            else:
                if use_fortran_adjust:
                    from .fortran_bridge import adjust_spectra
                    acc_f = adjust_spectra(
                        acc, dt, zeta,
                        np.ascontiguousarray(P_ctrl, dtype=np.float64),
                        np.ascontiguousarray(SPAT_ctrl, dtype=np.float64),
                        tol, max_iter, 1,
                    )
                    # 强制确保只取前 n 点并维持 PGA
                    acc = np.asarray(acc_f[:n], dtype=np.float64)
                    pk = np.max(np.abs(acc))
                    if pk > 0:
                        acc *= peak0 / pk
                    # 计算拟合误差用于选优
                    from .spectrum import Spectra
                    spec = Spectra.compute(acc, dt, ctrl_periods, zeta, method="mixed")
                    e = (np.abs(spec.sa) - ctrl_target) / np.maximum(ctrl_target, 1e-30)
                    best_aerror = float(np.sqrt(np.mean(e * e)))
                    if progress_callback and trial == 0:
                        progress_callback(max_iter, float(np.max(np.abs(e))), best_aerror)
                else:
                    # 阶段1：低PGA下修形
                    peak_low = float(np.max(np.abs(acc)))
                    if use_atik:
                        acc, _ = WaveGenerator._adjustspectra_atik(
                            acc, n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl, tol, max_iter,
                            progress_callback
                        )
                    else:
                        acc, _ = WaveGenerator._adjustspectra(
                            acc, n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl, tol, max_iter,
                            progress_callback
                        )
                    
                    # 阶段2（可选/实验）：仅在 use_staged_peak 下做分阶段全局缩放+每步重拟合。
                    # 默认不再强行增压到 target PGA —— 谱匹配迭代修复后 PGA 由短周期谱纵标
                    # 自然决定；旧的"单点硬裁剪逐步增压"会被重拟合抹平、对 PGA 无实效且浪费
                    # 迭代（实测仍停在物理 PGA），故移除。
                    if use_staged_peak and peak_low < peak0 * 0.95:
                        # 实验性：分阶段全局线性缩放 + 每步谱匹配
                        def _stage_adjust(acc_stage):
                            if use_atik:
                                acc_stage, _ = WaveGenerator._adjustspectra_atik(
                                    acc_stage, n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl,
                                    tol, max(5, max_iter // 3), None
                                )
                            else:
                                acc_stage, _ = WaveGenerator._adjustspectra(
                                    acc_stage, n, dt, zeta, P_ctrl, nP_ctrl, SPAT_ctrl,
                                    tol, max(5, max_iter // 3), None
                                )
                            return acc_stage
                        n_steps = max(2, min(5, int((peak0 - peak_low) / 0.02) + 1))
                        acc = WaveGenerator._adjust_peak_staged(
                            acc, peak0, stages=n_steps, adjust_fn=_stage_adjust
                        )

                    # 计算最终误差
                    from .spectrum import Spectra
                    spec = Spectra.compute(acc, dt, ctrl_periods, zeta, method="mixed")
                    e = (np.abs(spec.sa) - ctrl_target) / np.maximum(ctrl_target, 1e-30)
                    best_aerror = float(np.sqrt(np.mean(e * e)))

            if best_aerror < global_best_error:
                global_best_error = best_aerror
                global_best_acc = acc.copy()

        acc = global_best_acc if global_best_acc is not None else acc
        result = EQSig(acc[:n], dt, name="artificial")
        result.a2vd()
        return result

    @staticmethod
    def _downsample_control_points(periods, target, max_ctrl=50):
        """为 fm=1 的时域谱匹配降采样控制点。

        该方法面向 GB50011 一类分段形状明显的目标谱：
        保留首尾端点，并在上升段、平台段、下降段、长周期尾段
        按不同权重抽点，避免将 300 个密集控制点直接送入
        O(nP²) 的时域小波叠加谱匹配。
        """
        periods = np.asarray(periods, dtype=np.float64)
        target = np.asarray(target, dtype=np.float64)
        nP = len(periods)

        if nP != len(target):
            raise ValueError("periods 与 target 长度必须一致")
        if nP <= max_ctrl:
            return periods.copy(), target.copy()
        if max_ctrl < 2:
            raise ValueError("max_ctrl 必须至少为 2")

        def _uniform_take(indices, count):
            indices = np.asarray(indices, dtype=int)
            if len(indices) == 0 or count <= 0:
                return np.array([], dtype=int)
            if len(indices) <= count:
                return indices.copy()
            take = np.linspace(0, len(indices) - 1, count)
            take = np.round(take).astype(int)
            take[0] = 0
            take[-1] = len(indices) - 1
            return indices[np.unique(take)]

        peak_idx = int(np.argmax(target))
        peak_val = float(target[peak_idx])
        Tg_approx = None
        if peak_val > 0.0:
            threshold = peak_val * 0.98
            for idx in range(peak_idx + 1, nP):
                if target[idx] < threshold:
                    Tg_approx = float(periods[idx])
                    break

        if Tg_approx is None or Tg_approx <= 0.1:
            idx = np.unique(np.round(np.linspace(0, nP - 1, max_ctrl)).astype(int))
            idx[0] = 0
            idx[-1] = nP - 1
            idx = np.unique(idx)
            return periods[idx], target[idx]

        T5g = 5.0 * Tg_approx
        seg1 = np.where(periods < 0.1)[0]
        seg2 = np.where((periods >= 0.1) & (periods <= Tg_approx))[0]
        seg3 = np.where((periods > Tg_approx) & (periods <= T5g))[0]
        seg4 = np.where(periods > T5g)[0]

        budgets = [
            min(len(seg1), max(5, int(round(max_ctrl * 0.15)))),
            min(len(seg2), max(3, int(round(max_ctrl * 0.10)))),
            min(len(seg3), max(12, int(round(max_ctrl * 0.55)))),
            min(len(seg4), max(5, int(round(max_ctrl * 0.20)))),
        ]
        segments = [seg1, seg2, seg3, seg4]

        chosen_parts = [_uniform_take(seg, budget) for seg, budget in zip(segments, budgets)]
        chosen = np.unique(np.concatenate([part for part in chosen_parts if len(part) > 0] + [np.array([0, nP - 1], dtype=int)]))

        if len(chosen) < max_ctrl:
            remaining = np.setdiff1d(np.arange(nP, dtype=int), chosen, assume_unique=False)
            if len(remaining) > 0:
                extra = _uniform_take(remaining, max_ctrl - len(chosen))
                chosen = np.unique(np.concatenate([chosen, extra]))

        if len(chosen) > max_ctrl:
            removable_groups = [
                np.intersect1d(chosen, seg2, assume_unique=False),
                np.intersect1d(chosen, seg1, assume_unique=False),
                np.intersect1d(chosen, seg4, assume_unique=False),
                np.intersect1d(chosen, seg3, assume_unique=False),
            ]
            protected = {0, nP - 1}
            removable = []
            for group in removable_groups:
                mids = [idx for idx in group.tolist() if idx not in protected]
                if len(mids) > 2:
                    removable.extend(mids[1:-1])
                else:
                    removable.extend(mids)
            remove_need = len(chosen) - max_ctrl
            if remove_need > 0 and removable:
                removable = np.asarray(removable, dtype=int)
                drop = _uniform_take(removable, min(remove_need, len(removable)))
                chosen = np.setdiff1d(chosen, drop, assume_unique=False)

        if len(chosen) > max_ctrl:
            chosen = _uniform_take(chosen, max_ctrl)
            chosen[0] = 0
            chosen[-1] = nP - 1
            chosen = np.unique(chosen)
            if len(chosen) < max_ctrl:
                remaining = np.setdiff1d(np.arange(nP, dtype=int), chosen, assume_unique=False)
                extra = _uniform_take(remaining, max_ctrl - len(chosen))
                chosen = np.unique(np.concatenate([chosen, extra]))

        chosen = np.sort(chosen)
        return periods[chosen].copy(), target[chosen].copy()

    @staticmethod
    def _init_art_wave(n, dt, zeta, P, SPT, nP, seed=42):
        """从目标反应谱估计功率谱并生成初始信号（复现 initArtWave）

        使用 Vanmarcke (1975) 近似将 Sa 转换为功率谱密度，
        然后用随机相位合成时域信号。
        """
        nfft = WaveGenerator._nextpow2(n)
        fs = 1.0 / dt
        df = fs / nfft
        TWO_PI = 2.0 * np.pi
        PI = np.pi

        # 频率轴（复现 EQSignal fftfreqs，全谱）
        f = np.zeros(nfft)
        f[1:nfft//2] = np.arange(1, nfft//2) * df
        f[nfft//2:] = np.arange(-(nfft//2), 0) * df

        # Pf: 周期数组（递减），对应 f[1:nfft//2]
        # EQSignal: Pf(1) = 100*Pf(2), Pf(2:Nfft/2) = 1/f(2:Nfft/2)
        # Fortran 1-based: Pf has Nfft/2 elements
        # f(1)=0, f(2)=df, ..., f(Nfft/2)=(Nfft/2-1)*df
        n_pf = nfft // 2
        Pf = np.zeros(n_pf)
        # Pf[1:n_pf] corresponds to Fortran Pf(2:Nfft/2) = 1/f(2:Nfft/2)
        # f[1]..f[nfft//2-1] in Python = f(2)..f(Nfft/2) in Fortran
        pos_f = f[1:nfft//2]  # nfft//2-1 elements
        Pf[1:n_pf] = 1.0 / pos_f
        Pf[0] = 100.0 * Pf[1] if n_pf > 1 else 1e6

        # 找频率范围（Pf 递减）
        IPf1 = WaveGenerator._decrfindfirst(Pf, P[-1])
        IPf2 = WaveGenerator._decrfindlast(Pf, P[0])
        NPf = IPf2 - IPf1 + 1

        # 插值目标谱到 FFT 频率（递减线性插值）
        SPTf = np.zeros(nfft // 2)
        SPTf[IPf1:IPf2+1] = WaveGenerator._decrlininterp_core(
            P, SPT[:int(nP)], Pf[IPf1:IPf2+1])

        # 构造频域信号
        rng = np.random.default_rng(seed=seed)
        af = np.zeros(nfft, dtype=complex)
        # NOTE: plateau enhancement 曾被移除（理由：在迭代发散的旧匹配器下，初始波形
        # 质量决定结果，过度抬高短中周期会拖累 envelope-only mean）。谱匹配迭代修复后
        # （带符号 dR + line-search），谱形由匹配器收敛保证，保留 plateau 反而同时改善
        # FF mean(2.0%→1.8%) 并让 NFP 脉冲周期 max 回到 0.176-0.181，故撤销移除。
        # 实测见 tests/probe_plateau_tradeoff.py。
        max_sptf = float(np.max(SPTf[IPf1:IPf2+1])) if IPf2 >= IPf1 else 0.0
        for k in range(IPf1, IPf2 + 1):
            phi = rng.uniform(0, TWO_PI)
            # Pf[k] = 1/f[k]，对应频率 f[k]（Fortran: Pf(k) -> f(k) -> af(k)）
            wk = TWO_PI * f[k]
            if abs(wk) < 1e-30:
                continue
            # Vanmarcke (1975) 功率谱密度估计
            log_arg = (-PI / wk / dt / n) * np.log(1.0 - 0.85)
            if log_arg > 0 and log_arg < 1:
                Saw = (zeta / PI / wk) * SPTf[k]**2 / np.log(1.0 / log_arg)
            else:
                Saw = (zeta / PI / wk) * SPTf[k]**2

            # plateau enhancement: 对接近目标谱平台峰值的频带温和提升 PSD
            # (撤销了会话前的移除, 见上方 NOTE; tests/probe_plateau_tradeoff.py)
            if max_sptf > 0.0:
                plateau_ratio = SPTf[k] / max_sptf
                Saw *= 1.0 + 0.4 / (1.0 + np.exp(-(plateau_ratio - 0.85) / 0.05))

            Saw = max(Saw, 0.0)
            if not np.isfinite(Saw):
                Saw = 0.0
            Ak = 2.0 * np.sqrt(Saw * TWO_PI * fs * nfft / 2)
            # 正频率
            af[k] = Ak * (np.cos(phi) + 1j * np.sin(phi))
            # 负频率（共轭对称）
            af[nfft - k] = Ak * (np.cos(phi) - 1j * np.sin(phi))

        # IFFT (EQSignal: fftw_plan_dft_1d BACKWARD, then /Nfft)
        a0 = np.fft.ifft(af)
        a = np.real(a0[:n])

        return a

    @staticmethod
    def _nextpow2(n):
        """不小于 n 的 2 的整数次幂"""
        p = 1
        while p < n:
            p *= 2
        return p

    @staticmethod
    def _decrfindfirst(a, x):
        """找到递减数组 a 中第一个 <= x 的位置"""
        for i in range(len(a)):
            if a[i] <= x:
                return i
        return len(a) - 1

    @staticmethod
    def _decrfindlast(a, x):
        """找到递减数组 a 中最后一个 >= x 的位置"""
        for i in range(len(a) - 1, -1, -1):
            if a[i] >= x:
                return i
        return 0

    @staticmethod
    def _decrlininterp_core(x, y, xi):
        """递减线性插值（复现 decrlininterp）

        x, xi 均为递减数组。从 x 的最小端开始，逐段插值。
        """
        n = len(x)
        ni = len(xi)
        yi = np.zeros(ni)

        # 从最小值端开始（x[n-1] 是最小的）
        xp = x[n - 1]
        yp = y[n - 1]
        j = 0
        for i in range(1, n):
            xc = x[n - 1 - i]
            yc = y[n - 1 - i]
            if abs(xc - xp) < 1e-30:
                xp = xc
                yp = yc
                continue
            slope = (yc - yp) / (xc - xp)
            while j < ni:
                if xi[j] < xc:
                    break
                yi[j] = yp + slope * (xi[j] - xp)
                j += 1
            xp = xc
            yp = yc
        # 处理剩余点（外推）
        while j < ni:
            yi[j] = yp
            j += 1
        return yi

    @staticmethod
    def _rsimple(pe0, p0, phi, t, zeta):
        """SDOF 对单频激励的响应符号（复现 EQSignal rsimple）"""
        TWO_PI = 2.0 * np.pi
        we = TWO_PI / pe0
        w = TWO_PI / p0

        we2 = we * we
        w2 = w * w
        we3 = we2 * we
        w3 = w2 * w
        we4 = we3 * we
        w4 = w3 * w

        zeta2 = zeta * zeta
        zeta3 = zeta2 * zeta
        zeta4 = zeta3 * zeta

        sinphi = np.sin(phi)
        cosphi = np.cos(phi)

        denom = (8.0*w2*we2*zeta4
                 + (2.0*we4 - 12.0*w2*we2 + 2.0*w4)*zeta2
                 - 2.0*we4 + 4.0*w2*we2 - 2.0*w4)

        if abs(denom) < 1e-30:
            return np.cos(we * t + phi)

        wd_sq = 4.0*w2 - 4.0*w2*zeta2
        wd = np.sqrt(max(wd_sq, 0.0))

        exp_neg = np.exp(-w * zeta * t)
        exp_pos = np.exp(w * zeta * t)

        sin_wet = np.sin(we * t + phi)
        cos_wet = np.cos(we * t + phi)
        sin_wdt = np.sin(wd * t / 2.0)
        cos_wdt = np.cos(wd * t / 2.0)

        inner = ((4.0*w*we3*zeta - 4.0*w*we3*zeta3) * exp_pos * sin_wet
                 + ((2.0*we4 - 2.0*w2*we2)*zeta2 - 2.0*we4 + 2.0*w2*we2)
                 * exp_pos * cos_wet
                 + wd * (4.0*cosphi*w*we2*zeta3
                         + 2.0*sinphi*we3*zeta2
                         + (cosphi*w3 - 3.0*cosphi*w*we2)*zeta
                         - sinphi*we3 + sinphi*w2*we) * sin_wdt
                 + (8.0*cosphi*w2*we2*zeta4
                    + 4.0*sinphi*w*we3*zeta3
                    + (2.0*cosphi*w4 - 10.0*cosphi*w2*we2)*zeta2
                    - 4.0*sinphi*w*we3*zeta
                    + 2.0*cosphi*w2*we2 - 2.0*cosphi*w4) * cos_wdt)

        return cos_wet - exp_neg * inner / denom

    @staticmethod
    def _fitspectra(acc, n, dt, zeta, P, nP, SPAT, tol, max_iter, peak0,
                    progress_callback):
        """频域迭代谱匹配算法（精确复现 EQSignal fitspectra）

        关键：af 在迭代间累积调整，不重新 FFT。

        Returns (best_acc, best_aerror)
        """
        TWO_PI = 2.0 * np.pi
        nfft = WaveGenerator._nextpow2(n) * 4
        iNfft = 1.0 / nfft

        # 频率轴（复现 EQSignal fftfreqs，全谱）
        fs = 1.0 / dt
        df = fs / nfft
        f = np.zeros(nfft)
        f[1:nfft//2] = np.arange(1, nfft//2) * df
        f[nfft//2] = fs / 2.0  # Nyquist
        f[nfft//2+1:] = np.arange(-(nfft//2) + 1, 0) * df

        # Pf: 周期数组（递减）
        # EQSignal: Pf(2:Nfft/2) = 1/f(2:Nfft/2), Pf(1) = 2*Pf(2)
        # Fortran 1-based → Python 0-based
        n_pf = nfft // 2
        Pf = np.zeros(n_pf)
        pos_f = f[1:nfft//2]  # f[1]..f[nfft//2-1], nfft//2-1 elements
        Pf[1:n_pf] = 1.0 / pos_f
        Pf[0] = 2.0 * Pf[1] if n_pf > 1 else 1e6

        # 找频率范围
        IPf1 = WaveGenerator._decrfindfirst(Pf, P[nP - 1])
        IPf2 = WaveGenerator._decrfindlast(Pf, P[0])
        NPf = IPf2 - IPf1 + 1

        # 初始 FFT（使用 r2c 等效：只存正频率部分）
        a0 = np.zeros(nfft)
        a0[:n] = acc
        # 使用 rfft（等效于 FFTW r2c）
        af = np.fft.rfft(a0)
        # af 的索引：af[0]=DC, af[1]=f[1], ..., af[nfft//2]=Nyquist
        # Pf[k] 对应 af[k]（Fortran 中 Pf(k) 和 af(k) 共享索引）

        a = acc.copy()

        # 初始反应谱
        SPA, SPI = WaveGenerator._spamixed(a, dt, zeta, P, nP)
        aerror, merror = WaveGenerator._error(np.abs(SPA), SPAT, nP)

        if aerror <= tol and merror <= 3.0 * tol:
            return a, aerror

        R = SPAT / np.maximum(np.abs(SPA), 1e-30)
        Rf = np.ones(nfft // 2)
        Rf[IPf1:IPf2+1] = WaveGenerator._decrlininterp_core(
            P, R[:int(nP)], Pf[IPf1:IPf2+1])

        minerr = aerror
        best = a.copy()

        iteration = 1
        while (aerror > tol or merror > 3.0 * tol) and iteration <= max_iter:
            # ── rsimple 符号修正（复现 EQSignal fitspectra）──
            j = IPf2
            for i in range(1, nP - 1):
                p0 = P[i]
                t_peak = dt * SPI[i] - dt
                dp = min(p0 - P[i - 1], P[i + 1] - p0)

                while Pf[j] < p0 + 0.5 * dp and j > IPf1:
                    pe0 = Pf[j]
                    # Pf[j] 对应 af[j]
                    phi = np.arctan2(np.imag(af[j]), np.real(af[j]))
                    ra = WaveGenerator._rsimple(pe0, p0, phi, t_peak, zeta)
                    if np.sign(ra) * np.sign(SPA[i]) < 0.0:
                        Rf[j] = 1.0 / Rf[j]
                    j -= 1

            # ── 频域调整（累积在 af 上）──
            af[IPf1:IPf2+1] *= Rf[IPf1:IPf2+1]

            # ── IFFT ──
            a0 = np.fft.irfft(af, nfft)
            a = a0[:n] * 1.0  # rfft/irfft 已归一化

            # ── adjustpeak ──
            a = WaveGenerator._adjust_peak(a, peak0)

            # ── 重新计算反应谱 ──
            SPA, SPI = WaveGenerator._spamixed(a, dt, zeta, P, nP)
            aerror, merror = WaveGenerator._error(np.abs(SPA), SPAT, nP)

            # ── 更新 ratio 和插值（为下次迭代准备）──
            R = SPAT / np.maximum(np.abs(SPA), 1e-30)
            Rf = np.ones(nfft // 2)
            Rf[IPf1:IPf2+1] = WaveGenerator._decrlininterp_core(
                P, R[:int(nP)], Pf[IPf1:IPf2+1])

            if progress_callback:
                progress_callback(iteration, merror, aerror)

            if aerror < minerr:
                minerr = aerror
                best = a.copy()

            iteration += 1

        return best, minerr

    @staticmethod
    def _adjustspectra_atik(acc, n, dt, zeta, P, nP, SPAT, tol, max_iter,
                           progress_callback):
        """时域小波叠加谱匹配算法（Atik & Abrahamson 2010 改进版，全自由度）

        基于 _adjustspectra 的全 nP×nP 响应矩阵，核心改进：
        - 小波：Gaussian → Tapered Cosine（零均值/零一阶矩）
        - 矩阵：全自由度 nP×nP（非降采样 K 点），保留完整控制点耦合
        - 求解：Levenberg-Marquardt 阻尼最小二乘，防止 dR 过大发散
        - 控制：多层级收敛+发散检测，alpha clip 收紧到 ±1e3
        """
        from .spectral_match import _match_to_target_impl

        return _match_to_target_impl(
            np.asarray(acc, dtype=np.float64),
            dt,
            np.asarray(P[:nP], dtype=np.float64),
            np.asarray(SPAT[:nP], dtype=np.float64),
            zeta=zeta,
            tol=tol,
            max_iter=max_iter,
            progress_callback=progress_callback,
        )

    @staticmethod
    def _adjustspectra(acc, n, dt, zeta, P, nP, SPAT, tol, max_iter,
                       progress_callback):
        """时域小波叠加谱匹配算法（复现 EQSignal adjustspectra）

        通过在时域叠加 Gaussian-modulated cosine 小波函数，
        用最小二乘求解调整系数，逐步逼近目标谱。
        比频域法 (fitspectra) 更稳定。

        Returns (best_acc, best_aerror)
        """
        TWO_PI = 2.0 * np.pi
        peak0 = float(np.max(np.abs(acc)))
        a = acc.copy()

        SPA, SPI = WaveGenerator._spamixed(a, dt, zeta, P, nP)
        aerror, merror = WaveGenerator._errora(np.abs(SPA), SPAT, nP)

        if aerror <= tol and merror <= 3.0 * tol:
            return a, aerror

        minerr = aerror
        best = a.copy()
        iteration = 1
        stall = 0

        # 预计算频域法所需常量
        nfft_freq = WaveGenerator._nextpow2(n) * 2
        nf = nfft_freq // 2 + 1
        fs = 1.0 / dt
        df_freq = fs / nfft_freq
        wj = np.zeros(nf)
        wj[1:] = TWO_PI * np.arange(1, nf) * df_freq
        wj2 = wj * wj
        w0_arr = TWO_PI / P

        while iteration <= max_iter:
            if aerror <= tol and merror <= 3.0 * tol:
                break

            # 带符号相对残差，与带符号 M 同约定（见 _adjustspectra_atik 注释）
            dR = np.sign(SPA) - SPA / np.maximum(SPAT, 1e-30)

            # 构造小波函数 W (n x nP)
            W = np.zeros((n, nP))
            for i in range(nP):
                W[:, i] = WaveGenerator._wfunc(n, dt, SPI[i], P[i], zeta)

            # 构造响应矩阵 M (nP x nP) — 全频域批量 FFT
            M = np.zeros((nP, nP))
            spi_idx = SPI - 1  # 0-based 峰值时刻

            W_padded = np.zeros((nP, nfft_freq))
            W_padded[:, :n] = W.T
            Wf = np.fft.rfft(W_padded, axis=1)

            for i in range(nP):
                w0 = w0_arr[i]
                w0i2 = w0 * w0
                w0iwj = w0 * wj
                denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
                safe = np.abs(denom) > 1e-30
                H = np.ones(nf, dtype=complex)
                H[safe] = (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]
                raf = Wf * H[np.newaxis, :]
                ra_all = np.fft.irfft(raf, nfft_freq, axis=1)
                # M[i, :] = 周期 i 振子在其响应峰值时刻 SPI[i] 处对各 wavelet 的响应
                si = spi_idx[i]
                if 0 <= si < n:
                    M[i, :] = ra_all[:, si] / max(SPAT[i], 1e-30)
                else:
                    M[i, i] = 1.0

            # Tikhonov 正则化求解 M·alpha = dR
            alpha = WaveGenerator._solve_tikhonov(M, dR, lam=10.0)
            alpha = np.nan_to_num(alpha, nan=0.0, posinf=0.0, neginf=0.0)
            alpha = np.clip(alpha, -1e3, 1e3)

            W_safe = np.nan_to_num(W, nan=0.0, posinf=0.0, neginf=0.0)
            base_delta = W_safe @ alpha
            base_delta = np.nan_to_num(base_delta, nan=0.0, posinf=0.0, neginf=0.0)
            amax = float(np.max(np.abs(base_delta)))
            if amax > 0.5 * peak0 and amax > 0:
                base_delta *= (0.5 * peak0) / amax

            # Backtracking line-search：误差不降则步长减半，保证单调下降
            improved = False
            s = 1.0
            for _ls in range(8):
                a_trial = a + s * base_delta
                SPA_t, SPI_t = WaveGenerator._spamixed(a_trial, dt, zeta, P, nP)
                ae_t, me_t = WaveGenerator._errora(np.abs(SPA_t), SPAT, nP)
                if ae_t < aerror:
                    a = a_trial
                    SPA, SPI = SPA_t, SPI_t
                    aerror, merror = ae_t, me_t
                    improved = True
                    break
                s *= 0.5

            if progress_callback:
                progress_callback(iteration, merror, aerror)

            if not improved:
                break

            if aerror < minerr - 1e-9:
                minerr = aerror
                best = a.copy()
                stall = 0
            else:
                stall += 1
                if stall >= 3:
                    break

            iteration += 1

        return best, minerr

    @staticmethod
    def _wfunc(n, dt, itm, P, zeta):
        """Gaussian-modulated cosine 小波函数（复现 EQSignal wfunc）

        Parameters
        ----------
        n : int
            信号长度
        dt : float
            时间步长
        itm : int
            峰值时刻索引（1-based）
        P : float
            目标周期
        zeta : float
            阻尼比
        """
        TWO_PI = 2.0 * np.pi
        tm = (itm - 1) * dt
        w = TWO_PI / P
        f = 1.0 / P

        tmp1 = np.sqrt(1.0 - zeta**2)
        gamma = 1.178 * (f * tmp1)**(-0.93)
        deltaT = np.arctan(tmp1 / zeta) / (w * tmp1) if abs(w * tmp1) > 1e-30 else 0.0

        t = np.arange(n) * dt
        tmp2 = t - tm + deltaT

        wf = np.cos(w * tmp1 * tmp2) * np.exp(-(tmp2 / gamma)**2)
        return wf


    @staticmethod
    def _wfunc_atik(n, dt, itm, P, zeta):
        """改进 tapered cosine wavelet（Atik & Abrahamson 2010）

        替换 Gaussian-modulated cosine，采用分段 Hann taper 包络，
        并施加零均值和零一阶矩约束，防止速度/位移漂移。
        """
        TWO_PI = 2.0 * np.pi
        t_peak = (itm - 1) * dt

        f = 1.0 / P
        w = TWO_PI / P
        tmp1 = np.sqrt(1.0 - zeta ** 2)
        w_d = w * tmp1

        deltaT = np.arctan(tmp1 / zeta) / w_d if abs(w_d) > 1e-30 else 0.0

        # 频率自适应持续时间
        n_cycles = 3.0 if P > 0.5 else 5.0
        duration = n_cycles * P

        # 超短周期：采样点过少，跳过矩约束避免压没信号
        n_points_est = int(duration / dt)
        skip_moment_constraints = n_points_est < 12

        tau_rise = 0.25 * duration
        tau_fall = 0.35 * duration
        t_start = t_peak - 0.45 * duration
        t_end = t_start + duration

        t = np.arange(n) * dt
        mask = (t >= t_start) & (t <= t_end)
        t_wave = t[mask]

        if len(t_wave) == 0:
            return np.zeros(n, dtype=np.float64)

        # 包络构造
        envelope = np.zeros_like(t_wave, dtype=np.float64)

        rise_mask = (t_wave >= t_start) & (t_wave < t_start + tau_rise)
        if np.any(rise_mask):
            envelope[rise_mask] = 0.5 * (
                1.0 - np.cos(np.pi * (t_wave[rise_mask] - t_start) / tau_rise)
            )

        flat_mask = (t_wave >= t_start + tau_rise) & (t_wave <= t_end - tau_fall)
        if np.any(flat_mask):
            envelope[flat_mask] = 1.0

        fall_mask = (t_wave > t_end - tau_fall) & (t_wave <= t_end)
        if np.any(fall_mask):
            envelope[fall_mask] = 0.5 * (
                1.0 - np.cos(np.pi * (t_end - t_wave[fall_mask]) / tau_fall)
            )

        # 载波（与旧 _wfunc 一致的相位补偿）
        tau = t_wave - t_peak + deltaT
        carrier = np.cos(w_d * tau)

        # 原始 wavelet
        w_raw = envelope * carrier

        # 施加零均值和零一阶矩约束（超短周期跳过）
        if skip_moment_constraints:
            w_corrected = w_raw
        else:
            w_corrected = WaveGenerator._apply_moment_constraints(
                w_raw, t_wave, t_peak, envelope
            )

        wf = np.zeros(n, dtype=np.float64)
        wf[mask] = w_corrected
        return wf

    @staticmethod
    def _apply_moment_constraints(w_raw, t, t_peak, envelope):
        """对 wavelet 施加零均值和零一阶矩约束（事后修正法）。

        在原始 wavelet 上叠加两个修正基函数的线性组合，
        使修正后的 wavelet 满足 ∫w dt = 0 且 ∫t·w dt = 0。
        """
        # 计算原始矩
        m0 = np.trapz(w_raw, t)
        m1 = np.trapz(w_raw * (t - t_peak), t)

        dt_local = t[1] - t[0] if len(t) > 1 else 1.0
        threshold = 1e-12 * dt_local * len(t)
        if abs(m0) < threshold and abs(m1) < threshold:
            return w_raw

        # 修正基函数
        b0 = envelope.copy()
        b1 = envelope * (t - t_peak)

        # Gram 矩阵
        g00 = np.trapz(b0, t)
        g01 = np.trapz(b0 * (t - t_peak), t)
        g11 = np.trapz(b1 * (t - t_peak), t)

        G = np.array([[g00, g01], [g01, g11]])

        try:
            coeffs = np.linalg.solve(G, [m0, m1])
        except np.linalg.LinAlgError:
            coeffs = np.array([m0 / g00 if g00 > 1e-30 else 0.0, 0.0])

        return w_raw - coeffs[0] * b0 - coeffs[1] * b1

    @staticmethod
    def _select_control_points(periods, target, current, K, nP):
        """自适应分批选择控制点。

        按误差降序选择，排除相邻点（避免 wavelet 重叠干涉）。
        始终包含首尾两个端点。
        """
        rel_error = np.abs(target - current) / np.maximum(target, 1e-30)
        selected = [0, nP - 1]
        sorted_indices = np.argsort(rel_error)[::-1]

        for idx in sorted_indices:
            if len(selected) >= K:
                break
            if idx in selected:
                continue

            P_idx = float(periods[idx])
            min_sep = 0.15 * P_idx

            too_close = False
            for s in selected:
                if abs(float(periods[s]) - P_idx) < min_sep:
                    too_close = True
                    break

            if not too_close:
                selected.append(idx)

        return sorted(selected)

    @staticmethod
    def _adaptive_K(aerror, nP):
        """根据当前误差自适应选择 K 值。"""
        if aerror > 0.30:
            return min(50, nP)
        elif aerror > 0.15:
            return min(80, nP)
        elif aerror > 0.05:
            return min(120, nP)
        else:
            return min(150, nP)

    @staticmethod
    def _solve_tikhonov(M, dR, lam=1.0):
        """Tikhonov 正则化求解 (M^T M + lam*I) alpha = M^T dR"""
        # 退化输入时矩阵可能含极大值，运算会触发 over/invalid 警告；
        # 下方 nan_to_num+clip 已兜底，这里静默以免刷屏（不改变数值结果）。
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            MtM = M.T @ M
            MtdR = M.T @ dR
            # 添加正则化
            A = MtM + lam * np.eye(M.shape[1])
            try:
                alpha = np.linalg.solve(A, MtdR)
            except np.linalg.LinAlgError:
                alpha, _, _, _ = np.linalg.lstsq(A, MtdR, rcond=None)
        alpha = np.nan_to_num(alpha, nan=0.0, posinf=0.0, neginf=0.0)
        alpha = np.clip(alpha, -1e3, 1e3)
        return alpha

    @staticmethod
    def _update_lambda(lambda_prev, error_prev, error_current, factor=4.0):
        """LM 阻尼因子自适应更新。"""
        if error_current < error_prev:
            return max(lambda_prev / factor, 1e-6)
        else:
            return min(lambda_prev * factor, 1e6)


    @staticmethod
    def _ramixed(acc, n, dt, zeta, P):
        """混合法计算单周期绝对加速度响应时程（复现 EQSignal ramixed）

        短周期用频域法，长周期用 Newmark-β 法。
        返回长度为 n 的响应时程数组。
        """
        threshold = WaveGenerator.MPR * dt
        if P < threshold:
            return WaveGenerator._rafreq(acc, n, dt, zeta, P)
        else:
            return WaveGenerator._ranmk(acc, n, dt, zeta, P)

    @staticmethod
    def _ramixed_batch(acc, n, dt, zeta, periods, nP):
        """批量计算所有周期的绝对加速度响应时程

        返回 (nP, n) 数组。频域周期共享一次 FFT。
        """
        TWO_PI = 2.0 * np.pi
        threshold = WaveGenerator.MPR * dt
        result = np.zeros((nP, n))

        # 分离短周期和长周期
        freq_idx = []
        time_idx = []
        for i in range(nP):
            if periods[i] < threshold:
                freq_idx.append(i)
            else:
                time_idx.append(i)

        # 频域法：共享一次 FFT
        if freq_idx:
            nfft = WaveGenerator._nextpow2(n) * 2
            a0 = np.zeros(nfft)
            a0[:n] = acc
            af = np.fft.rfft(a0)

            fs = 1.0 / dt
            df = fs / nfft
            w_arr = np.zeros(nfft // 2 + 1)
            w_arr[1:] = TWO_PI * np.arange(1, nfft // 2 + 1) * df
            wj2 = w_arr * w_arr
            IONE = 1j

            for i in freq_idx:
                w0 = TWO_PI / periods[i]
                w0i2 = w0 * w0
                w0iwj = w0 * w_arr
                denom = w0i2 - wj2 + 2.0 * zeta * w0iwj * IONE
                # 避免除零
                safe = np.abs(denom) > 1e-30
                raf = np.zeros(nfft // 2 + 1, dtype=complex)
                raf[safe] = af[safe] * (w0i2 + 2.0 * zeta * w0iwj[safe] * IONE) / denom[safe]
                raf[~safe] = af[~safe]
                ra = np.fft.irfft(raf, nfft)
                result[i, :] = ra[:n]

        # 时域法
        for i in time_idx:
            result[i, :] = WaveGenerator._ranmk(acc, n, dt, zeta, periods[i])

        return result

    @staticmethod
    def _rafreq(acc, n, dt, zeta, P):
        """频域法计算绝对加速度响应时程（复现 EQSignal rafreq）"""
        TWO_PI = 2.0 * np.pi
        nfft = WaveGenerator._nextpow2(n) * 2

        a0 = np.zeros(nfft)
        a0[:n] = acc
        af = np.fft.rfft(a0)

        fs = 1.0 / dt
        df = fs / nfft
        nf = nfft // 2 + 1
        wj = np.zeros(nf)
        wj[1:] = TWO_PI * np.arange(1, nf) * df
        wj2 = wj * wj

        w0 = TWO_PI / P
        w0i2 = w0 * w0
        w0iwj = w0 * wj

        denom = w0i2 - wj2 + 2.0j * zeta * w0iwj
        safe = np.abs(denom) > 1e-30
        raf = af.copy()
        raf[safe] = af[safe] * (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]

        ra = np.fft.irfft(raf, nfft)
        return ra[:n]

    @staticmethod
    def _ranmk(acc, n, dt, zeta, P):
        """Newmark-β 法计算绝对加速度响应时程（复现 EQSignal ranmk）"""
        from .spectrum import Spectra
        ra_rel, rv, rd = Spectra._newmark_beta(acc, dt, P, zeta)
        # 绝对加速度 = 地面加速度 - 相对加速度
        abs_acc = np.zeros(n)
        nn = min(n, len(ra_rel))
        abs_acc[:nn] = -ra_rel[:nn] + acc[:nn]
        return abs_acc

    @staticmethod
    def _spafreq(acc, n, dt, zeta, periods, nP):
        """频域法反应谱（复现 EQSignal spafreq）

        用于短周期（T < MPR*dt），与频域迭代调整自洽。
        返回带符号的 SPA 和峰值位置 SPI（1-based）。
        向量化实现：传递函数计算无 Python 循环。
        """
        TWO_PI = 2.0 * np.pi
        nfft = WaveGenerator._nextpow2(n)

        # FFT
        a0 = np.zeros(nfft)
        a0[:n] = acc
        af = np.fft.rfft(a0)  # (nfft//2+1,)

        # 频率轴（角频率）
        fs = 1.0 / dt
        df = fs / nfft
        nf = nfft // 2 + 1
        wj = np.zeros(nf)
        wj[1:] = TWO_PI * np.arange(1, nf) * df
        wj2 = wj * wj

        spa = np.zeros(nP)
        spi = np.ones(nP, dtype=np.int32)

        # 向量化：对每个周期，批量计算传递函数
        w0_arr = TWO_PI / periods[:nP]  # (nP,)
        for i in range(nP):
            w0 = w0_arr[i]
            w0i2 = w0 * w0
            w0iwj = w0 * wj  # (nf,)
            denom = w0i2 - wj2 + 2.0j * zeta * w0iwj  # (nf,)
            safe = np.abs(denom) > 1e-30
            raf = af.copy()
            raf[safe] = af[safe] * (w0i2 + 2.0j * zeta * w0iwj[safe]) / denom[safe]

            ra = np.fft.irfft(raf, nfft)
            ra_n = ra[:n]
            idx = np.argmax(np.abs(ra_n))
            spa[i] = ra_n[idx]
            spi[i] = idx + 1

        return spa, spi

    @staticmethod
    def _spamixed(acc, dt, zeta, periods, nP):
        """混合反应谱计算（复现 EQSignal spamixed）

        短周期（T < MPR*dt）用频域法（与频域迭代自洽），
        长周期用 Newmark-β 法（精度更高）。
        """
        n = len(acc)
        threshold = WaveGenerator.MPR * dt  # MPR=20

        # 找分界点：与 Fortran spamixed 一致，P(1:m) 包含第一个 >= threshold 的周期
        # Fortran: m=1; do while(P(m)<MPR*dt) m=m+1; spafreq(P(1:m))
        # 即 P(m) 是第一个 >= threshold 的，也归频域法处理
        m = 0
        while m < nP and periods[m] < threshold:
            m += 1
        # 包含第一个 >= threshold 的周期（如果存在）
        if m < nP:
            m += 1

        spa = np.zeros(nP, dtype=np.float64)
        spi = np.ones(nP, dtype=np.int32)

        # 短周期：频域法
        if m > 0:
            spa[:m], spi[:m] = WaveGenerator._spafreq(
                acc, n, dt, zeta, periods[:m], m)

        # 长周期：Newmark-β
        if m < nP:
            long_periods = periods[m:nP]
            n_long = nP - m

            acc_c = np.ascontiguousarray(acc, dtype=np.float64)
            long_p = np.ascontiguousarray(long_periods, dtype=np.float64)
            spa_long = np.zeros(n_long, dtype=np.float64)
            spi_long = np.zeros(n_long, dtype=np.int32)

            if _c_lib is not None:
                _c_lib.newmark_spectrum(
                    acc_c.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                    n, dt, zeta,
                    long_p.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                    n_long,
                    spa_long.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                    spi_long.ctypes.data_as(ctypes.POINTER(ctypes.c_int)),
                )
            else:
                from concurrent.futures import ThreadPoolExecutor
                from .spectrum import HAS_NUMBA, Spectra, _newmark_beta_task

                if HAS_NUMBA and n_long > 1:
                    tasks = [(acc_c, dt, float(T), zeta) for T in long_periods]
                    with ThreadPoolExecutor() as executor:
                        results = list(executor.map(_newmark_beta_task, tasks))
                    for i, (ra_rel, rv, rd) in enumerate(results):
                        abs_acc = -ra_rel + acc_c[:len(ra_rel)]
                        idx = np.argmax(np.abs(abs_acc))
                        spa_long[i] = abs_acc[idx]
                        spi_long[i] = idx + 1
                else:
                    out_ra = np.zeros(n, dtype=np.float64)
                    out_rv = np.zeros(n, dtype=np.float64)
                    out_rd = np.zeros(n, dtype=np.float64)
                    for i in range(n_long):
                        ra_rel, rv, rd = Spectra._newmark_beta(
                            acc_c, dt, long_periods[i], zeta, out_ra, out_rv, out_rd)
                        abs_acc = -ra_rel + acc_c[:len(ra_rel)]
                        idx = np.argmax(np.abs(abs_acc))
                        spa_long[i] = abs_acc[idx]
                        spi_long[i] = idx + 1

            spa[m:nP] = spa_long
            spi[m:nP] = spi_long

        return spa, spi

    @staticmethod
    def _error(y, y0, n):
        """相对误差（复现 error）：跳过首尾与近零目标点。"""
        if n <= 2:
            section_y = y[:n]
            section_y0 = y0[:n]
        else:
            section_y = y[1:n-1]
            section_y0 = y0[1:n-1]

        mask = np.abs(section_y0) > 1e-12
        if not np.any(mask):
            return 0.0, 0.0

        e = (section_y[mask] - section_y0[mask]) / section_y0[mask]
        aerror = float(np.sqrt(np.mean(e * e)))
        merror = float(np.max(np.abs(e)))
        return aerror, merror

    @staticmethod
    def _errora(y, y0, n):
        """相对误差（复现 errora）：包括所有元素，用于 adjustspectra"""
        e = (y[:n] - y0[:n]) / np.maximum(np.abs(y0[:n]), 1e-30)
        aerror = float(np.sqrt(np.mean(e * e)))
        merror = float(np.max(np.abs(e)))
        return aerror, merror

    @staticmethod
    def _adjust_peak_linear(acc, peak_target):
        """全局线性缩放增压（替代单点硬裁剪），保持谱形不变。

        当 current_peak < peak_target 时，整个信号统一乘以
        peak_target / current_peak，不做任何裁剪或单点硬推。
        """
        result = acc.copy()
        current_peak = float(np.max(np.abs(result)))
        if current_peak < 1e-30 or current_peak >= peak_target:
            return result
        scale = peak_target / current_peak
        return result * scale

    @staticmethod
    def _adjust_peak_staged(acc, peak_target, stages=4, adjust_fn=None):
        """分阶段渐进增压，每步使用全局线性缩放而非单点硬裁剪。

        Parameters
        ----------
        acc : np.ndarray
            输入加速度时程
        peak_target : float
            目标 PGA
        stages : int
            分阶段数（默认 4）
        adjust_fn : callable, optional
            每阶段后可选的谱形修正回调，签名 adjust_fn(acc) -> acc

        Returns
        -------
        np.ndarray
            增压后的加速度时程
        """
        result = acc.copy()
        current_peak = float(np.max(np.abs(result)))
        if current_peak < 1e-30 or current_peak >= peak_target:
            return result

        step_targets = np.linspace(current_peak, peak_target, stages + 1)[1:]
        for step_target in step_targets:
            scale = step_target / float(np.max(np.abs(result)))
            result = result * scale
            if adjust_fn is not None:
                result = adjust_fn(result)
        return result

    @staticmethod
    def _adjust_peak(acc, peak0):
        """裁剪峰值（复现 EQSignal adjustpeak）"""
        result = acc.copy()
        pk = int(np.argmax(np.abs(result)))
        peak = result[pk]
        result = np.clip(result, -peak0, peak0)
        if abs(peak) < peak0:
            result[pk] = np.sign(peak) * peak0 if peak != 0 else peak0
        return result

    @staticmethod
    def _envelope(n, dt):
        """时域包络函数（Saragoni & Hart 型）"""
        t_total = (n - 1) * dt
        t = np.arange(n) * dt
        t_peak = t_total * 0.2
        b = 2.0
        c = b / t_peak
        env = np.zeros(n)
        mask = t > 0
        env[mask] = (t[mask] / t_peak) ** b * np.exp(-c * (t[mask] - t_peak))
        env_max = np.max(env)
        if env_max > 0:
            env /= env_max
        return env

    @staticmethod
    def _resolve_envelope(n, dt, envelope_values=None):
        """返回生成器应使用的包络数组。"""
        if envelope_values is None:
            return WaveGenerator._envelope(n, dt)

        env = np.asarray(envelope_values, dtype=np.float64)
        if env.ndim != 1 or len(env) != n:
            raise ValueError(
                f"envelope_values 长度应为 {n}，得到 {env.shape}"
            )
        return env.copy()

    @staticmethod
    def fit_error(actual, target):
        """计算拟合误差，跳过首尾与近零目标点。"""
        actual = np.asarray(actual, dtype=np.float64)
        target = np.asarray(target, dtype=np.float64)
        n = len(target)
        if n <= 2:
            section_actual = actual[:n]
            section_target = target[:n]
        else:
            section_actual = actual[1:n-1]
            section_target = target[1:n-1]

        mask = np.abs(section_target) > 1e-12
        if not np.any(mask):
            return {'max_error': 0.0, 'mean_error': 0.0}

        e = (section_actual[mask] - section_target[mask]) / section_target[mask]
        e_max = float(np.max(np.abs(e))) if len(e) > 0 else 0.0
        e_mean = float(np.sqrt(np.mean(e ** 2))) if len(e) > 0 else 0.0
        return {'max_error': e_max, 'mean_error': e_mean}


def create_ground_motion(type, Mw, R, Vs30=760.0, fault_type="strike_slip",
                         n=4096, dt=0.02, zeta=0.05, tol=0.05, max_iter=20,
                         **kwargs):
    """便捷工厂函数：按类型创建特殊地震动。"""
    from .gmpe import GMPEAdapter, FaultType, MotionType

    ft_map = {
        "strike_slip": FaultType.STRIKE_SLIP,
        "normal": FaultType.NORMAL,
        "reverse": FaultType.REVERSE,
    }
    ft = ft_map.get(fault_type, FaultType.STRIKE_SLIP)

    if type == "FF":
        return FarFieldGenerator.generate(
            Mw=Mw, R=R, Vs30=Vs30, fault_type=fault_type,
            n=n, dt=dt, zeta=zeta, tol=tol, max_iter=max_iter,
            **kwargs,
        )
    elif type == "NF":
        return NearFieldNoPulseGenerator.generate(
            Mw=Mw, R=R, Vs30=Vs30, fault_type=fault_type,
            n=n, dt=dt, zeta=zeta, tol=tol, max_iter=max_iter,
            **kwargs,
        )
    elif type == "NFP":
        return NearFieldPulseGenerator.generate(
            Mw=Mw, R=R, Vs30=Vs30, fault_type=fault_type,
            n=n, dt=dt, zeta=zeta, tol=tol, max_iter=max_iter,
            **kwargs,
        )
    else:
        raise ValueError(f"无效的地震动类型: {type}")


# ═══════════════════ 特殊地震动生成器 ═══════════════════


# ── 通用辅助 ──

_FaultType_map = {
    "strike_slip": lambda: FaultType.STRIKE_SLIP,
    "normal": lambda: FaultType.NORMAL,
    "reverse": lambda: FaultType.REVERSE,
}


def _resolve_fault_type(fault_type: str):
    """字符串断层类型 → FaultType 枚举（惰性导入避免循环依赖）。"""
    from .gmpe import FaultType
    ft_map = {
        "strike_slip": FaultType.STRIKE_SLIP,
        "normal": FaultType.NORMAL,
        "reverse": FaultType.REVERSE,
    }
    return ft_map.get(fault_type, FaultType.STRIKE_SLIP)


def _attach_spectrum_meta(sig, target_sa, periods):
    """把目标谱和周期附加到 EQSignal 实例。"""
    sig.total_spectrum = np.asarray(target_sa, dtype=np.float64)
    sig.spectrum_periods = np.asarray(periods, dtype=np.float64)
    return sig


def _estimate_pga_from_spectrum(target_sa):
    """用目标谱首点估计 PGA（频域法迭代用）。"""
    if len(target_sa) == 0:
        return 0.1
    return float(np.max(target_sa))


def _near_field_factor(R, motion_type):
    """近断层放大系数（GB50011-2010 §3.10 + 附录L）。

    距发震断裂 <5km → 1.5；5–10km → 1.25；>10km → 1.0。
    远场（FF）不放大，恒为 1.0。
    """
    from .gmpe import MotionType
    if motion_type == MotionType.FAR_FIELD:
        return 1.0
    if R < 5.0:
        return 1.5
    if R <= 10.0:
        return 1.25
    return 1.0


def _build_special_target(spectrum_source, code_periods, code_sa,
                          factor, gmpe_compute):
    """特殊地震动目标谱构造。

    spectrum_source="code"（方案甲，默认）且提供了 GB50011 谱时，目标谱 =
    code_sa × 近场系数，直接沿用 code 周期网格（不重采样，保持规范谱 T<0.1s 上升/
    平台段与误差口径一致）。否则回退到 GMPE 情景谱（方案乙 / 向后兼容）。
    """
    use_code = (spectrum_source == "code" and code_periods is not None
                and code_sa is not None and len(np.asarray(code_sa)) > 0)
    if use_code:
        return (np.asarray(code_periods, dtype=np.float64),
                np.asarray(code_sa, dtype=np.float64) * factor)
    return gmpe_compute()


def _special_gmpe_compute(spectrum_source, Mw, R, Vs30, ft, motion_type,
                          region, axis):
    """按 spectrum_source 选择 GMPE：
    - "gmpe" → ChinaGMPEAdapter（第五代区划 GB18306-2015，符合规范）
    - 其它（回退）→ 简化 ASK14 GMPEAdapter（仅用于无 code_sa 的兼容回退）
    """
    from .gmpe import GMPEAdapter
    if spectrum_source == "gmpe":
        from .gmpe import ChinaGMPEAdapter
        return ChinaGMPEAdapter.compute_spectrum(Mw, R, region=region, axis=axis)
    return GMPEAdapter.compute_spectrum(
        Mw=Mw, R=R, Vs30=Vs30, fault_type=ft, motion_type=motion_type)



# ── FarFieldGenerator ──

class FarFieldGenerator:
    """远场地震动生成器：GMPE 远场目标谱 + 时域谱匹配 (fm=1)。"""

    @classmethod
    def generate(cls,
                 Mw, R, Vs30=760, fault_type="strike_slip",
                 n=None, dt=None, zeta=None,
                 tol=0.05, max_iter=20, fm=1,
                 progress_callback=None,
                 spectrum_source="code", code_periods=None, code_sa=None,
                 region="east_strong", axis="major",
                 **kwargs):
        from .gmpe import MotionType
        from .envelope_presets import get_envelope
        n = n or 4096
        dt = dt or 0.02
        zeta = zeta or 0.05

        ft = _resolve_fault_type(fault_type)
        # 近场系数仅在规范设计谱(code)模式下应用；GMPE 模式由衰减关系自含距离效应
        factor = (1.0 if spectrum_source == "gmpe"
                  else _near_field_factor(R, MotionType.FAR_FIELD))
        periods, target_sa = _build_special_target(
            spectrum_source, code_periods, code_sa, factor,
            lambda: _special_gmpe_compute(spectrum_source, Mw, R, Vs30, ft,
                                          MotionType.FAR_FIELD, region, axis),
        )

        pga = _estimate_pga_from_spectrum(target_sa)
        envelope_values = get_envelope("FF").envelope_at(n, dt)
        sig = WaveGenerator.generate(
            target_spectrum=target_sa, periods=periods,
            n=n, dt=dt, zeta=zeta, pga=pga,
            tol=tol, max_iter=max_iter, fm=fm,
            n_trials=1,  # 情景波单次实现即可，避免 3 个随机重启拖慢
            progress_callback=progress_callback,
            envelope_values=envelope_values,
        )
        sig.name = f"FF_M{Mw:.1f}_R{R:.1f}"
        sig.near_field_factor = factor
        sig.spectrum_source = spectrum_source
        return _attach_spectrum_meta(sig, target_sa, periods)


# ── NearFieldNoPulseGenerator ──

class NearFieldNoPulseGenerator:
    """近场无脉冲地震动生成器：GMPE 近场目标谱 + 时域谱匹配 (fm=1)。"""

    @classmethod
    def generate(cls,
                 Mw, R, Vs30=760, fault_type="strike_slip",
                 n=None, dt=None, zeta=None,
                 tol=0.05, max_iter=20, fm=1,
                 progress_callback=None,
                 spectrum_source="code", code_periods=None, code_sa=None,
                 region="east_strong", axis="major",
                 **kwargs):
        from .gmpe import MotionType
        from .envelope_presets import get_envelope
        n = n or 4096
        dt = dt or 0.01
        zeta = zeta or 0.05

        ft = _resolve_fault_type(fault_type)
        factor = (1.0 if spectrum_source == "gmpe"
                  else _near_field_factor(R, MotionType.NEAR_FIELD))
        periods, target_sa = _build_special_target(
            spectrum_source, code_periods, code_sa, factor,
            lambda: _special_gmpe_compute(spectrum_source, Mw, R, Vs30, ft,
                                          MotionType.NEAR_FIELD, region, axis),
        )

        pga = _estimate_pga_from_spectrum(target_sa)
        envelope_values = get_envelope("NF").envelope_at(n, dt)
        sig = WaveGenerator.generate(
            target_spectrum=target_sa, periods=periods,
            n=n, dt=dt, zeta=zeta, pga=pga,
            tol=tol, max_iter=max_iter, fm=fm,
            n_trials=1,  # 情景波单次实现即可，避免 3 个随机重启拖慢
            progress_callback=progress_callback,
            envelope_values=envelope_values,
        )
        sig.name = f"NF_M{Mw:.1f}_R{R:.1f}"
        sig.near_field_factor = factor
        sig.spectrum_source = spectrum_source
        return _attach_spectrum_meta(sig, target_sa, periods)


# ── NearFieldPulseGenerator ──

class NearFieldPulseGenerator:
    """近场脉冲地震动生成器：直接匹配 + 脉冲注入法。

    策略：
    1. 频域匹配 GMPE total_sa → base_signal
    2. 时域注入 MP 脉冲分量，搜索最优缩放因子 sf
    3. 小幅频域校正使叠加谱贴近目标
    4. Baker 识别 has_pulse=True & confidence>=0.85，取 mean_error 最小
    """

    @classmethod
    def generate(cls,
                 Mw, R, Vs30=760, fault_type="strike_slip",
                 n=None, dt=None, zeta=None,
                 tol=0.05, max_iter=20, fm=0,
                 progress_callback=None,
                 phi=None, t_total=None,
                 Tp_override=None, A_override=None,
                 phi_override=None, t0_override=None,
                 spectrum_source="code", code_periods=None, code_sa=None,
                 region="east_strong", axis="major",
                 **kwargs):
        from .gmpe import MotionType
        from .pulse import PulseCalculator, PulseWavelet, BakerPulseDetector
        from .residual import ResidualSpectrum
        from .signal import EQSignal as EQSig
        from .spectrum import Spectra
        from .envelope_presets import get_envelope

        n = n or 4096
        dt = dt or 0.01
        zeta = zeta or 0.05

        ft = _resolve_fault_type(fault_type)
        # NFP 默认倾向 reverse（与旧版一致）
        if fault_type not in ("strike_slip", "normal", "reverse"):
            from .gmpe import FaultType
            ft = FaultType.REVERSE

        factor = (1.0 if spectrum_source == "gmpe"
                  else _near_field_factor(R, MotionType.NEAR_FIELD_PULSE))
        periods, total_sa = _build_special_target(
            spectrum_source, code_periods, code_sa, factor,
            lambda: _special_gmpe_compute(spectrum_source, Mw, R, Vs30, ft,
                                          MotionType.NEAR_FIELD_PULSE, region, axis),
        )

        # ── 1) 频域匹配生成基础信号 ──
        pga = _estimate_pga_from_spectrum(total_sa)
        base_signal = WaveGenerator.generate(
            target_spectrum=total_sa, periods=periods,
            n=n, dt=dt, zeta=zeta, pga=pga,
            tol=tol, max_iter=max_iter, fm=0,
            n_trials=1,
            progress_callback=progress_callback,
        )

        # ── 2) 生成 MP 脉冲分量 ──
        t_total_eff = t_total if t_total is not None else n * dt
        pulse_params = PulseCalculator.compute_params(
            Mw=Mw, R=R, fault_type=fault_type,
            phi=phi, t_total=t_total_eff,
            Tp_override=Tp_override, A_override=A_override,
            phi_override=phi_override, t0_override=t0_override,
        )
        # 脉冲有效持时 = γ·Tp，必须完整容纳于信号内，否则脉冲被截断、结果失真
        required_dur = pulse_params.gamma * pulse_params.Tp
        if n * dt < required_dur:
            min_n = int(np.ceil(required_dur / dt)) + 1
            raise ValueError(
                f"信号时长 {n * dt:.1f}s 不足以容纳脉冲(γ·Tp={required_dur:.1f}s, "
                f"Tp={pulse_params.Tp:.2f}s, γ={pulse_params.gamma:.1f})；"
                f"请将点数 n 增至 ≥ {min_n}（Mw 越大脉冲越长）"
            )
        pulse_vel_cm, pulse_acc_cm = PulseWavelet.generate(pulse_params, dt, n)
        # cm/s² → g
        pulse_acc_g = pulse_acc_cm / 980.0
        envelope_values = get_envelope("NFP").envelope_at(n, dt)

        # ── 3) 用残余谱分解搜索最优脉冲缩放因子，并对总波小幅频域校正 ──
        sf_candidates = [0.2, 0.3, 0.5, 0.7, 1.0]

        best_sig = None
        best_rank = None
        best_sf = 1.0
        best_metrics = None
        best_residual_result = None
        best_residual_acc = None

        for sf in sf_candidates:
            residual_acc, residual_result = ResidualSpectrum.generate(
                total_sa=total_sa,
                pulse_acc=pulse_acc_g * sf,
                dt=dt,
                periods=periods,
                zeta=zeta,
                n=n,
                tol=tol,
                max_iter=max_iter,
                # 残差分解固定用快速频域法（fm=0）：这是内部分解步骤，无需慢速时域
                # line-search 匹配；否则 NFP 在 5× sf 候选上会非常慢（界面卡在100%）。
                fm=0,
                correct_combined=False,
                envelope_values=envelope_values,
            )
            combined_acc = ResidualSpectrum.combine(
                residual_result.scaled_pulse_acc, residual_acc
            )
            corrected_acc = cls._small_freq_correct(
                combined_acc, dt, total_sa, periods
            )

            sig = EQSig(corrected_acc, dt, name="artificial")
            sig.a2vd()

            # EQSignal.acc 以 g 为单位时，积分后的速度需乘以 980 转为 cm/s。
            vel_cm_s = sig.vel * 980.0
            metrics = BakerPulseDetector.analyze(vel_cm_s, dt)

            gen_sa = Spectra.compute(
                sig.acc, sig.dt, periods, zeta=0.05, method="mixed"
            ).sa
            fit = WaveGenerator.fit_error(gen_sa, total_sa)
            pulse_period = metrics.get("pulse_period", 0.0)
            if pulse_period > 0:
                period_misfit = abs(np.log(pulse_period / pulse_params.Tp))
            else:
                period_misfit = float("inf")

            required_ok = (
                metrics["has_pulse"]
                and metrics["confidence"] >= 0.85
                and not residual_result.residual_has_pulse
            )
            pgv_gap = abs(max(100.0 - metrics["pulse_amplitude"], 0.0))

            if required_ok and metrics["pulse_amplitude"] >= 100.0:
                rank = (0, fit["mean_error"], period_misfit)
            elif required_ok:
                rank = (1, pgv_gap, fit["mean_error"], period_misfit)
            else:
                rank = (2, -metrics["confidence"], fit["mean_error"], period_misfit)

            if best_rank is None or rank < best_rank:
                best_rank = rank
                best_sig = sig
                best_sf = sf
                best_metrics = metrics
                best_residual_result = residual_result
                best_residual_acc = residual_acc.copy()

        # ── 4) 附加元数据（保留旧版接口）──
        if best_sig is None or best_metrics is None or best_residual_result is None:
            raise RuntimeError("NFP 候选搜索失败")

        pulse_acc = np.asarray(best_residual_result.scaled_pulse_acc, dtype=np.float64)
        residual_acc = best_sig.acc - pulse_acc
        residual_sig = EQSig(residual_acc, dt, name="residual")
        residual_sig.a2vd()
        residual_metrics = BakerPulseDetector.analyze(residual_sig.vel * 980.0, dt)
        pulse_scale = float(best_sf * best_residual_result.scaling_factor)
        # 脉冲速度 = 实际进入信号的脉冲分量(pulse_acc)的积分，与 sig.vel 同单位(g·s)，
        # 绘图时 ×980 得 cm/s。避免旧式 pulse_vel_cm*scale/100 的单位错误(放大~9.8倍)。
        pulse_sig = EQSig(pulse_acc, dt, name="pulse")
        pulse_sig.a2vd()

        best_sig.name = f"NFP_M{Mw:.1f}_R{R:.1f}"
        best_sig.near_field_factor = factor
        best_sig.spectrum_source = spectrum_source
        best_sig.pulse_params = pulse_params
        best_sig.pulse_metrics = best_metrics
        best_sig.pulse_acc = pulse_acc
        best_sig.pulse_vel = pulse_sig.vel
        best_sig.residual_acc = residual_acc
        best_sig.residual_has_pulse = residual_metrics["has_pulse"]
        best_sig.residual_pulse_metrics = residual_metrics

        residual_sa = Spectra.compute(
            residual_acc, dt, periods, zeta=0.05, method="mixed"
        ).sa
        best_sig.residual_spectrum = residual_sa
        best_sig.residual_target_spectrum = np.asarray(
            best_residual_result.residual_spectrum, dtype=np.float64
        )

        # 脉冲谱
        pulse_sa = Spectra.compute(
            best_sig.pulse_acc, dt, periods, zeta=0.05, method="mixed"
        ).sa
        best_sig.pulse_spectrum = pulse_sa

        best_sig.total_spectrum = np.asarray(total_sa, dtype=np.float64)
        best_sig.spectrum_periods = np.asarray(periods, dtype=np.float64)
        best_sig.scaling_factor = pulse_scale
        return best_sig

    @staticmethod
    def _small_freq_correct(acc, dt, target_sa, periods):
        """小幅频域校正：ratio = target / current，clip [0.6, 1.4]。"""
        from scipy.interpolate import interp1d
        from .spectrum import Spectra

        n = len(acc)
        current_sa = Spectra.compute(
            acc, dt, periods, zeta=0.05, method="mixed"
        ).sa
        ratio = target_sa / np.maximum(current_sa, 1e-30)
        ratio = np.clip(ratio, 0.6, 1.4)

        # FFT
        nfft = WaveGenerator._nextpow2(n) * 4
        af = np.fft.rfft(acc, n=nfft)

        # 正频率轴
        fs = 1.0 / dt
        df = fs / nfft
        pos_freq = np.arange(1, len(af)) * df

        # 周期递增 → 频率递减；反转后频率递增
        T_valid = periods[periods > 0]
        f_ctrl = 1.0 / T_valid[::-1]
        ratio_ctrl = ratio[periods > 0][::-1]

        if len(f_ctrl) >= 2:
            f_interp = interp1d(
                np.log(f_ctrl), ratio_ctrl,
                kind="linear", bounds_error=False,
                fill_value=(ratio_ctrl[0], ratio_ctrl[-1]),
            )
            ratio_freq = f_interp(np.log(pos_freq))
            ratio_freq = np.nan_to_num(ratio_freq, nan=1.0)
        else:
            ratio_freq = np.ones(len(pos_freq))

        Rf = np.ones(len(af), dtype=np.float64)
        Rf[1:] = ratio_freq

        af *= Rf
        corrected = np.fft.irfft(af, n=nfft)[:n]
        return corrected

    @classmethod
    def validate(cls, sig, target_spectrum=None, periods=None, zeta=0.05):
        """验证生成信号与目标谱的匹配误差（backward-compatible）。"""
        from .spectrum import Spectra
        if target_spectrum is None or periods is None:
            if hasattr(sig, "total_spectrum") and hasattr(sig, "spectrum_periods"):
                target_spectrum = sig.total_spectrum
                periods = sig.spectrum_periods
            else:
                raise ValueError("validate 需要 target_spectrum 和 periods")
        gen_sa = Spectra.compute(
            sig.acc, sig.dt, periods, zeta=zeta, method="mixed"
        ).sa
        return WaveGenerator.fit_error(gen_sa, target_spectrum)
