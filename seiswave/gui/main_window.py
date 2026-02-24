import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QStatusBar, QMessageBox, QPushButton, QLabel, QStackedWidget,
    QSplitter, QDockWidget, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QFont

from seiswave.gui.styles import get_theme, get_mpl_colors
from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar
from seiswave.gui.panels.selector_panel import SelectorPanel
from seiswave.gui.panels.generator_panel import GeneratorPanel
from seiswave.gui.panels.signal_panel import SignalPanel
from seiswave.gui.panels.import_panel import ImportPanel
from seiswave.gui.panels.result_panel import ResultPanel
from seiswave.gui.panels.summary_panel import SummaryPanel
from seiswave.gui.panels.combine_panel import CombinePanel
from seiswave.gui.widgets.spectrum_plot import SpectrumPlot

# 向导步骤定义
WIZARD_STEPS = [
    {"label": "规范谱", "icon": "1"},
    {"label": "选波", "icon": "2"},
    {"label": "生成", "icon": "3"},
    {"label": "组合", "icon": "4"},
]


class _StepIndicator(QFrame):
    """向导步骤指示条"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = 0
        self._labels: list[QLabel] = []
        self._connectors: list[QFrame] = []
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(0)
        for i, step in enumerate(WIZARD_STEPS):
            if i > 0:
                conn = QFrame()
                conn.setFixedHeight(2)
                conn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                conn.setObjectName("stepConnector")
                layout.addWidget(conn)
                self._connectors.append(conn)
            lbl = QLabel(f"  {step['icon']}. {step['label']}  ")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setObjectName("stepLabel")
            lbl.setFont(QFont("", 11))
            layout.addWidget(lbl)
            self._labels.append(lbl)
        self.set_step(0)

    def set_step(self, index: int):
        self._current = index
        for i, lbl in enumerate(self._labels):
            if i < index:
                lbl.setProperty("state", "done")
            elif i == index:
                lbl.setProperty("state", "active")
            else:
                lbl.setProperty("state", "pending")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)
        for i, conn in enumerate(self._connectors):
            conn.setProperty("state", "done" if i < index else "pending")
            conn.style().unpolish(conn)
            conn.style().polish(conn)


_STEP_STYLE = """
#stepLabel[state="active"] {
    background: #2196F3; color: white; border-radius: 4px;
    padding: 4px 8px; font-weight: bold;
}
#stepLabel[state="done"] {
    background: #4CAF50; color: white; border-radius: 4px;
    padding: 4px 8px;
}
#stepLabel[state="pending"] {
    background: #e0e0e0; color: #888; border-radius: 4px;
    padding: 4px 8px;
}
#stepConnector[state="done"] { background: #4CAF50; }
#stepConnector[state="pending"] { background: #e0e0e0; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._dark = False
        self.setWindowTitle("SeisWave — 地震波选取与生成工具")
        self.setMinimumSize(1200, 800)
        self.resize(1440, 920)
        self._selection_spectra = []
        self._generated_spectra = []
        self._current_step = 0
        self._setup_sidebar()
        self._setup_central()
        self._setup_menubar()
        self._setup_statusbar()
        self._connect_signals()
        self._apply_theme()
        self._sidebar.trigger_update()

    # ── sidebar ──

    def _setup_sidebar(self):
        self._sidebar = SpectrumSidebar(dark=self._dark)
        dock = QDockWidget("设防参数", self)
        dock.setWidget(self._sidebar)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock)
        self._sidebar_dock = dock

    # ── central: step indicator + stacked panels + nav buttons ──

    def _setup_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Step indicator bar
        self._step_indicator = _StepIndicator()
        self._step_indicator.setStyleSheet(_STEP_STYLE)
        root.addWidget(self._step_indicator)

        # Main splitter (panels + shared plot)
        splitter = QSplitter(Qt.Vertical)

        # Stacked widget for wizard panels
        self._stack = QStackedWidget()
        self._import_panel = ImportPanel(dark=self._dark)
        self._selector_panel = SelectorPanel(dark=self._dark)
        self._generator_panel = GeneratorPanel(dark=self._dark)
        self._signal_panel = SignalPanel(dark=self._dark)
        self._summary_panel = SummaryPanel(dark=self._dark)
        self._result_panel = ResultPanel(dark=self._dark)
        self._combine_panel = CombinePanel(dark=self._dark)

        # Step 0: 规范谱 → import + spectrum sidebar (sidebar is dock)
        self._stack.addWidget(self._import_panel)
        # Step 1: 选波
        self._stack.addWidget(self._selector_panel)
        # Step 2: 生成 (artificial wave)
        self._stack.addWidget(self._generator_panel)
        # Step 3: 组合 (combine + summary + result)
        step3 = QWidget()
        s3_layout = QVBoxLayout(step3)
        s3_layout.setContentsMargins(0, 0, 0, 0)
        s3_layout.addWidget(self._combine_panel, 3)
        s3_layout.addWidget(self._summary_panel, 1)
        s3_layout.addWidget(self._result_panel, 2)
        self._stack.addWidget(step3)

        splitter.addWidget(self._stack)

        # Shared spectrum plot
        self._shared_plot = SpectrumPlot(dark=self._dark, log_x=False)
        self._shared_plot.setMinimumHeight(150)
        splitter.addWidget(self._shared_plot)
        splitter.setSizes([600, 280])
        root.addWidget(splitter, 1)

        # Navigation buttons
        nav = QHBoxLayout()
        nav.setContentsMargins(12, 6, 12, 6)
        self._btn_prev = QPushButton("← 上一步")
        self._btn_next = QPushButton("下一步 →")
        self._btn_prev.setFixedWidth(120)
        self._btn_next.setFixedWidth(120)
        nav.addWidget(self._btn_prev)
        nav.addStretch()
        self._nav_label = QLabel("")
        self._nav_label.setAlignment(Qt.AlignCenter)
        nav.addWidget(self._nav_label)
        nav.addStretch()
        nav.addWidget(self._btn_next)
        root.addLayout(nav)

        self._btn_prev.clicked.connect(self._go_prev)
        self._btn_next.clicked.connect(self._go_next)
        self._update_nav()
    # ── wizard navigation ──

    def _go_prev(self):
        if self._current_step > 0:
            self._set_step(self._current_step - 1)

    def _go_next(self):
        if self._current_step < len(WIZARD_STEPS) - 1:
            self._set_step(self._current_step + 1)

    def _set_step(self, index: int):
        self._current_step = index
        self._stack.setCurrentIndex(index)
        self._step_indicator.set_step(index)
        self._update_nav()
        names = ["规范谱 / 导入", "选波", "人工波生成", "组合 / 导出"]
        if 0 <= index < len(names):
            self._statusbar.showMessage(f"步骤 {index + 1}: {names[index]}")

    def _update_nav(self):
        step = self._current_step
        self._btn_prev.setEnabled(step > 0)
        self._btn_next.setEnabled(step < len(WIZARD_STEPS) - 1)
        self._nav_label.setText(
            f"步骤 {step + 1} / {len(WIZARD_STEPS)}: "
            f"{WIZARD_STEPS[step]['label']}")

    # ── menubar ──

    def _setup_menubar(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件(&F)")
        import_action = QAction("导入地震动(&I)...", self)
        import_action.setShortcut(QKeySequence("Ctrl+I"))
        import_action.triggered.connect(lambda: self._set_step(0))
        file_menu.addAction(import_action)
        export_action = QAction("导出结果(&E)...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(lambda: self._set_step(3))
        file_menu.addAction(export_action)

    def _setup_statusbar(self):
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._statusbar.showMessage("就绪")

    # ── signal wiring ──

    def _connect_signals(self):
        self._sidebar.spectrum_changed.connect(self._on_spectrum_changed)
        self._import_panel.signals_loaded.connect(self._on_signals_loaded)
        self._selector_panel.selection_done.connect(self._on_selection_done)
        self._generator_panel.wave_generated.connect(self._on_wave_generated)
        self._import_panel._table.wave_double_clicked.connect(
            self._on_wave_double_clicked)

    def _on_spectrum_changed(self, periods, sa):
        self._selector_panel.set_code_spectrum(periods, sa)
        # 传递隔震模式信息到选波面板
        iso = self._sidebar.is_isolation_mode()
        t_before, t_after = self._sidebar.get_isolation_periods()
        T_iso = [t_before, t_after] if iso and t_before and t_after else []
        self._selector_panel.set_isolation_mode(iso, T_iso)
        self._generator_panel.set_code_spectrum(periods, sa)
        self._summary_panel.set_code_spectrum(periods, sa)
        self._result_panel.set_code_spectrum(periods, sa)
        self._combine_panel.set_code_spectrum(periods, sa)
        self._refresh_shared_plot(periods, sa)

    def _refresh_shared_plot(self, periods=None, sa=None):
        self._shared_plot.clear()
        colors = get_mpl_colors(self._dark)
        if periods is not None and sa is not None:
            self._shared_plot.plot_code_spectrum(periods, sa, label="规范谱")
            self._shared_plot.plot_envelope(periods, sa)
        for i, (label, p, s) in enumerate(self._selection_spectra):
            self._shared_plot.ax.plot(
                p, s, label=label,
                color=colors['palette'][i % len(colors['palette'])],
                linewidth=1.2, alpha=0.8)
        for (label, p, s) in self._generated_spectra:
            self._shared_plot.ax.plot(
                p, s, label=label, color=colors['accent'],
                linewidth=1.5, linestyle='--', alpha=0.9)
        self._shared_plot.refresh()

    def _on_signals_loaded(self, signals):
        self._selector_panel.set_imported_signals(signals)
        self._signal_panel.set_signal_pool(signals)
        self._statusbar.showMessage(f"已加载 {len(signals)} 条地震波")

    def _on_selection_done(self, results):
        db = self._selector_panel.get_database()
        self._result_panel.set_results(results, database=db)
        self._summary_panel.set_results(results)
        self._combine_panel.set_results(results, database=db)
        self._selection_spectra = []
        db_periods = db.spectra_periods if db else None
        if db_periods is not None:
            for r in results:
                self._selection_spectra.append(
                    (f"RSN{r.record.rsn}", db_periods,
                     r.record.sa * r.scale_factor))
        periods, sa = self._sidebar.get_spectrum()
        self._refresh_shared_plot(periods, sa)

    def _on_wave_generated(self, signal):
        self._result_panel.add_generated_wave(signal)
        self._combine_panel.add_generated_wave(signal)
        self._summary_panel.set_generated_waves(
            self._result_panel._generated_waves)
        from seiswave.core import Spectra
        periods, code_sa = self._sidebar.get_spectrum()
        if periods is not None:
            spec = Spectra.compute(signal.acc, signal.dt, periods, 0.05)
            self._generated_spectra.append(
                (f"人工波 (PGA={signal.pga:.3f}g)", periods, spec.sa))
            self._refresh_shared_plot(periods, code_sa)

    def _on_wave_double_clicked(self, row):
        sig = self._import_panel._table.get_signal(row)
        if sig:
            self._signal_panel.set_signal(sig)

    def _toggle_theme(self):
        self._dark = self._theme_action.isChecked()
        self._apply_theme()

    def _apply_theme(self):
        QApplication.instance().setStyleSheet(get_theme(self._dark))

    def _show_about(self):
        QMessageBox.about(self, "关于 SeisWave", "SeisWave")
