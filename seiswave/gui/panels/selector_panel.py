import numpy as np
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QDoubleSpinBox, QSpinBox, QFormLayout, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMessageBox, QFileDialog, QLineEdit,
    QProgressBar, QSizePolicy, QComboBox,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core.peer_db import PeerDatabase, PeerRecord
from seiswave.core.selector import SelectionConfig, SelectionResult
from seiswave.core import Spectra
from seiswave.gui.widgets.spectrum_plot import SpectrumPlot
from seiswave.gui.workers import PeerLoadWorker, PeerSelectWorker
from seiswave.gui.styles import get_mpl_colors


class SelectorPanel(QWidget):
    selection_done = Signal(list)

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._db = PeerDatabase()
        self._imported_db = PeerDatabase(data_dir='.')
        self._imported_signals = []
        self._code_periods = None
        self._code_sa = None
        self._results = []
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        param_widget = QWidget(); param_widget.setMinimumWidth(320)
        param_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        param_layout = QVBoxLayout(param_widget); param_layout.setContentsMargins(0, 0, 0, 0)

        source_group = QGroupBox("选波数据源")
        source_form = QFormLayout(source_group)
        self._source_combo = QComboBox(); self._source_combo.addItems(["PEER数据库（天然波候选）", "导入地震动（候选/校核）"])
        self._source_combo.currentIndexChanged.connect(self._on_source_changed)
        self._source_hint = QLabel("说明：导入地震动可作为项目自有候选库，或用于与规范谱做校核对比。")
        self._source_hint.setWordWrap(True)
        source_form.addRow("来源:", self._source_combo)
        source_form.addRow(self._source_hint)
        param_layout.addWidget(source_group)

        db_group = QGroupBox("PEER 数据库")
        db_form = QFormLayout(db_group)
        dir_row = QHBoxLayout(); self._dir_edit = QLineEdit(); self._dir_edit.setReadOnly(True)
        self._browse_btn = QPushButton("浏览..."); self._browse_btn.clicked.connect(self._browse_db)
        dir_row.addWidget(self._dir_edit, 1); dir_row.addWidget(self._browse_btn)
        db_form.addRow("数据目录:", dir_row)
        self._load_btn = QPushButton("加载数据库"); self._load_btn.clicked.connect(self._load_database)
        self._db_label = QLabel("未加载")
        self._progress_bar = QProgressBar(); self._progress_bar.setVisible(False)
        db_form.addRow(self._load_btn); db_form.addRow(self._db_label); db_form.addRow(self._progress_bar)
        self._db_group = db_group
        param_layout.addWidget(db_group)

        period_group = QGroupBox("结构周期")
        pf = QFormLayout(period_group)
        self._t1_spin = QDoubleSpinBox(); self._t1_spin.setRange(0.01, 10.0); self._t1_spin.setValue(1.0)
        self._t2_spin = QDoubleSpinBox(); self._t2_spin.setRange(0.01, 10.0); self._t2_spin.setValue(0.5)
        self._t3_spin = QDoubleSpinBox(); self._t3_spin.setRange(0.01, 10.0); self._t3_spin.setValue(0.3)
        pf.addRow("T₁ (s):", self._t1_spin); pf.addRow("T₂ (s):", self._t2_spin); pf.addRow("T₃ (s):", self._t3_spin)
        param_layout.addWidget(period_group)

        filter_group = QGroupBox("筛选条件")
        ff = QFormLayout(filter_group)
        self._n_select_spin = QSpinBox(); self._n_select_spin.setRange(1, 20); self._n_select_spin.setValue(5)
        self._dur_factor_spin = QDoubleSpinBox(); self._dur_factor_spin.setRange(1.0, 20.0); self._dur_factor_spin.setValue(5.0)
        self._tol_spin = QDoubleSpinBox(); self._tol_spin.setRange(0.10, 0.50); self._tol_spin.setValue(0.30)
        self._scale_lo_spin = QDoubleSpinBox(); self._scale_lo_spin.setRange(0.1, 2.0); self._scale_lo_spin.setValue(0.5)
        self._scale_hi_spin = QDoubleSpinBox(); self._scale_hi_spin.setRange(1.0, 10.0); self._scale_hi_spin.setValue(4.0)
        ff.addRow("选取数量:", self._n_select_spin); ff.addRow("持时倍数:", self._dur_factor_spin)
        ff.addRow("谱偏差容限:", self._tol_spin); ff.addRow("缩放下限:", self._scale_lo_spin); ff.addRow("缩放上限:", self._scale_hi_spin)
        param_layout.addWidget(filter_group)

        self._run_btn = QPushButton("执行选波"); self._run_btn.clicked.connect(self._run_selection)
        self._stat_label = QLabel("等待执行...")
        param_layout.addWidget(self._run_btn); param_layout.addWidget(self._stat_label); param_layout.addStretch(); layout.addWidget(param_widget)

        right_splitter = QSplitter(Qt.Vertical)
        self._plot = SpectrumPlot(dark=self._dark, log_x=False, show_toolbar=False)
        self._result_table = QTableWidget(); self._result_table.setColumnCount(7)
        self._result_table.setHorizontalHeaderLabels(["RSN", "事件", "台站", "分量", "缩放系数", "RMSE", "主周期偏差"])
        self._result_table.setSelectionBehavior(QAbstractItemView.SelectRows); self._result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._result_table.verticalHeader().setVisible(False)
        h = self._result_table.horizontalHeader(); h.setSectionResizeMode(1, QHeaderView.Stretch); h.setSectionResizeMode(2, QHeaderView.Stretch)
        self._result_table.itemSelectionChanged.connect(self._on_result_selected)
        right_splitter.addWidget(self._plot); right_splitter.addWidget(self._result_table); layout.addWidget(right_splitter, 1)
        self._on_source_changed(0)

    def set_imported_signals(self, signals):
        self._imported_signals = signals or []
        periods = np.linspace(0.04, 6.0, 200)
        recs = []
        for i, sig in enumerate(self._imported_signals, 1):
            sa = Spectra.compute(sig.acc, sig.dt, periods, 0.05).sa
            recs.append(PeerRecord(
                rsn=900000 + i,
                event="Imported", station=sig.name or f"Signal_{i}", component="IMP", direction='H',
                dt=sig.dt, npts=sig.n, pga=float(sig.pga), duration=float(sig.duration),
                eff_duration=float(sig.effective_duration), sa=sa, acc=sig.acc.copy(),
            ))
        self._imported_db.records = recs
        self._imported_db._spectra_periods = periods
        if self._source_combo.currentIndex() == 1:
            self._db_label.setText(f"导入候选库：{len(recs)} 条")

    def _on_source_changed(self, idx):
        self._db_group.setEnabled(idx == 0)
        if idx == 1:
            self._db_label.setText(f"导入候选库：{len(self._imported_signals)} 条")

    def _browse_db(self):
        d = QFileDialog.getExistingDirectory(self, "选择 PEER 数据目录")
        if d: self._dir_edit.setText(d)

    def _load_database(self):
        d = self._dir_edit.text()
        if not d:
            QMessageBox.warning(self, "警告", "请先选择 PEER 数据目录"); return
        self._load_btn.setEnabled(False); self._progress_bar.setVisible(True); self._progress_bar.setRange(0, 0)
        self._worker = PeerLoadWorker(d, parent=self)
        self._worker.signals.progress.connect(lambda p, m: (self._progress_bar.setRange(0,100), self._progress_bar.setValue(p), self._db_label.setText(m)))
        self._worker.signals.finished.connect(self._on_load_done)
        self._worker.signals.error.connect(lambda e: QMessageBox.critical(self, "错误", e))
        self._worker.start()

    def _on_load_done(self, db):
        self._db = db; self._load_btn.setEnabled(True); self._progress_bar.setVisible(False)
        self._db_label.setText(f"已加载: {len(db)} 条记录")

    def set_code_spectrum(self, periods, sa):
        self._code_periods = np.asarray(periods); self._code_sa = np.asarray(sa)

    def _run_selection(self):
        if self._code_sa is None:
            QMessageBox.warning(self, "警告", "请先设置规范谱参数"); return
        db = self._db if self._source_combo.currentIndex() == 0 else self._imported_db
        if len(db) == 0:
            QMessageBox.warning(self, "警告", "当前数据源无候选记录"); return
        T_main = [self._t1_spin.value(), self._t2_spin.value(), self._t3_spin.value()]
        db_periods = db.spectra_periods
        from scipy.interpolate import interp1d
        target_sa = np.maximum(interp1d(self._code_periods, self._code_sa, kind='linear', fill_value='extrapolate')(db_periods), 0.0)
        config = SelectionConfig(target_sa=target_sa, periods=db_periods, T_main=T_main, n_select=self._n_select_spin.value(),
                                 duration_factor=self._dur_factor_spin.value(), spectral_tol=self._tol_spin.value(),
                                 scale_range=(self._scale_lo_spin.value(), self._scale_hi_spin.value()))
        self._run_btn.setEnabled(False); self._stat_label.setText("选波计算中...")
        self._worker = PeerSelectWorker(config, db, parent=self)
        self._worker.signals.finished.connect(self._on_selection_done)
        self._worker.signals.error.connect(self._on_selection_error)
        self._worker.start()

    def _on_selection_done(self, results):
        self._results = results; self._run_btn.setEnabled(True)
        self._result_table.setRowCount(len(results))
        for i, r in enumerate(results):
            rec = r.record
            vals = [str(rec.rsn), rec.event, rec.station, rec.component, f"{r.scale_factor:.2f}", f"{r.match_error:.4f}", ", ".join(f"{v:.0%}" for v in r.deviations.values())]
            for j, v in enumerate(vals): self._result_table.setItem(i, j, QTableWidgetItem(v))
        self._stat_label.setText(f"选中 {len(results)} 条地震波")
        self._plot_results(); self.selection_done.emit(results)

    def _on_selection_error(self, err):
        self._run_btn.setEnabled(True); self._stat_label.setText(f"选波出错: {err}")
        QMessageBox.critical(self, "错误", f"选波失败:\n{err}")

    def _plot_results(self):
        if not self._results or self._code_sa is None: return
        db = self._db if self._source_combo.currentIndex() == 0 else self._imported_db
        db_periods = db.spectra_periods
        self._plot.clear(); c = get_mpl_colors(self._dark); self._plot.plot_code_spectrum(self._code_periods, self._code_sa)
        sa_list = []
        for i, r in enumerate(self._results):
            scaled = r.record.sa * r.scale_factor; sa_list.append(scaled)
            self._plot.ax.plot(db_periods, scaled, color=c['palette'][i % len(c['palette'])], linewidth=1.2, alpha=0.8)
        if len(sa_list) > 1: self._plot.ax.plot(db_periods, np.mean(sa_list, axis=0), label="均值谱", color=c['fg'], linewidth=2.0, linestyle='-.')
        self._plot.plot_envelope(self._code_periods, self._code_sa); self._plot.refresh()

    def _on_result_selected(self):
        pass

    def get_results(self): return self._results

    def get_database(self):
        return self._db if self._source_combo.currentIndex() == 0 else self._imported_db

    def set_dark(self, dark: bool):
        self._dark = dark; self._plot.set_dark(dark)
