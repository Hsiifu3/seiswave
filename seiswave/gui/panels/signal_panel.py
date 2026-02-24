"""信号处理面板"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QComboBox, QFormLayout, QPushButton,
    QSplitter, QMessageBox, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core import EQSignal, Filter
from seiswave.gui.widgets.plot_widget import PlotWidget
from seiswave.gui.styles import get_mpl_colors


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
        param_widget = QWidget(); param_widget.setMinimumWidth(290)
        param_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        param_layout = QVBoxLayout(param_widget); param_layout.setContentsMargins(0, 0, 0, 0)

        info_group = QGroupBox("当前处理记录")
        info_layout = QVBoxLayout(info_group)
        self._picker = QComboBox(); self._picker.addItem("请选择导入记录...")
        self._pick_btn = QPushButton("载入记录"); self._pick_btn.clicked.connect(self._apply_selection)
        info_layout.addWidget(self._picker); info_layout.addWidget(self._pick_btn)
        self._info_label = QLabel("未选择信号，处理操作已禁用")
        self._info_label.setWordWrap(True)
        info_layout.addWidget(self._info_label)
        param_layout.addWidget(info_group)

        baseline_group = QGroupBox("基线校正")
        baseline_form = QFormLayout(baseline_group)
        self._baseline_combo = QComboBox(); self._baseline_combo.addItems(["多项式去趋势", "双线性去趋势"])
        self._poly_order_spin = QSpinBox(); self._poly_order_spin.setRange(1, 6); self._poly_order_spin.setValue(2)
        self._baseline_btn = QPushButton("应用基线校正"); self._baseline_btn.clicked.connect(self._apply_baseline)
        baseline_form.addRow("方法:", self._baseline_combo)
        baseline_form.addRow("多项式阶数:", self._poly_order_spin)
        baseline_form.addRow(self._baseline_btn)
        param_layout.addWidget(baseline_group)

        filter_group = QGroupBox("Butterworth 滤波")
        filter_form = QFormLayout(filter_group)
        self._filter_type_combo = QComboBox(); self._filter_type_combo.addItems(["带通", "低通", "高通"])
        self._filter_order_spin = QSpinBox(); self._filter_order_spin.setRange(1, 10); self._filter_order_spin.setValue(4)
        self._f1_spin = QDoubleSpinBox(); self._f1_spin.setRange(0.01, 50.0); self._f1_spin.setValue(0.1)
        self._f2_spin = QDoubleSpinBox(); self._f2_spin.setRange(0.1, 100.0); self._f2_spin.setValue(25.0)
        self._filter_btn = QPushButton("应用滤波"); self._filter_btn.clicked.connect(self._apply_filter)
        filter_form.addRow("滤波类型:", self._filter_type_combo)
        filter_form.addRow("滤波器阶数:", self._filter_order_spin)
        filter_form.addRow("低频截止 f₁ (Hz):", self._f1_spin)
        filter_form.addRow("高频截止 f₂ (Hz):", self._f2_spin)
        filter_form.addRow(self._filter_btn)
        param_layout.addWidget(filter_group)

        self._reset_btn = QPushButton("重置"); self._reset_btn.clicked.connect(self._reset)
        param_layout.addWidget(self._reset_btn); param_layout.addStretch(); layout.addWidget(param_widget)

        right_splitter = QSplitter(Qt.Vertical)
        self._orig_plot = PlotWidget(dark=self._dark, show_toolbar=False)
        self._proc_plot = PlotWidget(dark=self._dark, show_toolbar=False)
        right_splitter.addWidget(self._orig_plot); right_splitter.addWidget(self._proc_plot)
        layout.addWidget(right_splitter, 1)
        self._update_action_state()

    def set_signal_pool(self, signals):
        self._signal_pool = signals or []
        self._picker.clear(); self._picker.addItem("请选择导入记录...")
        for s in self._signal_pool:
            self._picker.addItem(s.name or "未命名记录")
        if not self._signal_pool:
            self._info_label.setText("未导入记录，处理操作已禁用")
            self._signal = None; self._processed = None
            self._update_action_state()

    def _apply_selection(self):
        idx = self._picker.currentIndex() - 1
        if idx < 0 or idx >= len(self._signal_pool):
            QMessageBox.information(self, "提示", "请先从下拉框选择记录")
            return
        self.set_signal(self._signal_pool[idx])

    def set_signal(self, signal):
        self._signal = signal
        self._processed = EQSignal(signal.acc.copy(), signal.dt, name=signal.name)
        self._info_label.setText(f"当前记录: {signal.name}\nPGA={signal.pga:.4f}g, 持时={signal.duration:.2f}s, Δt={signal.dt:.4f}s")
        self._plot_original(); self._plot_processed(); self._update_action_state()

    def _update_action_state(self):
        enabled = self._processed is not None
        for b in [self._baseline_btn, self._filter_btn, self._reset_btn]:
            b.setEnabled(enabled)

    def _plot_original(self):
        if self._signal is None: return
        c = get_mpl_colors(self._dark)
        self._orig_plot.clear(); ax = self._orig_plot.ax
        ax.plot(self._signal.time, self._signal.acc, color=c['primary'], linewidth=0.6)
        ax.set_title("原始信号", fontsize=11); self._orig_plot.refresh()

    def _plot_processed(self):
        if self._processed is None: return
        c = get_mpl_colors(self._dark)
        self._proc_plot.clear(); ax = self._proc_plot.ax
        ax.plot(self._processed.time, self._processed.acc, color=c['accent'], linewidth=0.6)
        ax.set_title(f"处理后信号 (PGA={self._processed.pga:.4f}g)", fontsize=11); self._proc_plot.refresh()

    def _apply_baseline(self):
        if self._processed is None:
            QMessageBox.warning(self, "警告", "未选择记录，无法处理")
            return
        if self._baseline_combo.currentIndex() == 0:
            self._processed.acc = Filter.detrend(self._processed.acc, self._processed.dt, order=self._poly_order_spin.value())
        else:
            self._processed.acc = Filter.bilinear_detrend(self._processed.acc)
        self._plot_processed(); self.signal_processed.emit(self._processed)

    def _apply_filter(self):
        if self._processed is None:
            QMessageBox.warning(self, "警告", "未选择记录，无法处理")
            return
        m = {0: 'bandpass', 1: 'lowpass', 2: 'highpass'}
        ftype = m[self._filter_type_combo.currentIndex()]
        f1, f2 = self._f1_spin.value(), self._f2_spin.value()
        freqs = (f1, f2) if ftype == 'bandpass' else (f2 if ftype == 'lowpass' else f1)
        try:
            self._processed.acc = Filter.butterworth(self._processed.acc, self._processed.dt, ftype=ftype, order=self._filter_order_spin.value(), freqs=freqs)
            self._plot_processed(); self.signal_processed.emit(self._processed)
        except Exception as e:
            QMessageBox.critical(self, "滤波错误", str(e))

    def _reset(self):
        if self._signal is not None: self.set_signal(self._signal)

    def get_processed(self):
        return self._processed

    def set_dark(self, dark: bool):
        self._dark = dark
        self._orig_plot.set_dark(dark); self._proc_plot.set_dark(dark)
