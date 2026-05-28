"""信号处理面板

增强功能：
- Arias 强度计算和显示 (Ia = π/(2g) ∫a²dt)
- 有效持时 D5-95 计算和显示
- 处理前后对比可视化
- 关键参数对比（PGA、Arias 强度、有效持时）
- 人工波与天然波统一后处理：基线校正、滤波、截断
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QComboBox, QFormLayout, QPushButton,
    QSplitter, QMessageBox, QSizePolicy, QGridLayout,
)
from PySide6.QtCore import Signal, Qt

import numpy as np

from seiswave.core import EQSignal, Filter
from seiswave.gui.widgets.plot_widget import PlotWidget
from seiswave.gui.styles import get_mpl_colors


def _arias_total(sig):
    """计算信号的总 Arias 强度 (m/s)"""
    ia = sig.arias_intensity()
    return float(ia[-1]) if len(ia) > 0 else 0.0


class SignalPanel(QWidget):
    signal_processed = Signal(object)

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._signal = None
        self._processed = None
        self._signal_pool = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)

        # ── 左侧参数面板 ──
        param_widget = QWidget()
        param_widget.setMinimumWidth(300)
        param_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        param_layout = QVBoxLayout(param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)

        # 记录选择
        info_group = QGroupBox("当前处理记录")
        info_layout = QVBoxLayout(info_group)
        self._picker = QComboBox()
        self._picker.addItem("请选择人工波/天然波记录...")
        self._pick_btn = QPushButton("载入当前记录")
        self._pick_btn.clicked.connect(self._apply_selection)
        info_layout.addWidget(self._picker)
        info_layout.addWidget(self._pick_btn)
        self._info_label = QLabel("未选择人工波/天然波记录，统一后处理操作已禁用")
        self._info_label.setWordWrap(True)
        info_layout.addWidget(self._info_label)
        param_layout.addWidget(info_group)

        # 参数对比表
        compare_group = QGroupBox("处理前后参数对比")
        compare_grid = QGridLayout(compare_group)
        compare_grid.addWidget(QLabel("参数"), 0, 0)
        compare_grid.addWidget(QLabel("处理前"), 0, 1)
        compare_grid.addWidget(QLabel("处理后"), 0, 2)
        compare_grid.addWidget(QLabel("PGA (g)"), 1, 0)
        compare_grid.addWidget(QLabel("Arias (m/s)"), 2, 0)
        compare_grid.addWidget(QLabel("D5-95 (s)"), 3, 0)
        self._lbl_pga_before = QLabel("--")
        self._lbl_pga_after = QLabel("--")
        self._lbl_arias_before = QLabel("--")
        self._lbl_arias_after = QLabel("--")
        self._lbl_d595_before = QLabel("--")
        self._lbl_d595_after = QLabel("--")
        compare_grid.addWidget(self._lbl_pga_before, 1, 1)
        compare_grid.addWidget(self._lbl_pga_after, 1, 2)
        compare_grid.addWidget(self._lbl_arias_before, 2, 1)
        compare_grid.addWidget(self._lbl_arias_after, 2, 2)
        compare_grid.addWidget(self._lbl_d595_before, 3, 1)
        compare_grid.addWidget(self._lbl_d595_after, 3, 2)
        param_layout.addWidget(compare_group)

        # 基线校正
        baseline_group = QGroupBox("统一后处理：基线校正")
        baseline_form = QFormLayout(baseline_group)
        self._baseline_combo = QComboBox()
        self._baseline_combo.addItems(["多项式去趋势", "双线性去趋势"])
        self._poly_order_spin = QSpinBox()
        self._poly_order_spin.setRange(1, 6)
        self._poly_order_spin.setValue(2)
        self._baseline_btn = QPushButton("应用统一后处理：基线校正")
        self._baseline_btn.clicked.connect(self._apply_baseline)
        baseline_form.addRow("方法:", self._baseline_combo)
        baseline_form.addRow("多项式阶数:", self._poly_order_spin)
        baseline_form.addRow(self._baseline_btn)
        param_layout.addWidget(baseline_group)

        # Butterworth 滤波
        filter_group = QGroupBox("统一后处理：Butterworth 滤波")
        filter_form = QFormLayout(filter_group)
        self._filter_type_combo = QComboBox()
        self._filter_type_combo.addItems(["带通", "低通", "高通"])
        self._filter_order_spin = QSpinBox()
        self._filter_order_spin.setRange(1, 10)
        self._filter_order_spin.setValue(4)
        self._f1_spin = QDoubleSpinBox()
        self._f1_spin.setRange(0.01, 50.0)
        self._f1_spin.setValue(0.1)
        self._f2_spin = QDoubleSpinBox()
        self._f2_spin.setRange(0.1, 100.0)
        self._f2_spin.setValue(25.0)
        self._filter_btn = QPushButton("应用统一后处理：滤波")
        self._filter_btn.clicked.connect(self._apply_filter)
        filter_form.addRow("滤波类型:", self._filter_type_combo)
        filter_form.addRow("滤波器阶数:", self._filter_order_spin)
        filter_form.addRow("低频截止 f\u2081 (Hz):", self._f1_spin)
        filter_form.addRow("高频截止 f\u2082 (Hz):", self._f2_spin)
        filter_form.addRow(self._filter_btn)
        param_layout.addWidget(filter_group)

        # 截断
        trim_group = QGroupBox("统一后处理：信号截断")
        trim_form = QFormLayout(trim_group)
        self._trim_start = QDoubleSpinBox()
        self._trim_start.setRange(0.0, 9999.0)
        self._trim_start.setDecimals(2)
        self._trim_start.setSuffix(" s")
        self._trim_end = QDoubleSpinBox()
        self._trim_end.setRange(0.0, 9999.0)
        self._trim_end.setDecimals(2)
        self._trim_end.setSuffix(" s")
        self._trim_btn = QPushButton("应用统一后处理：裁剪")
        self._trim_btn.clicked.connect(self._apply_trim)
        self._auto_trim_btn = QPushButton("自动裁剪 (D5-95)")
        self._auto_trim_btn.clicked.connect(self._apply_auto_trim)
        trim_form.addRow("起始时间:", self._trim_start)
        trim_form.addRow("结束时间:", self._trim_end)
        trim_form.addRow(self._trim_btn)
        trim_form.addRow(self._auto_trim_btn)
        param_layout.addWidget(trim_group)

        self._reset_btn = QPushButton("重置")
        self._reset_btn.clicked.connect(self._reset)
        param_layout.addWidget(self._reset_btn)
        param_layout.addStretch()
        layout.addWidget(param_widget)

        # ── 右侧绘图区 ──
        right_splitter = QSplitter(Qt.Vertical)
        self._orig_plot = PlotWidget(dark=self._dark, show_toolbar=False)
        self._proc_plot = PlotWidget(dark=self._dark, show_toolbar=False)
        right_splitter.addWidget(self._orig_plot)
        right_splitter.addWidget(self._proc_plot)
        layout.addWidget(right_splitter, 1)

        self._update_action_state()

    # ──────────────────── 信号池与选择 ────────────────────

    def _refresh_picker(self, placeholder="请选择人工波/天然波记录..."):
        self._picker.clear()
        self._picker.addItem(placeholder)
        for s in self._signal_pool:
            self._picker.addItem(s.name or "未命名记录")

    def set_signal_pool(self, signals):
        self._signal_pool = list(signals or [])
        self._refresh_picker()
        if not self._signal_pool:
            self._info_label.setText("暂无人工波/天然波记录，统一后处理操作已禁用")
            self._signal = None
            self._processed = None
            self._update_action_state()

    def add_signal(self, signal, select=False):
        if signal is None:
            return
        self._signal_pool.append(signal)
        self._refresh_picker()
        if select:
            self._picker.setCurrentIndex(len(self._signal_pool))
            self.set_signal(signal)

    def _apply_selection(self):
        idx = self._picker.currentIndex() - 1
        if idx < 0 or idx >= len(self._signal_pool):
            QMessageBox.information(self, "提示", "请先从下拉框选择记录")
            return
        self.set_signal(self._signal_pool[idx])

    def set_signal(self, signal):
        self._signal = signal
        self._processed = EQSignal(signal.acc.copy(), signal.dt, name=signal.name)
        self._info_label.setText(
            f"当前记录: {signal.name}\n"
            f"PGA={signal.pga:.4f}g, 持时={signal.duration:.2f}s, "
            f"\u0394t={signal.dt:.4f}s"
        )
        self._trim_start.setValue(0.0)
        self._trim_end.setValue(signal.duration)
        self._update_comparison()
        self._plot_original()
        self._plot_processed()
        self._update_action_state()

    # ──────────────────── 参数对比 ────────────────────

    def _update_comparison(self):
        """更新处理前后参数对比表"""
        if self._signal is not None:
            self._lbl_pga_before.setText(f"{self._signal.pga:.4f}")
            self._lbl_arias_before.setText(f"{_arias_total(self._signal):.4f}")
            self._lbl_d595_before.setText(f"{self._signal.effective_duration:.2f}")
        else:
            self._lbl_pga_before.setText("--")
            self._lbl_arias_before.setText("--")
            self._lbl_d595_before.setText("--")

        if self._processed is not None:
            self._lbl_pga_after.setText(f"{self._processed.pga:.4f}")
            self._lbl_arias_after.setText(f"{_arias_total(self._processed):.4f}")
            self._lbl_d595_after.setText(f"{self._processed.effective_duration:.2f}")
        else:
            self._lbl_pga_after.setText("--")
            self._lbl_arias_after.setText("--")
            self._lbl_d595_after.setText("--")

    def _update_action_state(self):
        enabled = self._processed is not None
        for b in [self._baseline_btn, self._filter_btn, self._reset_btn,
                  self._trim_btn, self._auto_trim_btn]:
            b.setEnabled(enabled)

    # ──────────────────── 绘图 ────────────────────

    def _plot_original(self):
        if self._signal is None:
            return
        c = get_mpl_colors(self._dark)
        self._orig_plot.clear()
        ax = self._orig_plot.ax
        ax.plot(self._signal.time, self._signal.acc,
                color=c['primary'], linewidth=0.6)
        ax.set_title(
            f"原始信号  |  PGA={self._signal.pga:.4f}g  "
            f"Ia={_arias_total(self._signal):.4f}m/s  "
            f"D5-95={self._signal.effective_duration:.2f}s",
            fontsize=10,
        )
        ax.set_xlabel("时间 (s)", fontsize=9)
        ax.set_ylabel("加速度 (g)", fontsize=9)
        self._orig_plot.refresh()

    def _plot_processed(self):
        if self._processed is None:
            return
        c = get_mpl_colors(self._dark)
        self._proc_plot.clear()
        ax = self._proc_plot.ax
        ax.plot(self._processed.time, self._processed.acc,
                color=c['accent'], linewidth=0.6)
        ax.set_title(
            f"处理后信号  |  PGA={self._processed.pga:.4f}g  "
            f"Ia={_arias_total(self._processed):.4f}m/s  "
            f"D5-95={self._processed.effective_duration:.2f}s",
            fontsize=10,
        )
        ax.set_xlabel("时间 (s)", fontsize=9)
        ax.set_ylabel("加速度 (g)", fontsize=9)
        self._proc_plot.refresh()

    # ──────────────────── 处理操作 ────────────────────

    def _apply_baseline(self):
        if self._processed is None:
            QMessageBox.warning(self, "警告", "未选择记录，无法处理")
            return
        from seiswave.core.filter import correct_baseline
        method = 'poly' if self._baseline_combo.currentIndex() == 0 else 'bilinear'
        self._processed = correct_baseline(
            self._processed,
            method=method,
            order=self._poly_order_spin.value(),
            copy=False,
        )
        self._after_process()

    def _apply_filter(self):
        if self._processed is None:
            QMessageBox.warning(self, "警告", "未选择记录，无法处理")
            return
        m = {0: 'bandpass', 1: 'lowpass', 2: 'highpass'}
        ftype = m[self._filter_type_combo.currentIndex()]
        f1, f2 = self._f1_spin.value(), self._f2_spin.value()
        freqs = (f1, f2) if ftype == 'bandpass' else (
            f2 if ftype == 'lowpass' else f1)
        try:
            self._processed.acc = Filter.butterworth(
                self._processed.acc, self._processed.dt,
                ftype=ftype, order=self._filter_order_spin.value(),
                freqs=freqs,
            )
            self._after_process()
        except Exception as e:
            QMessageBox.critical(self, "滤波错误", str(e))

    def _apply_trim(self):
        if self._processed is None:
            QMessageBox.warning(self, "警告", "未选择记录，无法处理")
            return
        t1 = self._trim_start.value()
        t2 = self._trim_end.value()
        if t2 <= t1:
            QMessageBox.warning(self, "警告", "结束时间必须大于起始时间")
            return
        i1 = max(0, int(round(t1 / self._processed.dt)))
        i2 = min(self._processed.n - 1, int(round(t2 / self._processed.dt)))
        if i2 <= i1:
            return
        self._processed.trim(i1, i2)
        self._after_process()

    def _apply_auto_trim(self):
        if self._processed is None:
            QMessageBox.warning(self, "警告", "未选择记录，无法处理")
            return
        self._processed.auto_trim(0.05, 0.95)
        self._after_process()

    def _after_process(self):
        """处理操作后的统一更新"""
        self._update_comparison()
        self._plot_processed()
        self.signal_processed.emit(self._processed)

    def _reset(self):
        if self._signal is not None:
            self.set_signal(self._signal)

    # ──────────────────── 公共接口 ────────────────────

    def get_processed(self):
        return self._processed

    def set_dark(self, dark: bool):
        self._dark = dark
        self._orig_plot.set_dark(dark)
        self._proc_plot.set_dark(dark)
