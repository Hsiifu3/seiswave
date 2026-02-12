"""
反应谱专用绘图控件

支持对数坐标、多谱叠加、规范谱对比。
"""

import numpy as np
from seiswave.gui.widgets.plot_widget import PlotWidget
from seiswave.gui.styles import get_mpl_colors


class SpectrumPlot(PlotWidget):
    """反应谱绘图控件"""

    def __init__(self, parent=None, dark=False):
        super().__init__(parent, dark=dark)
        self._setup_axes()

    def _setup_axes(self):
        self.ax.set_xlabel("周期 T (s)")
        self.ax.set_ylabel("加速度反应谱 Sa (g)")
        self.ax.set_xscale('log')
        self.ax.set_xlim(0.01, 10)

    def clear(self):
        super().clear()
        self._setup_axes()

    def plot_spectrum(self, periods, sa, label=None, color=None, linewidth=1.5,
                      linestyle='-', alpha=1.0):
        """绘制单条反应谱"""
        colors = get_mpl_colors(self.canvas._dark)
        if color is None:
            color = colors['primary']
        self.ax.plot(periods, sa, label=label, color=color,
                     linewidth=linewidth, linestyle=linestyle, alpha=alpha)
        if label:
            self.ax.legend(fontsize=9, framealpha=0.8)
        self.refresh()

    def plot_code_spectrum(self, periods, sa, label="规范谱", linewidth=2.5):
        """绘制规范谱（加粗红色虚线）"""
        colors = get_mpl_colors(self.canvas._dark)
        self.ax.plot(periods, sa, label=label, color=colors['secondary'],
                     linewidth=linewidth, linestyle='--')
        self.ax.legend(fontsize=9, framealpha=0.8)
        self.refresh()

    def plot_comparison(self, periods, code_sa, wave_spectra, wave_labels=None):
        """绘制规范谱与多条波反应谱对比"""
        self.clear()
        colors = get_mpl_colors(self.canvas._dark)
        palette = colors['palette']

        # 规范谱
        self.ax.plot(periods, code_sa, label="规范谱", color=colors['secondary'],
                     linewidth=2.5, linestyle='--')

        # 各波反应谱
        for i, sa in enumerate(wave_spectra):
            lbl = wave_labels[i] if wave_labels else f"Wave {i+1}"
            self.ax.plot(periods, sa, label=lbl,
                         color=palette[i % len(palette)],
                         linewidth=1.2, alpha=0.8)

        # 均值谱
        if len(wave_spectra) > 1:
            mean_sa = np.mean(wave_spectra, axis=0)
            self.ax.plot(periods, mean_sa, label="均值谱",
                         color=colors['fg'], linewidth=2.0, linestyle='-.')

        self.ax.legend(fontsize=8, framealpha=0.8, loc='upper right')
        self.refresh()

    def plot_envelope(self, periods, code_sa, lower_factor=0.65, upper_factor=1.35):
        """绘制规范谱包络线"""
        colors = get_mpl_colors(self.canvas._dark)
        self.ax.fill_between(periods, code_sa * lower_factor, code_sa * upper_factor,
                             alpha=0.1, color=colors['secondary'], label="容许范围")
        self.ax.legend(fontsize=9, framealpha=0.8)
        self.refresh()
