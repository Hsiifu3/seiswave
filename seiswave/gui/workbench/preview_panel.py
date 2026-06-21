"""中央预览面板。"""

from __future__ import annotations

from collections.abc import Sequence
import warnings

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from seiswave.core.signal_pool import SignalPool, SignalRecord
from seiswave.core.spectrum import Spectra
from seiswave.core.target_spectrum import TargetSpectrumService
from seiswave.gui.fonts import setup_matplotlib_fonts
from seiswave.gui.styles import get_mpl_colors
from seiswave.gui.widgets.plot_widget import PlotWidget

from .scorecard import Scorecard


class PreviewPanel(QWidget):
    """选中信号的 a/v/d 与谱预览。"""

    metrics_changed = Signal(object)

    def __init__(
        self,
        pool: SignalPool,
        target_service: TargetSpectrumService,
        parent: QWidget | None = None,
        dark: bool = False,
    ) -> None:
        super().__init__(parent)
        setup_matplotlib_fonts()
        self._pool = pool
        self._target_service = target_service
        self._dark = dark
        self._spectrum_axes = []
        self._selection_label: QLabel | None = None
        self._target_label: QLabel | None = None
        self._triple_log_check: QCheckBox | None = None
        self._damping_combo: QComboBox | None = None
        self._acc_plot: PlotWidget | None = None
        self._vel_plot: PlotWidget | None = None
        self._disp_plot: PlotWidget | None = None
        self._spectrum_plot: PlotWidget | None = None
        self._scorecard: Scorecard | None = None
        self._setup_ui()
        self._connect_services()
        self.refresh_from_services()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        header = QHBoxLayout()
        self._selection_label = QLabel("已选 0 条信号")
        self._target_label = QLabel("目标谱：未设置目标谱")
        self._target_label.setWordWrap(True)
        self._triple_log_check = QCheckBox("三联对数图")
        self._damping_combo = QComboBox()
        self._damping_combo.addItem("单阻尼 5%", "single")
        self._damping_combo.addItem("多阻尼 2% / 5% / 10%", "multi")
        header.addWidget(self._selection_label)
        header.addSpacing(12)
        header.addWidget(self._target_label, 1)
        header.addWidget(self._triple_log_check)
        header.addWidget(self._damping_combo)
        root.addLayout(header)

        motion_splitter = QSplitter(Qt.Vertical)
        motion_splitter.setChildrenCollapsible(False)
        self._acc_plot = PlotWidget(show_toolbar=False, dark=self._dark)
        self._vel_plot = PlotWidget(show_toolbar=False, dark=self._dark)
        self._disp_plot = PlotWidget(show_toolbar=False, dark=self._dark)
        motion_splitter.addWidget(self._acc_plot)
        motion_splitter.addWidget(self._vel_plot)
        motion_splitter.addWidget(self._disp_plot)
        motion_splitter.setSizes([220, 220, 220])
        root.addWidget(motion_splitter, 5)

        lower_splitter = QSplitter(Qt.Vertical)
        lower_splitter.setChildrenCollapsible(False)
        self._spectrum_plot = PlotWidget(show_toolbar=False, dark=self._dark)
        self._scorecard = Scorecard()
        self._scorecard.metrics_changed.connect(self.metrics_changed.emit)
        lower_splitter.addWidget(self._spectrum_plot)
        lower_splitter.addWidget(self._scorecard)
        lower_splitter.setSizes([320, 160])
        root.addWidget(lower_splitter, 4)

        self._triple_log_check.toggled.connect(self._refresh_spectrum_only)
        self._damping_combo.currentIndexChanged.connect(self._refresh_spectrum_only)

    def _connect_services(self) -> None:
        self._pool.selection_changed.connect(self.refresh_from_services)
        self._target_service.target_changed.connect(self.refresh_from_services)

    def state(self) -> dict[str, object]:
        """返回当前预览选项。"""
        assert self._triple_log_check is not None
        assert self._damping_combo is not None
        return {
            "triple_log": self._triple_log_check.isChecked(),
            "damping_mode": self._damping_combo.currentData(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        """恢复预览选项。"""
        if state is None:
            state = {}
        assert self._triple_log_check is not None
        assert self._damping_combo is not None
        self._triple_log_check.setChecked(bool(state.get("triple_log", False)))
        mode = str(state.get("damping_mode", "single"))
        index = self._damping_combo.findData(mode)
        if index >= 0:
            self._damping_combo.setCurrentIndex(index)
        self._refresh_spectrum_only()

    def spectrum_axes(self) -> list[object]:
        """返回当前谱图的 Matplotlib 轴列表。"""
        return list(self._spectrum_axes)

    def refresh_from_services(self) -> None:
        """响应选中信号/目标谱变化并刷新全部预览。"""
        records = self._pool.selection()
        self._update_header(records)
        self._plot_motion_records(records)
        self._refresh_spectrum_only()
        assert self._scorecard is not None
        self._scorecard.update_records(records, self._target_service)

    def _update_header(self, records: Sequence[SignalRecord]) -> None:
        assert self._selection_label is not None
        assert self._target_label is not None
        self._selection_label.setText(f"已选 {len(records)} 条信号")
        self._target_label.setText(f"目标谱：{self._target_service.describe()}")

    def _plot_motion_records(self, records: Sequence[SignalRecord]) -> None:
        plots = [
            (self._acc_plot, "加速度时程 a(t)", "加速度", lambda record: record.acc),
            (self._vel_plot, "速度时程 v(t)", "速度", lambda record: record.vel()),
            (self._disp_plot, "位移时程 d(t)", "位移", lambda record: record.disp()),
        ]

        if not records:
            for plot, title, _ylabel, _getter in plots:
                assert plot is not None
                plot.show_placeholder(f"{title}：请选择信号")
            return

        colors = get_mpl_colors(self._dark)
        palette = colors["palette"]

        for plot, title, ylabel, getter in plots:
            assert plot is not None
            plot.clear()
            axis = plot.ax
            axis.set_title(title, fontsize=10)
            axis.set_xlabel("时间 (s)", fontsize=9)
            axis.set_ylabel(ylabel, fontsize=9)
            for index, record in enumerate(records):
                time = np.arange(record.n, dtype=np.float64) * record.dt
                axis.plot(
                    time,
                    getter(record),
                    color=palette[index % len(palette)],
                    linewidth=1.0,
                    alpha=0.85,
                    label=record.name or f"信号 {index + 1}",
                )
            if len(records) <= 5:
                axis.legend(fontsize=8, framealpha=0.85, loc="upper right")
            plot.refresh()

    def _refresh_spectrum_only(self) -> None:
        records = self._pool.selection()
        target_sa = self._target_service.sa()
        if not records and target_sa.size == 0:
            self._show_spectrum_placeholder("反应谱：请选择信号")
            return

        periods = self._resolve_periods()
        base_zeta = float(self._target_service.zeta())
        zetas = self._selected_zetas(base_zeta)
        spectra_by_zeta = self._mean_spectra(records, periods, zetas)
        axes = self._reset_spectrum_axes(periods)
        colors = get_mpl_colors(self._dark)
        palette = colors["palette"]

        if len(axes) == 1:
            axis = axes[0]
            axis.set_title("反应谱对比", fontsize=10)
            if target_sa.size:
                axis.plot(
                    periods,
                    target_sa,
                    color=colors["secondary"],
                    linewidth=2.0,
                    linestyle="--",
                    label="目标谱",
                )
            for index, zeta in enumerate(zetas):
                mean_spec = spectra_by_zeta.get(zeta)
                if mean_spec is None:
                    continue
                axis.plot(
                    periods,
                    mean_spec["sa"],
                    color=palette[index % len(palette)],
                    linewidth=1.6,
                    label=f"结果谱 ζ={self._format_zeta(zeta)}",
                )
            axis.legend(fontsize=8, framealpha=0.85, loc="best")
            self._spectrum_plot.refresh()
            return

        labels = [
            ("Sa", "加速度反应谱 Sa"),
            ("Sv", "速度反应谱 Sv"),
            ("Sd", "位移反应谱 Sd"),
        ]
        for axis, (_key, title) in zip(axes, labels):
            axis.set_title(title, fontsize=10)

        if target_sa.size:
            axes[0].plot(
                periods,
                target_sa,
                color=colors["secondary"],
                linewidth=2.0,
                linestyle="--",
                label="目标谱",
            )

        for index, zeta in enumerate(zetas):
            mean_spec = spectra_by_zeta.get(zeta)
            if mean_spec is None:
                continue
            color = palette[index % len(palette)]
            axes[0].plot(
                periods,
                mean_spec["sa"],
                color=color,
                linewidth=1.5,
                label=f"结果谱 ζ={self._format_zeta(zeta)}",
            )
            axes[1].plot(periods, mean_spec["sv"], color=color, linewidth=1.5)
            axes[2].plot(periods, mean_spec["sd"], color=color, linewidth=1.5)

        axes[0].legend(fontsize=8, framealpha=0.85, loc="best")
        self._spectrum_plot.refresh()

    def _resolve_periods(self) -> np.ndarray:
        target_periods = self._target_service.periods()
        if target_periods.size:
            return target_periods
        return Spectra.default_periods(n=120)

    def _selected_zetas(self, base_zeta: float) -> list[float]:
        assert self._damping_combo is not None
        mode = self._damping_combo.currentData()
        if mode != "multi":
            return [base_zeta]
        zetas = []
        for zeta in (0.02, base_zeta, 0.10):
            if zeta not in zetas:
                zetas.append(float(zeta))
        return zetas

    def _mean_spectra(
        self,
        records: Sequence[SignalRecord],
        periods: np.ndarray,
        zetas: Sequence[float],
    ) -> dict[float, dict[str, np.ndarray]]:
        spectra_by_zeta: dict[float, dict[str, np.ndarray]] = {}
        for zeta in zetas:
            if not records:
                continue
            spectra = [record.spectrum(periods, zeta=zeta) for record in records]
            spectra_by_zeta[float(zeta)] = {
                "sa": np.mean([item.sa for item in spectra], axis=0),
                "sv": np.mean([item.sv for item in spectra], axis=0),
                "sd": np.mean([item.sd for item in spectra], axis=0),
            }
        return spectra_by_zeta

    def _reset_spectrum_axes(self, periods: np.ndarray) -> list[object]:
        assert self._spectrum_plot is not None
        assert self._triple_log_check is not None
        colors = get_mpl_colors(self._dark)
        fig = self._spectrum_plot.fig
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Attempt to set non-positive xlim on a log-scaled axis will be ignored.",
                category=UserWarning,
            )
            fig.clear()

        if self._triple_log_check.isChecked():
            axes = list(np.atleast_1d(fig.subplots(3, 1, sharex=True)))
            ylabels = ["Sa", "Sv", "Sd"]
            for axis, ylabel in zip(axes, ylabels):
                self._spectrum_plot.canvas._apply_style(axis, colors)
                axis.set_xlim(float(np.min(periods)), float(np.max(periods)))
                axis.set_xscale("log")
                axis.set_yscale("log")
                axis.set_ylabel(ylabel, fontsize=9)
            axes[-1].set_xlabel("周期 T (s)", fontsize=9)
        else:
            axis = fig.add_subplot(111)
            self._spectrum_plot.canvas._apply_style(axis, colors)
            axis.set_xlim(float(np.min(periods)), float(np.max(periods)))
            axis.set_xscale("log")
            axis.set_xlabel("周期 T (s)", fontsize=9)
            axis.set_ylabel("Sa", fontsize=9)
            axes = [axis]

        self._spectrum_plot.canvas.ax = axes[0]
        self._spectrum_axes = axes
        return axes

    def _show_spectrum_placeholder(self, text: str) -> None:
        assert self._spectrum_plot is not None
        fig = self._spectrum_plot.fig
        fig.clear()
        axis = fig.add_subplot(111)
        self._spectrum_plot.canvas.ax = axis
        self._spectrum_axes = [axis]
        self._spectrum_plot.show_placeholder(text)

    def _format_zeta(self, zeta: float) -> str:
        return f"{zeta * 100:.0f}%"
