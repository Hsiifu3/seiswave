"""
SeisWave 主窗口

菜单栏、工具栏、左侧参数面板切换、中央绘图区、底部状态栏。
"""

import sys
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QStackedWidget, QToolBar,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QActionGroup, QKeySequence

from seiswave.gui.styles import get_theme
from seiswave.gui.panels.spectrum_panel import SpectrumPanel
from seiswave.gui.panels.import_panel import ImportPanel
from seiswave.gui.panels.selector_panel import SelectorPanel
from seiswave.gui.panels.generator_panel import GeneratorPanel
from seiswave.gui.panels.signal_panel import SignalPanel
from seiswave.gui.panels.result_panel import ResultPanel


class MainWindow(QMainWindow):
    """SeisWave 主窗口"""

    def __init__(self):
        super().__init__()
        self._dark = False
        self.setWindowTitle("SeisWave v2 - 地震信号处理与选波工具")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        self._setup_panels()
        self._setup_menubar()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_panels()
        self._apply_theme()

        # 默认显示规范谱面板
        self._switch_panel(0)

    def _setup_panels(self):
        """创建所有面板并放入 StackedWidget"""
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        self._spectrum_panel = SpectrumPanel(dark=self._dark)
        self._import_panel = ImportPanel(dark=self._dark)
        self._selector_panel = SelectorPanel(dark=self._dark)
        self._generator_panel = GeneratorPanel(dark=self._dark)
        self._signal_panel = SignalPanel(dark=self._dark)
        self._result_panel = ResultPanel(dark=self._dark)

        self._stack.addWidget(self._spectrum_panel)   # 0
        self._stack.addWidget(self._import_panel)      # 1
        self._stack.addWidget(self._selector_panel)    # 2
        self._stack.addWidget(self._generator_panel)   # 3
        self._stack.addWidget(self._signal_panel)      # 4
        self._stack.addWidget(self._result_panel)      # 5

    def _setup_menubar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件(&F)")

        import_action = QAction("导入地震动(&I)...", self)
        import_action.setShortcut(QKeySequence("Ctrl+I"))
        import_action.triggered.connect(lambda: self._switch_panel(1))
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        export_action = QAction("导出结果(&E)...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(lambda: self._switch_panel(5))
        file_menu.addAction(export_action)

        file_menu.addSeparator()

        quit_action = QAction("退出(&Q)", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        # 计算菜单
        calc_menu = menubar.addMenu("计算(&C)")

        spectrum_action = QAction("规范谱设置(&S)", self)
        spectrum_action.triggered.connect(lambda: self._switch_panel(0))
        calc_menu.addAction(spectrum_action)

        select_action = QAction("选波(&W)", self)
        select_action.triggered.connect(lambda: self._switch_panel(2))
        calc_menu.addAction(select_action)

        generate_action = QAction("人工波生成(&G)", self)
        generate_action.triggered.connect(lambda: self._switch_panel(3))
        calc_menu.addAction(generate_action)

        signal_action = QAction("信号处理(&P)", self)
        signal_action.triggered.connect(lambda: self._switch_panel(4))
        calc_menu.addAction(signal_action)

        # 视图菜单
        view_menu = menubar.addMenu("视图(&V)")

        self._theme_action = QAction("深色主题(&D)", self)
        self._theme_action.setCheckable(True)
        self._theme_action.setChecked(False)
        self._theme_action.triggered.connect(self._toggle_theme)
        view_menu.addAction(self._theme_action)

        # 帮助菜单
        help_menu = menubar.addMenu("帮助(&H)")

        about_action = QAction("关于(&A)", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _setup_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))
        self.addToolBar(toolbar)

        self._panel_actions = QActionGroup(self)
        self._panel_actions.setExclusive(True)

        panels = [
            ("📊 规范谱", 0),
            ("📂 导入", 1),
            ("🔍 选波", 2),
            ("🌊 人工波", 3),
            ("⚙ 信号处理", 4),
            ("📤 导出", 5),
        ]

        for label, idx in panels:
            action = QAction(label, self)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, i=idx: self._switch_panel(i))
            self._panel_actions.addAction(action)
            toolbar.addAction(action)

        # 默认选中第一个
        self._panel_actions.actions()[0].setChecked(True)

    def _setup_statusbar(self):
        """创建状态栏"""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("就绪")

    def _connect_panels(self):
        """连接面板间的信号"""
        # 规范谱变化 → 更新选波面板和人工波面板的目标谱
        self._spectrum_panel.spectrum_changed.connect(self._on_spectrum_changed)

        # 导入完成 → 更新选波面板的地震波列表
        self._import_panel.signals_loaded.connect(self._on_signals_loaded)

        # 选波完成 → 更新导出面板
        self._selector_panel.selection_done.connect(self._on_selection_done)

        # 人工波生成完成 → 更新导出面板
        self._generator_panel.wave_generated.connect(self._on_wave_generated)

        # 导入面板双击 → 跳转信号处理
        self._import_panel._table.wave_double_clicked.connect(self._on_wave_double_clicked)

    def _on_spectrum_changed(self, periods, sa):
        self._selector_panel.set_code_spectrum(periods, sa)
        self._generator_panel.set_code_spectrum(periods, sa)
        self._result_panel.set_code_spectrum(periods, sa)
        self._statusbar.showMessage("规范谱已更新")

    def _on_signals_loaded(self, signals):
        self._selector_panel.set_signals(signals)
        self._statusbar.showMessage(f"已加载 {len(signals)} 条地震波")

    def _on_selection_done(self, results):
        self._result_panel.set_results(results)
        passed = sum(1 for r in results if r.passed)
        self._statusbar.showMessage(f"选波完成: {passed}/{len(results)} 条通过")

    def _on_wave_generated(self, signal):
        self._result_panel.add_generated_wave(signal)
        self._statusbar.showMessage(f"人工波已生成: PGA = {signal.pga:.4f} g")

    def _on_wave_double_clicked(self, row):
        sig = self._import_panel._table.get_signal(row)
        if sig:
            self._signal_panel.set_signal(sig)
            self._switch_panel(4)

    def _switch_panel(self, index):
        """切换面板"""
        self._stack.setCurrentIndex(index)
        actions = self._panel_actions.actions()
        if 0 <= index < len(actions):
            actions[index].setChecked(True)
        panel_names = ["规范谱设置", "数据导入", "选波", "人工波生成", "信号处理", "导出与报告"]
        if 0 <= index < len(panel_names):
            self._statusbar.showMessage(f"当前: {panel_names[index]}")

    def _toggle_theme(self):
        self._dark = self._theme_action.isChecked()
        self._apply_theme()
        # 更新所有面板主题
        for panel in [self._spectrum_panel, self._import_panel,
                       self._selector_panel, self._generator_panel,
                       self._signal_panel, self._result_panel]:
            panel.set_dark(self._dark)

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(get_theme(self._dark))

    def _show_about(self):
        QMessageBox.about(
            self,
            "关于 SeisWave",
            "<h3>SeisWave v2.0</h3>"
            "<p>地震信号处理与选波工具包</p>"
            "<p>基于 EQSignal C++ 和 MATLAB 选波程序重写</p>"
            "<p>核心功能：</p>"
            "<ul>"
            "<li>GB 50011 规范反应谱</li>"
            "<li>Newmark-β / 频域反应谱计算</li>"
            "<li>三步法地震波选取</li>"
            "<li>迭代谱拟合人工波生成</li>"
            "<li>基线校正与滤波</li>"
            "</ul>"
        )
