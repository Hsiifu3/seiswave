"""
SeisWave 主窗口

左侧：全局设置（规范谱 + 结构周期）
中央：Tab 工作区（选波 / 人工波 / 信号处理）
底部：共享反应谱对比图
"""

import sys
import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QToolBar, QStatusBar, QMenuBar, QMenu, QMessageBox, QFileDialog,
    QSplitter, QTabWidget, QDockWidget, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence

from seiswave.gui.styles import get_theme
from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar
from seiswave.gui.panels.selector_panel import SelectorPanel
from seiswave.gui.panels.generator_panel import GeneratorPanel
from seiswave.gui.panels.signal_panel import SignalPanel
from seiswave.gui.panels.import_panel import ImportPanel
from seiswave.gui.panels.result_panel import ResultPanel
from seiswave.gui.widgets.spectrum_plot import SpectrumPlot
from seiswave.gui.styles import get_mpl_colors


class MainWindow(QMainWindow):
    """SeisWave 主窗口"""

    def __init__(self):
        super().__init__()
        self._dark = False
        self.setWindowTitle("SeisWave — 地震波选取与生成工具")
        self.setMinimumSize(1200, 800)
        self.resize(1440, 920)

        self._setup_sidebar()
        self._setup_central()
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()
        self._apply_theme()

        # 初始化：触发一次规范谱计算
        self._sidebar.trigger_update()

    # ──────────── 布局 ────────────

    def _setup_sidebar(self):
        """左侧全局设置面板（规范谱参数）"""
        self._sidebar = SpectrumSidebar(dark=self._dark)

        dock = QDockWidget("设防参数", self)
        dock.setWidget(self._sidebar)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        dock.setFixedWidth(300)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self._sidebar_dock = dock

    def _setup_central(self):
        """中央区域：上方 Tab 工作区 + 下方共享反应谱图"""
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Vertical)

        # 上方：Tab 工作区
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._import_panel = ImportPanel(dark=self._dark)
        self._selector_panel = SelectorPanel(dark=self._dark)
        self._generator_panel = GeneratorPanel(dark=self._dark)
        self._signal_panel = SignalPanel(dark=self._dark)
        self._result_panel = ResultPanel(dark=self._dark)

        self._tabs.addTab(self._import_panel, "📂 导入")
        self._tabs.addTab(self._selector_panel, "🔍 选波")
        self._tabs.addTab(self._generator_panel, "🌊 人工波")
        self._tabs.addTab(self._signal_panel, "⚙ 信号处理")
        self._tabs.addTab(self._result_panel, "📤 导出")

        splitter.addWidget(self._tabs)

        # 下方：共享反应谱对比图
        self._shared_plot = SpectrumPlot(dark=self._dark, log_x=False,
                                         show_toolbar=True, compact_toolbar=True)
        self._shared_plot.setMinimumHeight(150)
        splitter.addWidget(self._shared_plot)

        splitter.setSizes([600, 280])
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter)

    def _setup_menubar(self):
        menubar = self.menuBar()

        # 文件
        file_menu = menubar.addMenu("文件(&F)")

        import_action = QAction("导入地震动(&I)...", self)
        import_action.setShortcut(QKeySequence("Ctrl+I"))
        import_action.triggered.connect(lambda: self._tabs.setCurrentIndex(0))
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        export_action = QAction("导出结果(&E)...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(lambda: self._tabs.setCurrentIndex(4))
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction("退出(&Q)", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # 视图
        view_menu = menubar.addMenu("视图(&V)")

        self._theme_action = QAction("深色主题(&D)", self)
        self._theme_action.setCheckable(True)
        self._theme_action.setChecked(False)
        self._theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._theme_action)

        # 帮助
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        toolbar = QToolBar("快捷操作")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        tabs = [
            ("📂 导入", 0), ("🔍 选波", 1), ("🌊 人工波", 2),
            ("⚙ 信号处理", 3), ("📤 导出", 4),
        ]
        for label, idx in tabs:
            action = QAction(label, self)
            action.triggered.connect(lambda checked, i=idx: self._tabs.setCurrentIndex(i))
            toolbar.addAction(action)

    def _setup_statusbar(self):
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("就绪")

    # ──────────── 信号连接 ────────────

    def _connect_signals(self):
        # 规范谱变化 → 更新所有面板 + 共享图
        self._sidebar.spectrum_changed.connect(self._on_spectrum_changed)

        # 导入完成
        self._import_panel.signals_loaded.connect(self._on_signals_loaded)

        # 选波完成 → 更新共享图 + 导出面板
        self._selector_panel.selection_done.connect(self._on_selection_done)

        # 人工波生成完成 → 更新共享图 + 导出面板
        self._generator_panel.wave_generated.connect(self._on_wave_generated)

        # 导入面板双击 → 跳转信号处理
        self._import_panel._table.wave_double_clicked.connect(self._on_wave_double_clicked)

        # Tab 切换时更新状态栏
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _on_spectrum_changed(self, periods, sa):
        """规范谱更新：刷新所有依赖面板 + 共享图"""
        self._selector_panel.set_code_spectrum(periods, sa)
        self._generator_panel.set_code_spectrum(periods, sa)
        self._result_panel.set_code_spectrum(periods, sa)

        # 更新共享反应谱图
        self._refresh_shared_plot(periods, sa)
        self._statusbar.showMessage("规范谱已更新")

    def _refresh_shared_plot(self, periods=None, sa=None):
        """刷新底部共享反应谱对比图"""
        self._shared_plot.clear()
        colors = get_mpl_colors(self._dark)

        if periods is not None and sa is not None:
            self._shared_plot.plot_code_spectrum(periods, sa, label="规范谱")
            self._shared_plot.plot_envelope(periods, sa)

        # 叠加选波结果
        if hasattr(self, '_selection_spectra'):
            palette = colors['palette']
            for i, (label, p, s) in enumerate(self._selection_spectra):
                self._shared_plot.ax.plot(
                    p, s, label=label,
                    color=palette[i % len(palette)],
                    linewidth=1.2, alpha=0.8)

        # 叠加人工波反应谱
        if hasattr(self, '_generated_spectra'):
            for i, (label, p, s) in enumerate(self._generated_spectra):
                self._shared_plot.ax.plot(
                    p, s, label=label,
                    color=colors['accent'], linewidth=1.5,
                    linestyle='--', alpha=0.9)

        # 均值谱
        all_sa = []
        if hasattr(self, '_selection_spectra'):
            all_sa.extend([s for _, _, s in self._selection_spectra])
        if hasattr(self, '_generated_spectra'):
            all_sa.extend([s for _, _, s in self._generated_spectra])
        if len(all_sa) > 1 and periods is not None:
            # 需要统一周期轴，这里简化处理
            pass

        self._shared_plot.ax.legend(fontsize=8, framealpha=0.8, loc='upper right')
        self._shared_plot.ax.set_title("反应谱总览", fontsize=11)
        self._shared_plot.refresh()

    def _on_signals_loaded(self, signals):
        self._statusbar.showMessage(f"已加载 {len(signals)} 条地震波")

    def _on_selection_done(self, results):
        """选波完成：缓存反应谱数据，刷新共享图"""
        db = self._selector_panel.get_database()
        self._result_panel.set_results(results, database=db)

        # 缓存选波反应谱用于共享图
        self._selection_spectra = []
        db_periods = db.spectra_periods if db else None
        if db_periods is not None:
            for r in results:
                scaled_sa = r.record.sa * r.scale_factor
                label = f"RSN{r.record.rsn} ({r.scale_factor:.2f}x)"
                self._selection_spectra.append((label, db_periods, scaled_sa))

        periods, sa = self._sidebar.get_spectrum()
        self._refresh_shared_plot(periods, sa)
        self._statusbar.showMessage(f"选波完成: {len(results)} 条")

    def _on_wave_generated(self, signal):
        """人工波生成完成：缓存反应谱，刷新共享图"""
        self._result_panel.add_generated_wave(signal)

        from seiswave.core import Spectra
        periods, code_sa = self._sidebar.get_spectrum()
        if periods is not None:
            spec = Spectra.compute(signal.acc, signal.dt, periods, 0.05)
            label = f"人工波 (PGA={signal.pga:.3f}g)"
            if not hasattr(self, '_generated_spectra'):
                self._generated_spectra = []
            self._generated_spectra.append((label, periods, spec.sa))
            self._refresh_shared_plot(periods, code_sa)

        self._statusbar.showMessage(f"人工波已生成: PGA = {signal.pga:.4f} g")

    def _on_wave_double_clicked(self, row):
        sig = self._import_panel._table.get_signal(row)
        if sig:
            self._signal_panel.set_signal(sig)
            self._tabs.setCurrentIndex(3)

    def _on_tab_changed(self, index):
        names = ["数据导入", "选波", "人工波生成", "信号处理", "导出与报告"]
        if 0 <= index < len(names):
            self._statusbar.showMessage(f"当前: {names[index]}")

    # ──────────── 主题 ────────────

    def _toggle_theme(self):
        self._dark = self._theme_action.isChecked()
        self._apply_theme()
        for panel in [self._sidebar, self._import_panel, self._selector_panel,
                       self._generator_panel, self._signal_panel, self._result_panel]:
            panel.set_dark(self._dark)
        self._shared_plot.set_dark(self._dark)
        # 刷新共享图
        periods, sa = self._sidebar.get_spectrum()
        if periods is not None:
            self._refresh_shared_plot(periods, sa)

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(get_theme(self._dark))

    def _show_about(self):
        QMessageBox.about(
            self,
            "关于 SeisWave",
            "<h3>SeisWave v2.0</h3>"
            "<p>地震波选取与生成工具</p>"
            "<p>功能：</p>"
            "<ul>"
            "<li>GB 50011 / EC8 / ASCE 7 规范反应谱</li>"
            "<li>PEER NGA 数据库选波</li>"
            "<li>迭代谱拟合人工波生成</li>"
            "<li>基线校正与 Butterworth 滤波</li>"
            "<li>组合导出（天然 + 人工）</li>"
            "</ul>"
        )
