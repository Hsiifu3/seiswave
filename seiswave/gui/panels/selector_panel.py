"""
选波面板

结构周期输入（T1/T2/T3）、筛选条件设置、执行选波按钮。
结果列表、反应谱对比图（选中波 vs 规范谱）。
"""

import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QCheckBox, QFormLayout, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core import WaveSelector, SelectionCriteria, Spectra, CodeSpectrum
from seiswave.gui.widgets.spectrum_plot import SpectrumPlot
from seiswave.gui.widgets.progress_dialog import ProgressDialog
from seiswave.gui.workers import SelectionWorker, BatchSpectrumWorker
from seiswave.gui.styles import get_mpl_colors


class SelectorPanel(QWidget):
    """选波面板"""

    selection_done = Signal(list)  # 选波完成信号

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._signals = []
        self._code_periods = None
        self._code_sa = None
        self._results = []
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 左侧参数面板
        param_widget = QWidget()
        param_widget.setFixedWidth(320)
        param_layout = QVBoxLayout(param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)

        # 结构周期
        period_group = QGroupBox("结构周期")
        period_form = QFormLayout(period_group)

        self._t1_spin = QDoubleSpinBox()
        self._t1_spin.setRange(0.01, 10.0)
        self._t1_spin.setSingleStep(0.01)
        self._t1_spin.setValue(1.0)
        self._t1_spin.setDecimals(3)
        period_form.addRow("T₁ (s):", self._t1_spin)

        self._t2_spin = QDoubleSpinBox()
        self._t2_spin.setRange(0.01, 10.0)
        self._t2_spin.setSingleStep(0.01)
        self._t2_spin.setValue(0.5)
        self._t2_spin.setDecimals(3)
        period_form.addRow("T₂ (s):", self._t2_spin)

        self._t3_spin = QDoubleSpinBox()
        self._t3_spin.setRange(0.01, 10.0)
        self._t3_spin.setSingleStep(0.01)
        self._t3_spin.setValue(0.3)
        self._t3_spin.setDecimals(3)
        period_form.addRow("T₃ (s):", self._t3_spin)

        param_layout.addWidget(period_group)

        # 筛选条件
        filter_group = QGroupBox("筛选条件")
        filter_form = QFormLayout(filter_group)

        self._dur_factor_spin = QDoubleSpinBox()
        self._dur_factor_spin.setRange(1.0, 20.0)
        self._dur_factor_spin.setSingleStep(0.5)
        self._dur_factor_spin.setValue(5.0)
        filter_form.addRow("持时倍数:", self._dur_factor_spin)

        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.05, 0.50)
        self._tol_spin.setSingleStep(0.05)
        self._tol_spin.setValue(0.20)
        self._tol_spin.setDecimals(2)
        filter_form.addRow("谱偏差容限:", self._tol_spin)

        self._shear_check = QCheckBox("底部剪力校核")
        filter_form.addRow(self._shear_check)

        self._shear_low_spin = QDoubleSpinBox()
        self._shear_low_spin.setRange(0.1, 1.0)
        self._shear_low_spin.setValue(0.65)
        self._shear_low_spin.setDecimals(2)
        filter_form.addRow("剪力比下限:", self._shear_low_spin)

        self._shear_high_spin = QDoubleSpinBox()
        self._shear_high_spin.setRange(1.0, 2.0)
        self._shear_high_spin.setValue(1.35)
        self._shear_high_spin.setDecimals(2)
        filter_form.addRow("剪力比上限:", self._shear_high_spin)

        param_layout.addWidget(filter_group)

        # 执行按钮
        self._run_btn = QPushButton("▶ 执行选波")
        self._run_btn.clicked.connect(self._run_selection)
        param_layout.addWidget(self._run_btn)

        # 结果统计
        self._stat_label = QLabel("等待执行...")
        self._stat_label.setWordWrap(True)
        param_layout.addWidget(self._stat_label)

        param_layout.addStretch()
        layout.addWidget(param_widget)

        # 右侧：结果表格 + 对比图
        right_splitter = QSplitter(Qt.Vertical)

        # 反应谱对比图
        self._plot = SpectrumPlot(dark=self._dark)
        right_splitter.addWidget(self._plot)

        # 结果表格
        self._result_table = QTableWidget()
        self._result_table.setColumnCount(6)
        self._result_table.setHorizontalHeaderLabels([
            "文件名", "有效持时(s)", "T₁偏差(%)", "T₂偏差(%)", "T₃偏差(%)", "通过",
        ])
        self._result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._result_table.verticalHeader().setVisible(False)
        header = self._result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 6):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._result_table.itemSelectionChanged.connect(self._on_result_selected)
        right_splitter.addWidget(self._result_table)

        right_splitter.setSizes([500, 250])
        layout.addWidget(right_splitter, 1)

    def set_signals(self, signals):
        """设置待选地震波"""
        self._signals = signals

    def set_code_spectrum(self, periods, sa):
        """设置规范谱"""
        self._code_periods = periods
        self._code_sa = sa

    def _run_selection(self):
        """执行选波"""
        if not self._signals:
            QMessageBox.warning(self, "警告", "请先导入地震动数据")
            return
        if self._code_sa is None:
            QMessageBox.warning(self, "警告", "请先设置规范谱参数")
            return

        T_main = [self._t1_spin.value(), self._t2_spin.value(), self._t3_spin.value()]

        # 从规范谱获取 Tg 和 alpha_max（通过查找水平段）
        # 简化：直接用规范谱数据
        criteria = SelectionCriteria(
            Tg=0.0,  # 占位，selector 内部会用 target_spectrum
            alpha_max=0.0,
            T_main=T_main,
            zeta=0.05,
            duration_factor=self._dur_factor_spin.value(),
            spectral_tol=self._tol_spin.value(),
            shear_check=self._shear_check.isChecked(),
            shear_range=(self._shear_low_spin.value(), self._shear_high_spin.value()),
        )

        selector = WaveSelector(criteria)
        selector.target_spectrum = (self._code_periods, self._code_sa)

        # 进度对话框
        progress = ProgressDialog("选波计算中...", self)

        self._worker = SelectionWorker(selector, self._signals, parent=self)
        self._worker.signals.progress.connect(progress.update_progress)
        self._worker.signals.finished.connect(
            lambda results: self._on_selection_done(results, progress))
        self._worker.signals.error.connect(
            lambda err: self._on_selection_error(err, progress))

        self._worker.start()
        progress.exec()

        if progress.is_cancelled and self._worker:
            self._worker.cancel()

    def _on_selection_done(self, results, progress):
        self._results = results
        progress.set_finished(f"选波完成，{sum(1 for r in results if r.passed)}/{len(results)} 条通过")

        # 填充结果表格
        self._result_table.setRowCount(len(results))
        for i, r in enumerate(results):
            self._result_table.setItem(i, 0, QTableWidgetItem(r.signal.name))
            self._result_table.setItem(i, 1, QTableWidgetItem(f"{r.effective_duration:.2f}"))
            for j, t_key in enumerate(sorted(r.deviations.keys())):
                val = r.deviations[t_key] * 100
                self._result_table.setItem(i, 2 + j, QTableWidgetItem(f"{val:.1f}"))
            status = "✓" if r.passed else "✗"
            self._result_table.setItem(i, 5, QTableWidgetItem(status))
            # 右对齐数值列
            for j in range(1, 6):
                item = self._result_table.item(i, j)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

        passed = sum(1 for r in results if r.passed)
        self._stat_label.setText(
            f"筛选结果: {passed}/{len(results)} 条通过\n"
            f"通过率: {passed/len(results)*100:.1f}%" if results else "无结果"
        )

        # 绘制通过波的反应谱对比
        self._plot_passed_spectra()
        self.selection_done.emit(results)

    def _on_selection_error(self, err, progress):
        progress.set_finished(f"计算出错: {err}")

    def _plot_passed_spectra(self):
        """绘制通过波的反应谱与规范谱对比"""
        if not self._results or self._code_sa is None:
            return

        passed = [r for r in self._results if r.passed]
        if not passed:
            self._plot.clear()
            self._plot.ax.text(0.5, 0.5, "无通过的地震波",
                               transform=self._plot.ax.transAxes,
                               ha='center', va='center', fontsize=14)
            self._plot.refresh()
            return

        # 计算通过波的反应谱
        periods = self._code_periods
        wave_spectra = []
        wave_labels = []
        for r in passed:
            spec = Spectra.compute(r.signal.acc, r.signal.dt, periods, 0.05)
            wave_spectra.append(spec.sa)
            wave_labels.append(r.signal.name)

        self._plot.plot_comparison(periods, self._code_sa, wave_spectra, wave_labels)
        self._plot.plot_envelope(periods, self._code_sa)

    def _on_result_selected(self):
        """选中结果行时高亮对应谱"""
        rows = self._result_table.selectionModel().selectedRows()
        if not rows or not self._results:
            return
        row = rows[0].row()
        if row >= len(self._results):
            return

        r = self._results[row]
        periods = self._code_periods
        spec = Spectra.compute(r.signal.acc, r.signal.dt, periods, 0.05)

        self._plot.clear()
        self._plot.plot_code_spectrum(periods, self._code_sa)
        self._plot.plot_envelope(periods, self._code_sa)
        colors = get_mpl_colors(self._dark)
        self._plot.plot_spectrum(periods, spec.sa, label=r.signal.name,
                                color=colors['primary'], linewidth=2.0)
        self._plot.ax.set_title(f"反应谱对比: {r.signal.name}", fontsize=11)
        self._plot.refresh()

    def get_results(self):
        return self._results

    def get_passed_results(self):
        return [r for r in self._results if r.passed]

    def set_dark(self, dark: bool):
        self._dark = dark
        self._plot.set_dark(dark)
