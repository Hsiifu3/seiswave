"""SeisWave 工作台三栏主壳。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from seiswave.core.signal_pool import SignalPool
from seiswave.core.target_spectrum import TargetSpectrumService
from seiswave.gui.fonts import qt_font, setup_matplotlib_fonts
from seiswave.gui.styles import get_theme

from . import get_signal_pool, get_target_spectrum_service
from .preview_panel import PreviewPanel
from .project_io import ProjectIO
from .signal_pool_panel import SignalPoolPanel
from .tool_dock import ToolDock


TOOLBAR_TOOLS = [
    "导入",
    "自动选波",
    "人工波生成",
    "基线校正",
    "滤波",
    "谱拟合",
    "反应谱",
    "组合校核",
]


class AppWindow(QMainWindow):
    """工作台三栏主窗口。"""

    def __init__(
        self,
        pool: SignalPool | None = None,
        target_service: TargetSpectrumService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        setup_matplotlib_fonts()
        self._pool = pool or get_signal_pool()
        self._target_service = target_service or get_target_spectrum_service()
        self._current_project_path: Path | None = None
        self._current_tool = "导入"
        self._tool_action_group: QActionGroup | None = None
        self._tool_actions: dict[str, QAction] = {}
        self._toolbar_target_label: QLabel | None = None
        self._selection_status_label: QLabel | None = None
        self._target_status_label: QLabel | None = None
        self._progress_bar: QProgressBar | None = None
        self._signal_pool_panel: SignalPoolPanel | None = None
        self._preview_panel: PreviewPanel | None = None
        self._tool_dock: ToolDock | None = None
        self._configure_app_defaults()
        self._setup_window()
        self._setup_toolbar()
        self._setup_central()
        self._setup_menu()
        self._setup_statusbar()
        self._connect_state()
        self.set_current_tool(self._current_tool)
        self._refresh_status()

    def _configure_app_defaults(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        app.setFont(qt_font())
        app.setStyleSheet(get_theme(False))

    def _setup_window(self) -> None:
        self.setWindowTitle("SeisWave — 工作台")
        self.setMinimumSize(1400, 860)
        self.resize(1440, 900)

    def _setup_toolbar(self) -> None:
        toolbar = QToolBar("工作台工具", self)
        toolbar.setMovable(False)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        action_group = QActionGroup(self)
        action_group.setExclusive(True)
        self._tool_action_group = action_group
        for tool_name in TOOLBAR_TOOLS:
            action = QAction(tool_name, self)
            action.setCheckable(True)
            action.triggered.connect(
                lambda _checked=False, name=tool_name: self.set_current_tool(name)
            )
            action_group.addAction(action)
            toolbar.addAction(action)
            self._tool_actions[tool_name] = action

        toolbar.addSeparator()
        toolbar.addWidget(QLabel("目标谱："))
        self._toolbar_target_label = QLabel(self._target_service.describe())
        self._toolbar_target_label.setMinimumWidth(280)
        toolbar.addWidget(self._toolbar_target_label)

    def _setup_central(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        self._signal_pool_panel = SignalPoolPanel(self._pool)
        self._preview_panel = PreviewPanel(self._pool, self._target_service)
        self._tool_dock = ToolDock()
        splitter.addWidget(self._signal_pool_panel)
        splitter.addWidget(self._preview_panel)
        splitter.addWidget(self._tool_dock)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([300, 860, 320])
        layout.addWidget(splitter, 1)

    def _setup_menu(self) -> None:
        project_menu = self.menuBar().addMenu("项目(&P)")

        new_action = QAction("新建", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self.new_project)
        project_menu.addAction(new_action)

        open_action = QAction("打开…", self)
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self.open_project_dialog)
        project_menu.addAction(open_action)

        save_action = QAction("保存", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self.save_project_dialog)
        project_menu.addAction(save_action)

    def _setup_statusbar(self) -> None:
        statusbar = QStatusBar(self)
        self.setStatusBar(statusbar)

        self._selection_status_label = QLabel()
        self._target_status_label = QLabel()
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setFixedWidth(180)
        self._progress_bar.setFormat("空闲")

        statusbar.addWidget(self._selection_status_label, 0)
        statusbar.addPermanentWidget(self._target_status_label, 1)
        statusbar.addPermanentWidget(self._progress_bar)

    def _connect_state(self) -> None:
        assert self._signal_pool_panel is not None
        self._signal_pool_panel.tool_requested.connect(self.set_current_tool)
        self._pool.signals_changed.connect(self._refresh_status)
        self._pool.selection_changed.connect(self._refresh_status)
        self._target_service.target_changed.connect(self._refresh_status)

    def set_current_tool(self, tool_name: str) -> None:
        """切换当前工具占位。"""
        self._current_tool = tool_name
        action = self._tool_actions.get(tool_name)
        if action is not None:
            action.setChecked(True)
        assert self._tool_dock is not None
        self._tool_dock.set_current_tool(tool_name)
        self.statusBar().showMessage(f"当前工具：{tool_name}", 3000)

    def new_project(self) -> None:
        """清空当前工作台状态。"""
        self._pool.clear()
        self._target_service.clear()
        assert self._preview_panel is not None
        assert self._tool_dock is not None
        self._preview_panel.restore_state(None)
        self._tool_dock.restore_state(None)
        self.set_current_tool("导入")
        self._current_project_path = None
        self.statusBar().showMessage("已新建空项目", 3000)

    def save_project_dialog(self) -> None:
        """弹出对话框保存项目。"""
        default_path = ""
        if self._current_project_path is not None:
            default_path = str(self._current_project_path)
        path, _ = QFileDialog.getSaveFileName(
            self,
            "保存项目",
            default_path,
            "SeisWave Project (*.json)",
        )
        if path:
            self.save_project_to(path)

    def open_project_dialog(self) -> None:
        """弹出对话框打开项目。"""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "打开项目",
            "",
            "SeisWave Project (*.json)",
        )
        if path:
            self.load_project_from(path)

    def save_project_to(self, path: str | Path) -> tuple[Path, Path]:
        """将当前工作台写入项目文件。"""
        assert self._preview_panel is not None
        assert self._tool_dock is not None
        json_path, npz_path = ProjectIO.save_project(
            path,
            self._pool,
            self._target_service,
            ui_state={
                "current_tool": self._current_tool,
                "preview": self._preview_panel.state(),
                "tool_dock": self._tool_dock.state(),
            },
        )
        self._current_project_path = json_path
        self.statusBar().showMessage(f"项目已保存：{json_path.name}", 3000)
        return json_path, npz_path

    def load_project_from(self, path: str | Path) -> None:
        """从项目文件恢复工作台。"""
        result = ProjectIO.load_project(path, self._pool, self._target_service)
        ui_state = result.get("ui_state", {})
        assert self._preview_panel is not None
        assert self._tool_dock is not None
        self._preview_panel.restore_state(ui_state.get("preview"))
        self._tool_dock.restore_state(ui_state.get("tool_dock"))
        self.set_current_tool(ui_state.get("current_tool", "导入"))
        self._current_project_path = Path(path)
        self.statusBar().showMessage(f"项目已打开：{self._current_project_path.name}", 3000)

    def _refresh_status(self) -> None:
        count = len(self._pool.selection())
        target_description = self._target_service.describe()
        if self._toolbar_target_label is not None:
            self._toolbar_target_label.setText(target_description)
        if self._selection_status_label is not None:
            self._selection_status_label.setText(f"已选 {count} 条信号")
        if self._target_status_label is not None:
            self._target_status_label.setText(target_description)
        if self._progress_bar is not None:
            self._progress_bar.setValue(0)
            self._progress_bar.setFormat("空闲")
