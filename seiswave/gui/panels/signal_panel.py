"""
信号处理面板

基线校正方法选择、滤波参数设置、处理前后对比。
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QComboBox, QFormLayout, QPushButton,
    QSplitter, QMessageBox,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core import EQSignal, Filter
from seiswave.gui.widgets.plot_widget import PlotWidget
from seiswave.gui.styles import get_mpl_colors


class SignalPanel(QWidget):
    """信号处理面板"""

    signal_processed = Signal(object)  # 处理完成信号 (EQSignal)

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._signal = None
        self._processed = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 左侧参数面板
        param_widget = QWidget()
        param_widget.setFixedWidth(320)
        param_layout = QVBoxLayout(param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)

        # 当前信号信息
        info_group = QGroupBox("当前信号")
        info_layout = QVBoxLayout(info_group)
        self._info_label = QLabel("未选择信号")
        self._info_label.setWordWrap(True)
        info_layout.addWidget(self._info_label)
        param_layout.addWidget(info_group)

        # 基线校正
        baseline_group = QGroupBox("基线校正")
        baseline_form = QFormLayout(baseline_group)

        self._baseline_combo = QComboBox()
        self._baseline_combo.addItems(["多项式去趋势", "双线性去趋势"])
        baseline_form.addRow("方法:", self._baseline_combo)

        self._poly_order_spin = QSpinBox()
        self._poly_order_spin.setRange(1, 6)
        self._poly_order_spin.setValue(2)
        baseline_form.addRow("多项式阶数:", self._poly_order_spin)

        self._baseline_btn = QPushButton("应用基线校正")
        self._baseline_btn.clicked.connect(self._apply_baseline)
        baseline_form.addRow(self._baseline_btn)

        param_layout.addWidget(baseline_group)

        # 滤波
        filter_group = QGroupBox("Butterworth 滤波")
        filter_form = QFormLayout(filter_group)

        self._filter_type_combo = QComboBox()
        self._filter_type_combo.addItems(["带通", "低通", "高通"])
        filter_form.addRow("滤波类型:", self._filter_type_combo)

        self._filter_order_spin = QSpinBox()
        self._filter_order_spin.setRange(1, 10)
        self._filter_order_spin.setValue(4)
        filter_form.addRow("滤波器阶数:", self._filter_order_spin)

        self._f1_spin = QDoubleSpinBox()
        self._f1_spin.setRange(0.01, 50.0)
        self._f1_spin.setSingleStep(0.1)
        self._f1_spin.setValue(0.1)
        self._f1_spin.setDecimals(2)
        filter_form.addRow("低频截止 f₁ (Hz):", self._f1_spin)

        self._f2_spin = QDoubleSpinBox()
        self._f2_spin.setRange(0.1, 100.0)
        self._f2_spin.setSingleStep(1.0)
        self._f2_spin.setValue(25.0)
        self._f2_spin.setDecimals(2)
        filter_form.addRow("高频截止 f₂ (Hz):", self._f2_spin)

        self._filter_btn = QPushButton("应用滤波")
        self._filter_btn.clicked.connect(self._apply_filter)
        filter_form.addRow(self._filter_btn)

        param_layout.addWidget(filter_group)

        # 重置
        self._reset_btn = QPushButton("重置")
        self._reset_btn.setProperty("secondary", True)
        self._reset_btn.clicked.connect(self._reset)
        param_layout.addWidget(self._reset_btn)

        param_layout.addStretch()
        layout.addWidget(param_widget)

        # 右侧绘图区（上下对比）
        right_splitter = QSplitter(Qt.Vertical)

        self._orig_plot = PlotWidget(dark=self._dark)
        right_splitter.addWidget(self._orig_plot)

        self._proc_plot = PlotWidget(dark=self._dark)
        right_splitter.addWidget(self._proc_plot)

        right_splitter.setSizes([350, 350])
        layout.addWidget(right_splitter, 1)

    def set_signal(self, signal):
        """设置待处理信号"""
        self._signal = signal
        self._processed = EQSignal(signal.acc.copy(), signal.dt, name=signal.name)
        self._info_label.setText(
            f"名称: {signal.name}\n"
            f"PGA = {signal.pga:.4f} g\n"
            f"持时 = {signal.duration:.2f} s\n"
            f"Δt = {signal.dt:.4f} s"
        )
        self._plot_original()
        self._plot_processed()

    def _plot_original(self):
        if self._signal is None:
            return
        colors = get_mpl_colors(self._dark)
        self._orig_plot.clear()
        ax = self._orig_plot.ax
        ax.plot(self._signal.time, self._signal.acc,
                color=colors['primary'], linewidth=0.6)
        ax.set_xlabel("时间 (s)")
        ax.set_ylabel("加速度 (g)")
        ax.set_title("原始信号", fontsize=11)
        self._orig_plot.refresh()

    def _plot_processed(self):
        if self._processed is None:
            return
        colors = get_mpl_colors(self._dark)
        self._proc_plot.clear()
        ax = self._proc_plot.ax
        ax.plot(self._processed.time, self._processed.acc,
                color=colors['accent'], linewidth=0.6)
        ax.set_xlabel("时间 (s)")
        ax.set_ylabel("加速度 (g)")
        ax.set_title(f"处理后信号 (PGA = {self._processed.pga:.4f} g)", fontsize=11)
        self._proc_plot.refresh()

    def _apply_baseline(self):
        if self._processed is None:
            QMessageBox.warning(self, "警告", "请先选择信号")
            return
        method_idx = self._baseline_combo.currentIndex()
        if method_idx == 0:
            order = self._poly_order_spin.value()
            self._processed.acc = Filter.detrend(self._processed.acc, order=order)
        else:
            self._processed.acc = Filter.bilinear_detrend(
                self._processed.acc, self._processed.dt)
        self._plot_processed()
        self.signal_processed.emit(self._processed)

    def _apply_filter(self):
        if self._processed is None:
            QMessageBox.warning(self, "警告", "请先选择信号")
            return
        ftype_map = {0: "bandpass", 1: "lowpass", 2: "highpass"}
        ftype = ftype_map[self._filter_type_combo.currentIndex()]
        order = self._filter_order_spin.value()
        f1 = self._f1_spin.value()
        f2 = self._f2_spin.value()

        try:
            self._processed.acc = Filter.butterworth(
                self._processed.acc, self._processed.dt,
                ftype=ftype, order=order, f1=f1, f2=f2,
            )
            self._plot_processed()
            self.signal_processed.emit(self._processed)
        except Exception as e:
            QMessageBox.critical(self, "滤波错误", str(e))

    def _reset(self):
        if self._signal is not None:
            self.set_signal(self._signal)

    def get_processed(self):
        return self._processed

    def set_dark(self, dark: bool):
        self._dark = dark
        self._orig_plot.set_dark(dark)
        self._proc_plot.set_dark(dark)
