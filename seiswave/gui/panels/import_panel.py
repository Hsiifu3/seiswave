"""
数据导入面板

目录选择、文件列表、预览时程曲线、PGA/持时信息显示。
"""

import os
import glob
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFileDialog, QLineEdit, QComboBox,
    QSplitter, QMessageBox,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core import EQSignal
from seiswave.gui.widgets.wave_table import WaveTable
from seiswave.gui.widgets.plot_widget import PlotWidget
from seiswave.gui.widgets.progress_dialog import ProgressDialog
from seiswave.gui.workers import FileLoadWorker
from seiswave.gui.styles import get_mpl_colors


class ImportPanel(QWidget):
    """数据导入面板"""

    signals_loaded = Signal(list)  # 加载完成信号

    def __init__(self, parent=None, dark=False):
        super().__init__(parent)
        self._dark = dark
        self._signals = []
        self._current_dir = ""
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 顶部：目录选择
        dir_group = QGroupBox("数据目录")
        dir_layout = QHBoxLayout(dir_group)
        dir_layout.setSpacing(4)
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择地震动文件目录...")
        self._dir_edit.setReadOnly(True)
        dir_layout.addWidget(self._dir_edit, 1)

        self._browse_btn = QPushButton("浏览...")
        self._browse_btn.setProperty("secondary", True)
        self._browse_btn.clicked.connect(self._browse_directory)
        dir_layout.addWidget(self._browse_btn)

        self._format_combo = QComboBox()
        self._format_combo.addItems([
            "AT2 (*.AT2)", "TXT 单列 (*.txt)", "TXT 双列 (*.txt)", "CSV (*.csv)",
        ])
        self._format_combo.setMinimumWidth(140)
        dir_layout.addWidget(self._format_combo)

        self._load_btn = QPushButton("加载")
        self._load_btn.clicked.connect(self._load_files)
        dir_layout.addWidget(self._load_btn)

        layout.addWidget(dir_group)

        # 中间：分割器（表格 + 预览图）
        splitter = QSplitter(Qt.Vertical)

        # 文件列表表格
        self._table = WaveTable()
        self._table.wave_selected.connect(self._on_wave_selected)
        splitter.addWidget(self._table)

        # 预览区
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        self._plot = PlotWidget(dark=self._dark, show_toolbar=False)
        preview_layout.addWidget(self._plot)

        # 信息栏
        self._info_label = QLabel("选择地震波以预览时程曲线")
        self._info_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self._info_label)

        splitter.addWidget(preview_widget)
        splitter.setSizes([280, 420])
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        layout.addWidget(splitter)

        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._clear_btn = QPushButton("清空")
        self._clear_btn.setProperty("secondary", True)
        self._clear_btn.clicked.connect(self._clear_all)
        btn_layout.addWidget(self._clear_btn)

        self._count_label = QLabel("已加载: 0 条")
        btn_layout.addWidget(self._count_label)

        layout.addLayout(btn_layout)

    def _browse_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择地震动文件目录")
        if dir_path:
            self._dir_edit.setText(dir_path)
            self._current_dir = dir_path

    def _load_files(self):
        """加载地震动文件（后台线程 + 进度条）"""
        dir_path = self._dir_edit.text()
        if not dir_path or not os.path.isdir(dir_path):
            QMessageBox.warning(self, "警告", "请先选择有效的数据目录")
            return

        fmt_idx = self._format_combo.currentIndex()
        pattern_map = {0: "*.AT2", 1: "*.txt", 2: "*.txt", 3: "*.csv"}
        pattern = pattern_map[fmt_idx]

        files = sorted(glob.glob(os.path.join(dir_path, pattern)))
        if not files:
            files = sorted(glob.glob(os.path.join(dir_path, pattern.lower())))
        if not files:
            QMessageBox.information(self, "提示", f"目录中未找到 {pattern} 文件")
            return

        # 创建进度对话框
        self._progress_dlg = ProgressDialog("加载地震动文件...", self)

        # 创建后台 worker
        self._load_worker = FileLoadWorker(files, fmt_idx, parent=self)
        self._load_worker.signals.progress.connect(self._progress_dlg.update_progress)
        self._load_worker.signals.finished.connect(self._on_load_finished)
        self._load_worker.signals.error.connect(self._on_load_error)
        self._progress_dlg.cancelled.connect(self._load_worker.cancel)

        # 禁用加载按钮防止重复点击
        self._load_btn.setEnabled(False)

        self._load_worker.start()
        self._progress_dlg.exec()

    def _on_load_finished(self, signals):
        """文件加载完成回调"""
        self._signals = signals
        self._table.load_signals(signals)
        self._count_label.setText(f"已加载: {len(signals)} 条")
        self._load_btn.setEnabled(True)
        # 先关闭进度对话框，再发射信号（避免在模态对话框中触发重计算）
        if hasattr(self, '_progress_dlg') and self._progress_dlg.isVisible():
            self._progress_dlg.accept()
        self.signals_loaded.emit(signals)

    def _on_load_error(self, error_msg):
        """文件加载出错回调"""
        self._load_btn.setEnabled(True)
        if hasattr(self, '_progress_dlg') and self._progress_dlg.isVisible():
            self._progress_dlg.reject()
        QMessageBox.critical(self, "错误", f"加载失败: {error_msg}")

    def _on_wave_selected(self, row):
        """选中地震波时预览"""
        sig = self._table.get_signal(row)
        if sig is None:
            return

        colors = get_mpl_colors(self._dark)
        self._plot.clear()
        ax = self._plot.ax
        ax.plot(sig.time, sig.acc, color=colors['primary'], linewidth=0.6)
        ax.set_xlabel("时间 (s)")
        ax.set_ylabel("加速度 (g)")
        ax.set_title(sig.name or f"Wave {row+1}", fontsize=11)
        self._plot.refresh()

        self._info_label.setText(
            f"PGA = {sig.pga:.4f} g  |  "
            f"持时 = {sig.duration:.2f} s  |  "
            f"有效持时 = {sig.effective_duration:.2f} s  |  "
            f"Δt = {sig.dt:.4f} s  |  "
            f"N = {sig.n}"
        )

    def _clear_all(self):
        self._signals = []
        self._table.clear_all()
        self._plot.clear()
        self._plot.refresh()
        self._info_label.setText("选择地震波以预览时程曲线")
        self._count_label.setText("已加载: 0 条")

    def get_signals(self):
        """获取已加载的地震波列表"""
        return self._signals

    def set_dark(self, dark: bool):
        self._dark = dark
        self._plot.set_dark(dark)
