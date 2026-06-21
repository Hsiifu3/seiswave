"""三联对数反应谱弹窗：Sa / Sv / Sd 三谱独立大图，双对数坐标。"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QDialog, QVBoxLayout

from seiswave.gui.styles import get_mpl_colors
from seiswave.gui.widgets.plot_widget import PlotWidget


class TripleSpectrumWindow(QDialog):
    """独立窗口展示 Sa/Sv/Sd 三联对数反应谱，随选中信号/目标谱实时刷新。"""

    def __init__(self, preview_panel, pool, target_service, dark=False, parent=None) -> None:
        super().__init__(parent)
        self._preview = preview_panel
        self._pool = pool
        self._target = target_service
        self._dark = dark
        self.setWindowTitle("三联对数反应谱 (Sa / Sv / Sd)")
        self.setModal(False)
        self.resize(760, 880)

        layout = QVBoxLayout(self)
        self._sa_plot = PlotWidget(show_toolbar=True, dark=dark)
        self._sv_plot = PlotWidget(show_toolbar=True, dark=dark)
        self._sd_plot = PlotWidget(show_toolbar=True, dark=dark)
        for plot in (self._sa_plot, self._sv_plot, self._sd_plot):
            plot.setMinimumHeight(230)
            layout.addWidget(plot)

        # 随共享数据实时刷新
        self._pool.selection_changed.connect(self.refresh)
        self._target.target_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        data = self._preview.spectra_data()
        colors = get_mpl_colors(self._dark)
        palette = colors["palette"]

        specs = [
            (self._sa_plot, "sa", "加速度反应谱 Sa", "Sa"),
            (self._sv_plot, "sv", "速度反应谱 Sv", "Sv"),
            (self._sd_plot, "sd", "位移反应谱 Sd", "Sd"),
        ]

        if data is None:
            for plot, _key, title, _yl in specs:
                plot.show_placeholder(f"{title}：请选择信号或设置目标谱")
            return

        periods, target_sa, zetas, spectra_by_zeta = data
        positive = periods > 0

        for plot, key, title, ylabel in specs:
            plot.clear()
            axis = plot.ax
            axis.set_title(title, fontsize=11)
            axis.set_xlabel("周期 T (s)", fontsize=10)
            axis.set_ylabel(ylabel, fontsize=10)
            axis.set_xscale("log")
            axis.set_yscale("log")

            if key == "sa" and target_sa.size:
                mask = positive & (np.asarray(target_sa) > 0)
                axis.plot(
                    periods[mask],
                    np.asarray(target_sa)[mask],
                    color=colors["secondary"],
                    linewidth=2.2,
                    linestyle="--",
                    label="目标谱",
                )

            for index, zeta in enumerate(zetas):
                mean_spec = spectra_by_zeta.get(zeta)
                if mean_spec is None:
                    continue
                values = np.asarray(mean_spec[key])
                mask = positive & (values > 0)
                axis.plot(
                    periods[mask],
                    values[mask],
                    color=palette[index % len(palette)],
                    linewidth=1.6,
                    label=f"结果谱 ζ={self._preview.zeta_label(zeta)}",
                )
            axis.legend(fontsize=9, framealpha=0.85, loc="best")
            plot.refresh()


__all__ = ["TripleSpectrumWindow"]
