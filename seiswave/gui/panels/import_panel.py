"""
数据导入面板

目录选择、文件列表、预览时程曲线、PGA/持时信息显示。
"""

import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QFileDialog, QLineEdit, QComboBox, QFormLayout,
    QSplitter, QMessageBox,
)
from PySide6.QtCore import Signal, Qt

from seiswave.core import FileIO, EQSignal
from seiswave.gui.widgets.wave_table import WaveTable
from seiswave.gui.widgets.plot_widget import PlotWidget
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
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("选择地震动文件目录...")
        self._dir_edit.setReadOnly(True)
        dir_layout.addWidget(self._dir_edit)

        self._browse_btn = QPushButton("浏览...")
        self._browse_btn.setProperty("secondary", True)
        self._browse_btn.clicked.connect(self._browse_directory)
        dir_layout.addWidget(self._browse_btn)

        self._format_combo = QComboBox()
        self._format_combo.addItems(["AT2 (*.AT2)", "TXT 单列 (*.txt)", "TXT 双列 (*.txt)", "CSV (*.csv)"])
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

        self._plot = PlotWidget(dark=self._dark)
        preview_layout.addWidget(self._plot)

        # 信息栏
        self._info_label = QLabel("选择地震波以预览时程曲线")
        self._info_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self._info_label)

        splitter.addWidget(preview_widget)
        splitter.setSizes([300, 400])

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
        """加载地震动文件"""
        dir_path = self._dir_edit.text()
        if not dir_path or not os.path.isdir(dir_path):
            QMessageBox.warning(self, "警告", "请先选择有效的数据目录")
            return

        fmt_idx = self._format_combo.currentIndex()
        pattern_map = {0: "*.AT2", 1: "*.txt", 2: "*.txt", 3: "*.csv"}
        pattern = pattern_map[fmt_idx]

        try:
            import glob
            files = sorted(glob.glob(os.path.join(dir_path, pattern)))
            if not files:
                # 尝试小写扩展名
                pattern_lower = pattern.lower()
                files = sorted(glob.glob(os.path.join(dir_path, pattern_lower)))

            if not files:
                QMessageBox.information(self, "提示", f"目录中未找到 {pattern} 文件")
                return

            signals = []
            for f in files:
                try:
                    if fmt_idx == 0:  # AT2
                        sig = EQSignal.from_at2(f)
                    else:
                        # txt/csv 需要 dt，默认 0.02
                        sig = EQSignal.from_txt(f, dt=0.02,
                                                single_col=(fmt_idx == 1))
                    signals.append(sig)
                except Exception:
                    continue  # 跳过无法解析的文件

            self._signals = signals
            self._table.load_signals(signals)
            self._count_label.setText(f"已加载: {len(signals)} 条")
            self.signals_loaded.emit(signals)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载失败: {e}")

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
