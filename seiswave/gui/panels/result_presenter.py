"""结果绘图与文本格式化"""

import numpy as np
from PySide6.QtCore import QObject

from seiswave.core import WaveGenerator, Spectra
from seiswave.gui.styles import get_mpl_colors


class ResultPresenter(QObject):
    """所有 matplotlib 绘图 + 文本格式化，不耦合生成逻辑"""

    def __init__(self, spec_plot, time_plot, dark=False, parent=None):
        super().__init__(parent)
        self._spec_plot = spec_plot
        self._time_plot = time_plot
        self._dark = dark
        self._generated = None

    def set_dark(self, dark):
        self._dark = dark
        self._spec_plot.set_dark(dark)
        self._time_plot.set_dark(dark)

    def get_generated(self):
        return self._generated

    # ────────────────────────── 一般人工波 ──────────────────────────

    def present_general(self, result, code_periods, code_sa):
        """呈现多 trial 一般人工波结果

        Args:
            result: dict with 'best', 'all_results', 'best_index'
            code_periods, code_sa: 规范谱数据

        Returns:
            (info_lines, progress_text)
        """
        best = result['best']
        all_results = result['all_results']
        best_idx = result['best_index']
        self._generated = best

        colors = get_mpl_colors(self._dark)
        palette = colors['palette']

        trial_spectra = []
        trial_errors = []
        for sig in all_results:
            spec = Spectra.compute(sig.acc, sig.dt, code_periods, 0.05)
            fit = WaveGenerator.fit_error(spec.sa, code_sa)
            trial_spectra.append(spec.sa)
            trial_errors.append(fit)

        best_fit = trial_errors[best_idx]
        n_trials = len(all_results)

        info_lines = [
            f"最优: Trial {best_idx+1}/{n_trials}",
            f"PGA = {best.pga:.4f} g",
            f"持时 = {best.duration:.2f} s",
            f"最大偏差 = {best_fit['max_error']:.1%}",
            f"均方根偏差 = {best_fit['mean_error']:.1%}",
        ]

        self._plot_spectrum_comparison(
            code_periods, code_sa, trial_spectra, best_idx, palette, colors)
        self._plot_time_history(best, colors)

        progress_text = f"完成: {n_trials} trials, 最优 Trial {best_idx+1}"
        return info_lines, progress_text

    def _plot_spectrum_comparison(self, periods, code_sa, trial_spectra,
                                   best_idx, palette, colors):
        self._spec_plot.clear()
        self._spec_plot.plot_code_spectrum(periods, code_sa, label="目标谱")
        for i, sa in enumerate(trial_spectra):
            if i == best_idx:
                continue
            self._spec_plot.ax.plot(
                periods, sa,
                color=palette[i % len(palette)],
                linewidth=1.0, alpha=0.4,
                label=f"Trial {i+1}")
        self._spec_plot.ax.plot(
            periods, trial_spectra[best_idx],
            color=colors['primary'], linewidth=2.2,
            label=f"Trial {best_idx+1} (最优)")
        self._spec_plot.ax.legend(fontsize=8, framealpha=0.8)
        self._spec_plot.ax.set_title("反应谱拟合对比", fontsize=11)
        self._spec_plot.refresh()

    def _plot_time_history(self, best, colors):
        self._time_plot.clear()
        ax = self._time_plot.ax
        ax.plot(best.time, best.acc,
                color=colors['primary'], linewidth=0.6)
        ax.set_xlabel("时间 (s)")
        ax.set_ylabel("加速度 (g)")
        ax.set_title(
            f"人工波 (PGA={best.pga:.3f}g)", fontsize=11)
        self._time_plot.refresh()

    # ────────────────────────── 特殊地震动 ──────────────────────────

    def present_special(self, signal, label, code_periods=None, code_sa=None):
        """呈现特殊地震动结果（FF / NF / NFP）

        Args:
            signal: EQSignal 对象
            label: 地震动类型标签
            code_periods, code_sa: 可选的规范谱数据

        Returns:
            (info_lines, progress_text)
        """
        self._generated = signal
        colors = get_mpl_colors(self._dark)

        info_lines = [
            f"类型: {label}",
            f"名称: {signal.name}",
            f"PGA = {signal.pga:.4f} g",
            f"持时 = {signal.duration:.2f} s",
        ]

        # NFP 脉冲参数
        if hasattr(signal, 'pulse_params') and signal.pulse_params:
            p = signal.pulse_params
            info_lines += [
                "",
                "── 脉冲参数 ──",
                f"Tp = {p.Tp:.2f} s",
                f"A  = {p.A:.1f} cm/s",
                f"φ  = {p.phi:.3f} rad",
                f"t₀ = {p.t0:.2f} s",
            ]

        if hasattr(signal, 'pulse_metrics') and signal.pulse_metrics:
            m = signal.pulse_metrics
            info_lines += [
                "",
                "── Baker (2007) 识别 ──",
                f"含脉冲: {m.get('has_pulse', False)}",
                f"置信度: {m.get('confidence', 0.0):.3f}",
                f"估计 Tp: {m.get('pulse_period', 0.0):.2f} s",
                f"PGV: {m.get('pulse_amplitude', 0.0):.1f} cm/s",
                f"能量比: {m.get('energy_ratio', 0.0):.3f}",
            ]

        # 特殊地震动应与其 GMPE 目标谱对比，而不是与一般人工波规范谱对比。
        periods_plot = getattr(signal, 'spectrum_periods', None)
        target_sa = getattr(signal, 'total_spectrum', None)
        if periods_plot is not None and target_sa is not None:
            spec = Spectra.compute(signal.acc, signal.dt, periods_plot, 0.05)
            fit = WaveGenerator.fit_error(spec.sa, target_sa)
            info_lines += [
                "",
                f"与GMPE目标谱最大偏差 = {fit['max_error']:.1%}",
                f"与GMPE目标谱均方根偏差 = {fit['mean_error']:.1%}",
            ]

        self._plot_special_spectrum(signal, label, colors, code_periods, code_sa)
        self._plot_special_time_history(signal, label, colors)

        progress_text = f"完成: {signal.name}"
        return info_lines, progress_text

    def _plot_special_spectrum(self, signal, label, colors,
                                code_periods=None, code_sa=None):
        self._spec_plot.clear()

        periods_plot = getattr(signal, 'spectrum_periods', None)
        if periods_plot is None:
            periods_plot = code_periods

        if periods_plot is not None and hasattr(signal, 'total_spectrum'):
            self._spec_plot.ax.plot(
                periods_plot, signal.total_spectrum,
                color=colors['secondary'], linewidth=1.5,
                linestyle='--', label="GMPE 目标谱")

        if periods_plot is not None:
            spec = Spectra.compute(signal.acc, signal.dt, periods_plot, 0.05)
            self._spec_plot.ax.plot(
                periods_plot, spec.sa,
                color=colors['primary'], linewidth=2.0,
                label=f"{label} 生成谱")
        self._spec_plot.ax.legend(fontsize=8, framealpha=0.8)
        self._spec_plot.ax.set_title(
            f"{label} 反应谱对比", fontsize=11)
        self._spec_plot.refresh()

    def _plot_special_time_history(self, signal, label, colors):
        self._time_plot.clear()
        ax = self._time_plot.ax
        t = signal.time

        ax.plot(t, signal.acc, color=colors['primary'],
                linewidth=0.6, label="加速度")

        is_nfp = (label == "近场脉冲 NFP")
        if is_nfp and hasattr(signal, 'pulse_vel'):
            ax2 = ax.twinx()
            ax2.plot(t, signal.pulse_vel * 980.0,
                     color=colors['accent'], linewidth=1.0,
                     linestyle='--', label="脉冲速度 (cm/s)")
            ax2.set_ylabel("脉冲速度 (cm/s)", color=colors['accent'])
            ax2.tick_params(axis='y', labelcolor=colors['accent'])
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2,
                      fontsize=8, loc='upper right')
        else:
            ax.legend(fontsize=8)

        ax.set_xlabel("时间 (s)")
        ax.set_ylabel("加速度 (g)")
        ax.set_title(
            f"{signal.name} (PGA={signal.pga:.3f}g)",
            fontsize=11)
        self._time_plot.refresh()
