import numpy as np
from PySide6.QtWidgets import (
    QMainWindow, QApplication, QWidget, QVBoxLayout,
    QStatusBar, QMessageBox,
    QSplitter, QTabWidget, QDockWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence

from seiswave.gui.styles import get_theme, get_mpl_colors
from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar
from seiswave.gui.panels.selector_panel import SelectorPanel
from seiswave.gui.panels.generator_panel import GeneratorPanel
from seiswave.gui.panels.signal_panel import SignalPanel
from seiswave.gui.panels.import_panel import ImportPanel
from seiswave.gui.panels.result_panel import ResultPanel
from seiswave.gui.panels.summary_panel import SummaryPanel
from seiswave.gui.widgets.spectrum_plot import SpectrumPlot


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._dark = False
        self.setWindowTitle("SeisWave — 地震波选取与生成工具")
        self.setMinimumSize(1200, 800)
        self.resize(1440, 920)
        self._selection_spectra = []
        self._generated_spectra = []
        self._setup_sidebar(); self._setup_central(); self._setup_menubar(); self._setup_statusbar(); self._connect_signals(); self._apply_theme(); self._sidebar.trigger_update()

    def _setup_sidebar(self):
        self._sidebar = SpectrumSidebar(dark=self._dark)
        dock = QDockWidget("设防参数", self); dock.setWidget(self._sidebar); dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.LeftDockWidgetArea, dock); self._sidebar_dock = dock

    def _setup_central(self):
        central = QWidget(); self.setCentralWidget(central); layout = QVBoxLayout(central); layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Vertical)
        self._tabs = QTabWidget(); self._tabs.setDocumentMode(True)
        self._import_panel = ImportPanel(dark=self._dark)
        self._selector_panel = SelectorPanel(dark=self._dark)
        self._generator_panel = GeneratorPanel(dark=self._dark)
        self._signal_panel = SignalPanel(dark=self._dark)
        self._summary_panel = SummaryPanel(dark=self._dark)
        self._result_panel = ResultPanel(dark=self._dark)
        self._tabs.addTab(self._import_panel, "导入")
        self._tabs.addTab(self._selector_panel, "选波")
        self._tabs.addTab(self._generator_panel, "人工波")
        self._tabs.addTab(self._signal_panel, "信号处理")
        self._tabs.addTab(self._summary_panel, "汇总")
        self._tabs.addTab(self._result_panel, "导出")
        splitter.addWidget(self._tabs)
        self._shared_plot = SpectrumPlot(dark=self._dark, log_x=False); self._shared_plot.setMinimumHeight(150)
        splitter.addWidget(self._shared_plot); splitter.setSizes([600, 280]); layout.addWidget(splitter)

    def _setup_menubar(self):
        menubar = self.menuBar(); file_menu = menubar.addMenu("文件(&F)")
        import_action = QAction("导入地震动(&I)...", self); import_action.setShortcut(QKeySequence("Ctrl+I")); import_action.triggered.connect(lambda: self._tabs.setCurrentIndex(0)); file_menu.addAction(import_action)
        export_action = QAction("导出结果(&E)...", self); export_action.setShortcut(QKeySequence("Ctrl+E")); export_action.triggered.connect(lambda: self._tabs.setCurrentIndex(5)); file_menu.addAction(export_action)

    def _setup_statusbar(self): self._statusbar = QStatusBar(); self.setStatusBar(self._statusbar); self._statusbar.showMessage("就绪")

    def _connect_signals(self):
        self._sidebar.spectrum_changed.connect(self._on_spectrum_changed)
        self._import_panel.signals_loaded.connect(self._on_signals_loaded)
        self._selector_panel.selection_done.connect(self._on_selection_done)
        self._generator_panel.wave_generated.connect(self._on_wave_generated)
        self._import_panel._table.wave_double_clicked.connect(self._on_wave_double_clicked)
        self._tabs.currentChanged.connect(self._on_tab_changed)

    def _on_spectrum_changed(self, periods, sa):
        self._selector_panel.set_code_spectrum(periods, sa); self._generator_panel.set_code_spectrum(periods, sa)
        self._summary_panel.set_code_spectrum(periods, sa); self._result_panel.set_code_spectrum(periods, sa)
        self._refresh_shared_plot(periods, sa)

    def _refresh_shared_plot(self, periods=None, sa=None):
        self._shared_plot.clear(); colors = get_mpl_colors(self._dark)
        if periods is not None and sa is not None:
            self._shared_plot.plot_code_spectrum(periods, sa, label="规范谱"); self._shared_plot.plot_envelope(periods, sa)
        for i, (label, p, s) in enumerate(self._selection_spectra):
            self._shared_plot.ax.plot(p, s, label=label, color=colors['palette'][i % len(colors['palette'])], linewidth=1.2, alpha=0.8)
        for (label, p, s) in self._generated_spectra:
            self._shared_plot.ax.plot(p, s, label=label, color=colors['accent'], linewidth=1.5, linestyle='--', alpha=0.9)
        self._shared_plot.refresh()

    def _on_signals_loaded(self, signals):
        self._selector_panel.set_imported_signals(signals)
        self._signal_panel.set_signal_pool(signals)
        self._statusbar.showMessage(f"已加载 {len(signals)} 条地震波")

    def _on_selection_done(self, results):
        db = self._selector_panel.get_database(); self._result_panel.set_results(results, database=db); self._summary_panel.set_results(results)
        self._selection_spectra = []
        db_periods = db.spectra_periods if db else None
        if db_periods is not None:
            for r in results:
                self._selection_spectra.append((f"RSN{r.record.rsn}", db_periods, r.record.sa * r.scale_factor))
        periods, sa = self._sidebar.get_spectrum(); self._refresh_shared_plot(periods, sa)

    def _on_wave_generated(self, signal):
        self._result_panel.add_generated_wave(signal)
        self._summary_panel.set_generated_waves(self._result_panel._generated_waves)
        from seiswave.core import Spectra
        periods, code_sa = self._sidebar.get_spectrum()
        if periods is not None:
            spec = Spectra.compute(signal.acc, signal.dt, periods, 0.05)
            self._generated_spectra.append((f"人工波 (PGA={signal.pga:.3f}g)", periods, spec.sa)); self._refresh_shared_plot(periods, code_sa)

    def _on_wave_double_clicked(self, row):
        sig = self._import_panel._table.get_signal(row)
        if sig: self._signal_panel.set_signal(sig); self._tabs.setCurrentIndex(3)

    def _on_tab_changed(self, index):
        names = ["数据导入", "选波", "人工波生成", "信号处理", "选波汇总", "导出与报告"]
        if 0 <= index < len(names): self._statusbar.showMessage(f"当前: {names[index]}")

    def _toggle_theme(self):
        self._dark = self._theme_action.isChecked(); self._apply_theme()

    def _apply_theme(self): QApplication.instance().setStyleSheet(get_theme(self._dark))

    def _show_about(self):
        QMessageBox.about(self, "关于 SeisWave", "SeisWave")
