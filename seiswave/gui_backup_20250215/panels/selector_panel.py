"""
选波面板

PEER 数据库加载、结构周期输入、筛选条件设置、执行选波。
结果列表、反应谱对比图（选中波 vs 规范谱）。
"""

import os
import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QFormLayout, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox, QFileDialog, QLineEdit,
    QProgressBar,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core.peer_db import PeerDatabase
from seiswave.core.selector import WaveSelector, SelectionConfig, SelectionResult
from seiswave.gui.widgets.spectrum_plot import SpectrumPlot
from seiswave.gui.workers import PeerLoadWorker, PeerSelectWorker
from seiswave.gui.styles import get_mpl_colors


class SelectorPanel(QWidget):
    """选波面板"""

    selection_done = Signal(list)  # list[SelectionResult]

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._db = PeerDatabase()
        self._code_periods = None
        self._code_sa = None
        self._results: list[SelectionResult] = []
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # ── 左侧参数面板 ──
        param_widget = QWidget()
        param_widget.setFixedWidth(340)
        param_layout = QVBoxLayout(param_widget)
        param_layout.setContentsMargins(0, 0, 0, 0)

        # PEER 数据库
        db_group = QGroupBox("PEER 数据库")
        db_form = QFormLayout(db_group)
        db_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        db_form.setLabelAlignment(Qt.AlignRight)

        dir_row = QHBoxLayout()
        dir_row.setSpacing(4)
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择 PEER 数据目录...")
        self._dir_edit.setReadOnly(True)
        dir_row.addWidget(self._dir_edit, 1)
        self._browse_btn = QPushButton("浏览...")
        self._browse_btn.setProperty("secondary", True)
        self._browse_btn.setFixedHeight(self._dir_edit.sizeHint().height())
        self._browse_btn.clicked.connect(self._browse_db)
        dir_row.addWidget(self._browse_btn)
        db_form.addRow("数据目录:", dir_row)

        self._load_btn = QPushButton("加载数据库")
        self._load_btn.clicked.connect(self._load_database)
        db_form.addRow(self._load_btn)

        self._db_label = QLabel("未加载")
        self._db_label.setWordWrap(True)
        db_form.addRow(self._db_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        db_form.addRow(self._progress_bar)

        param_layout.addWidget(db_group)

        # 结构周期
        period_group = QGroupBox("结构周期")
        period_form = QFormLayout(period_group)
        period_form.setLabelAlignment(Qt.AlignRight)
        period_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._t1_spin = QDoubleSpinBox()
        self._t1_spin.setRange(0.01, 10.0)
        self._t1_spin.setSingleStep(0.01)
        self._t1_spin.setValue(1.0)
        self._t1_spin.setDecimals(3)
        self._t1_spin.setFixedWidth(120)
        period_form.addRow("T₁ (s):", self._t1_spin)

        self._t2_spin = QDoubleSpinBox()
        self._t2_spin.setRange(0.01, 10.0)
        self._t2_spin.setSingleStep(0.01)
        self._t2_spin.setValue(0.5)
        self._t2_spin.setDecimals(3)
        self._t2_spin.setFixedWidth(120)
        period_form.addRow("T₂ (s):", self._t2_spin)

        self._t3_spin = QDoubleSpinBox()
        self._t3_spin.setRange(0.01, 10.0)
        self._t3_spin.setSingleStep(0.01)
        self._t3_spin.setValue(0.3)
        self._t3_spin.setDecimals(3)
        self._t3_spin.setFixedWidth(120)
        period_form.addRow("T₃ (s):", self._t3_spin)

        param_layout.addWidget(period_group)

        # 筛选条件
        filter_group = QGroupBox("筛选条件")
        filter_form = QFormLayout(filter_group)
        filter_form.setLabelAlignment(Qt.AlignRight)
        filter_form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)

        self._n_select_spin = QSpinBox()
        self._n_select_spin.setRange(1, 20)
        self._n_select_spin.setValue(5)
        self._n_select_spin.setFixedWidth(120)
        filter_form.addRow("选取数量:", self._n_select_spin)

        self._dur_factor_spin = QDoubleSpinBox()
        self._dur_factor_spin.setRange(1.0, 20.0)
        self._dur_factor_spin.setSingleStep(0.5)
        self._dur_factor_spin.setValue(5.0)
        self._dur_factor_spin.setFixedWidth(120)
        filter_form.addRow("持时倍数:", self._dur_factor_spin)

        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.10, 0.50)
        self._tol_spin.setSingleStep(0.05)
        self._tol_spin.setValue(0.30)
        self._tol_spin.setDecimals(2)
        self._tol_spin.setFixedWidth(120)
        filter_form.addRow("谱偏差容限:", self._tol_spin)

        self._scale_lo_spin = QDoubleSpinBox()
        self._scale_lo_spin.setRange(0.1, 2.0)
        self._scale_lo_spin.setValue(0.5)
        self._scale_lo_spin.setDecimals(2)
        self._scale_lo_spin.setFixedWidth(120)
        filter_form.addRow("缩放下限:", self._scale_lo_spin)

        self._scale_hi_spin = QDoubleSpinBox()
        self._scale_hi_spin.setRange(1.0, 10.0)
        self._scale_hi_spin.setValue(4.0)
        self._scale_hi_spin.setDecimals(2)
        self._scale_hi_spin.setFixedWidth(120)
        filter_form.addRow("缩放上限:", self._scale_hi_spin)

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

        # ── 右侧：结果表格 + 对比图 ──
        right_splitter = QSplitter(Qt.Vertical)

        self._plot = SpectrumPlot(dark=self._dark, log_x=False,
                                  show_toolbar=True, compact_toolbar=True)
        right_splitter.addWidget(self._plot)

        self._result_table = QTableWidget()
        self._result_table.setColumnCount(7)
        self._result_table.setHorizontalHeaderLabels([
            "RSN", "事件", "台站", "分量", "缩放系数", "RMSE", "主周期偏差",
        ])
        self._result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._result_table.verticalHeader().setVisible(False)
        header = self._result_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        for i in [0, 3, 4, 5, 6]:
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._result_table.itemSelectionChanged.connect(self._on_result_selected)
        right_splitter.addWidget(self._result_table)

        right_splitter.setSizes([500, 200])
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)
        layout.addWidget(right_splitter, 1)

    # ──────────── 数据库操作 ────────────

    def _browse_db(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择 PEER 数据目录")
        if dir_path:
            self._dir_edit.setText(dir_path)

    def _load_database(self):
        dir_path = self._dir_edit.text()
        if not dir_path:
            QMessageBox.warning(self, "警告", "请先选择 PEER 数据目录")
            return

        self._load_btn.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)  # indeterminate
        self._db_label.setText("正在加载...")

        self._worker = PeerLoadWorker(dir_path, parent=self)
        self._worker.signals.progress.connect(self._on_load_progress)
        self._worker.signals.finished.connect(self._on_load_done)
        self._worker.signals.error.connect(self._on_load_error)
        self._worker.start()

    def _on_load_progress(self, pct, msg):
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(pct)
        self._db_label.setText(msg)

    def _on_load_done(self, db: PeerDatabase):
        self._db = db
        self._load_btn.setEnabled(True)
        self._progress_bar.setVisible(False)

        n_h = len(db.get_horizontal())
        n_v = len(db.get_vertical())
        self._db_label.setText(
            f"已加载: {len(db)} 条记录\n"
            f"水平分量: {n_h}, 竖向分量: {n_v}\n"
            f"反应谱已缓存"
        )

    def _on_load_error(self, err):
        self._load_btn.setEnabled(True)
        self._progress_bar.setVisible(False)
        self._db_label.setText(f"加载失败: {err}")
        QMessageBox.critical(self, "错误", f"数据库加载失败:\n{err}")

    # ──────────── 选波操作 ────────────

    def set_code_spectrum(self, periods, sa):
        self._code_periods = np.asarray(periods)
        self._code_sa = np.asarray(sa)

    def _run_selection(self):
        if len(self._db) == 0:
            QMessageBox.warning(self, "警告", "请先加载 PEER 数据库")
            return
        if self._code_sa is None:
            QMessageBox.warning(self, "警告", "请先设置规范谱参数")
            return

        T_main = [self._t1_spin.value(), self._t2_spin.value(),
                   self._t3_spin.value()]

        # 使用数据库的周期数组
        db_periods = self._db.spectra_periods
        if db_periods is None:
            QMessageBox.warning(self, "警告", "数据库未预计算反应谱")
            return

        # 将规范谱插值到数据库周期
        from scipy.interpolate import interp1d
        f = interp1d(self._code_periods, self._code_sa,
                     kind='linear', fill_value='extrapolate')
        target_sa = np.maximum(f(db_periods), 0.0)

        config = SelectionConfig(
            target_sa=target_sa,
            periods=db_periods,
            T_main=T_main,
            n_select=self._n_select_spin.value(),
            duration_factor=self._dur_factor_spin.value(),
            spectral_tol=self._tol_spin.value(),
            scale_range=(self._scale_lo_spin.value(), self._scale_hi_spin.value()),
        )

        self._run_btn.setEnabled(False)
        self._stat_label.setText("选波计算中...")

        self._worker = PeerSelectWorker(config, self._db, parent=self)
        self._worker.signals.finished.connect(self._on_selection_done)
        self._worker.signals.error.connect(self._on_selection_error)
        self._worker.start()

    def _on_selection_done(self, results: list):
        self._results = results
        self._run_btn.setEnabled(True)

        # 填充结果表格
        self._result_table.setRowCount(len(results))
        for i, r in enumerate(results):
            rec = r.record
            self._result_table.setItem(i, 0, QTableWidgetItem(str(rec.rsn)))
            self._result_table.setItem(i, 1, QTableWidgetItem(rec.event))
            self._result_table.setItem(i, 2, QTableWidgetItem(rec.station))
            self._result_table.setItem(i, 3, QTableWidgetItem(rec.component))
            self._result_table.setItem(i, 4, QTableWidgetItem(f"{r.scale_factor:.2f}"))
            self._result_table.setItem(i, 5, QTableWidgetItem(f"{r.match_error:.4f}"))

            devs_str = ", ".join(f"{v:.0%}" for v in r.deviations.values())
            self._result_table.setItem(i, 6, QTableWidgetItem(devs_str))

            for j in range(4, 7):
                item = self._result_table.item(i, j)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

        self._stat_label.setText(f"选中 {len(results)} 条地震波")

        # 绘制对比图
        self._plot_results()
        self.selection_done.emit(results)

    def _on_selection_error(self, err):
        self._run_btn.setEnabled(True)
        self._stat_label.setText(f"选波出错: {err}")
        QMessageBox.critical(self, "错误", f"选波失败:\n{err}")

    # ──────────── 绘图 ────────────

    def _plot_results(self):
        if not self._results or self._code_sa is None:
            return

        db_periods = self._db.spectra_periods
        period_map = np.array([
            np.argmin(np.abs(db_periods - p)) for p in db_periods
        ])

        self._plot.clear()
        colors = get_mpl_colors(self._dark)
        palette = colors['palette']

        # 规范谱
        self._plot.plot_code_spectrum(self._code_periods, self._code_sa)

        # 各波缩放谱
        sa_list = []
        labels = []
        for i, r in enumerate(self._results):
            scaled_sa = r.record.sa[period_map] * r.scale_factor
            sa_list.append(scaled_sa)
            label = f"RSN{r.record.rsn} ({r.scale_factor:.2f}x)"
            labels.append(label)
            self._plot.ax.plot(db_periods, scaled_sa, label=label,
                               color=palette[i % len(palette)],
                               linewidth=1.2, alpha=0.8)

        # 均值谱
        if len(sa_list) > 1:
            mean_sa = np.mean(sa_list, axis=0)
            self._plot.ax.plot(db_periods, mean_sa, label="均值谱",
                               color=colors['fg'], linewidth=2.0, linestyle='-.')

        # 容许范围
        self._plot.plot_envelope(self._code_periods, self._code_sa)

        self._plot.ax.legend(fontsize=8, framealpha=0.8, loc='upper right')
        self._plot.ax.set_title("选波结果 - 反应谱对比", fontsize=12)
        self._plot.refresh()

    def _on_result_selected(self):
        rows = self._result_table.selectionModel().selectedRows()
        if not rows or not self._results:
            return
        row = rows[0].row()
        if row >= len(self._results):
            return

        r = self._results[row]
        db_periods = self._db.spectra_periods

        self._plot.clear()
        self._plot.plot_code_spectrum(self._code_periods, self._code_sa)
        self._plot.plot_envelope(self._code_periods, self._code_sa)

        colors = get_mpl_colors(self._dark)
        scaled_sa = r.record.sa * r.scale_factor
        label = f"RSN{r.record.rsn} {r.record.component} ({r.scale_factor:.2f}x)"
        self._plot.ax.plot(db_periods, scaled_sa, label=label,
                           color=colors['primary'], linewidth=2.0)

        self._plot.ax.legend(fontsize=9, framealpha=0.8)
        self._plot.ax.set_title(f"RSN{r.record.rsn} - {r.record.event}", fontsize=11)
        self._plot.refresh()

    # ──────────── 外部接口 ────────────

    def get_results(self):
        return self._results

    def get_database(self):
        return self._db

    def set_dark(self, dark: bool):
        self._dark = dark
        self._plot.set_dark(dark)
