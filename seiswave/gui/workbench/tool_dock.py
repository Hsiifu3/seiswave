"""右侧工具与快捷动作容器。"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from seiswave.core.signal_pool import SignalPool
from seiswave.core.target_spectrum import TargetSpectrumService

from .preview_panel import PreviewPanel
from .tool_worker import ToolJobWorker
from .tools import (
    ArtificialTool,
    AutoSelectTool,
    CombineTool,
    DataExportTool,
    ImportTool,
    PlotExportTool,
    SignalProcessTool,
    SpectralMatchTool,
    SpectraTool,
)


class ToolDock(QWidget):
    """按当前工具切换参数面板，并常驻快捷出图/导出。"""

    message_requested = Signal(str)
    progress_changed = Signal(int, str)
    run_state_changed = Signal(bool)

    def __init__(
        self,
        pool: SignalPool,
        target_service: TargetSpectrumService,
        preview_panel: PreviewPanel,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pool = pool
        self._target_service = target_service
        self._preview_panel = preview_panel
        self._current_tool = "导入"
        self._tool_widgets: dict[str, QWidget] = {}
        self._title_label: QLabel | None = None
        self._stack: QStackedWidget | None = None
        self._run_button: QPushButton | None = None
        self._plot_export_tool: PlotExportTool | None = None
        self._data_export_tool: DataExportTool | None = None
        self._active_worker: ToolJobWorker | None = None
        self._setup_ui()
        self._register_tools()
        self.set_current_tool(self._current_tool)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("工具参数")
        root.addWidget(group)

        layout = QVBoxLayout(group)
        self._title_label = QLabel()
        layout.addWidget(self._title_label)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)

        self._run_button = QPushButton("▶ 运行")
        self._run_button.clicked.connect(self._run_current_tool)
        layout.addWidget(self._run_button)

        quick_group = QGroupBox("快捷动作")
        quick_layout = QVBoxLayout(quick_group)
        self._plot_export_tool = PlotExportTool(
            self._preview_panel,
            self.message_requested.emit,
        )
        quick_layout.addWidget(self._plot_export_tool)
        self._data_export_tool = DataExportTool(
            self._pool,
            self._target_service,
            self._preview_panel,
            self.message_requested.emit,
        )
        quick_layout.addWidget(self._data_export_tool)
        root.addWidget(quick_group)
        root.addStretch(1)

    def _register_tools(self) -> None:
        self._add_tool(
            "导入",
            ImportTool(self._pool, self.message_requested.emit),
        )
        self._add_tool(
            "自动选波",
            AutoSelectTool(
                self._pool,
                self._target_service,
                self.message_requested.emit,
            ),
        )
        self._add_tool(
            "人工波生成",
            ArtificialTool(
                self._pool,
                self._target_service,
                self.message_requested.emit,
            ),
        )
        self._add_tool(
            "基线校正",
            SignalProcessTool(self._pool, self.message_requested.emit, mode="baseline"),
        )
        self._add_tool(
            "滤波",
            SignalProcessTool(self._pool, self.message_requested.emit, mode="filter"),
        )
        self._add_tool(
            "谱拟合",
            SpectralMatchTool(
                self._pool,
                self._target_service,
                self.message_requested.emit,
            ),
        )
        self._add_tool(
            "反应谱",
            SpectraTool(self._preview_panel),
        )
        self._add_tool(
            "组合校核",
            CombineTool(
                self._pool,
                self._target_service,
                self.message_requested.emit,
            ),
        )

    def _add_tool(self, name: str, widget: QWidget) -> None:
        assert self._stack is not None
        self._tool_widgets[name] = widget
        self._stack.addWidget(widget)

    def current_tool(self) -> str:
        """返回当前工具名。"""
        return self._current_tool

    def set_current_tool(self, tool_name: str) -> None:
        """切换右栏工具内容。"""
        if self._active_worker is not None and tool_name != self._current_tool:
            self.message_requested.emit("有任务正在运行，请先等待或取消")
            return
        widget = self._tool_widgets.get(tool_name)
        if widget is None:
            tool_name = "导入"
            widget = self._tool_widgets[tool_name]
        self._current_tool = tool_name
        if self._title_label is not None:
            self._title_label.setText(f"当前工具：{tool_name}")
        if self._stack is not None:
            self._stack.setCurrentWidget(widget)
        if self._run_button is not None:
            supports_run = getattr(widget, "supports_run", lambda: False)()
            run_label = getattr(widget, "run_label", lambda: "▶ 运行")()
            self._run_button.setText(run_label)
            self._run_button.setEnabled(bool(supports_run))

    def _run_current_tool(self) -> object | None:
        # 运行中点击 = 取消
        if self._active_worker is not None:
            self._active_worker.cancel()
            self.message_requested.emit("正在取消…")
            return None

        widget = self._tool_widgets.get(self._current_tool)
        if widget is None:
            return None

        job = getattr(widget, "build_job", lambda: None)()
        if job is None:
            # 廉价工具：GUI 线程同步执行（run_tool 内部已各自兜底异常）
            return getattr(widget, "run_tool")()

        compute, finalize = job
        self._start_worker(compute, finalize)
        return None

    def _start_worker(self, compute, finalize) -> None:
        tool_name = self._current_tool
        worker = ToolJobWorker(compute)
        self._active_worker = worker
        worker.signals.progress.connect(
            lambda pct, text: self.progress_changed.emit(pct, text or "处理中…")
        )
        worker.signals.finished.connect(
            lambda payload: self._on_worker_finished(tool_name, finalize, payload)
        )
        worker.signals.error.connect(
            lambda message: self._on_worker_error(tool_name, message)
        )
        worker.finished.connect(worker.deleteLater)
        self._set_running(True, tool_name)
        worker.start()

    def _on_worker_finished(self, tool_name: str, finalize, payload) -> None:
        self._set_running(False, tool_name)
        try:
            finalize(payload)
        except Exception as exc:  # finalize 在 GUI 线程，安全弹窗
            QMessageBox.critical(self, tool_name, str(exc))

    def _on_worker_error(self, tool_name: str, message: str) -> None:
        self._set_running(False, tool_name)
        if message == "用户取消":
            self.message_requested.emit(f"{tool_name} 已取消")
            return
        QMessageBox.critical(self, tool_name, message)

    def _set_running(self, running: bool, tool_name: str) -> None:
        if not running:
            self._active_worker = None
        if self._run_button is not None:
            if running:
                self._run_button.setText("■ 取消")
            else:
                widget = self._tool_widgets.get(tool_name)
                run_label = getattr(widget, "run_label", lambda: "▶ 运行")()
                self._run_button.setText(run_label)
        self.run_state_changed.emit(running)
        if not running:
            self.progress_changed.emit(0, "空闲")

    def state(self) -> dict[str, object]:
        """返回可序列化的右栏状态。"""
        tool_states = {
            name: getattr(widget, "state", lambda: {})()
            for name, widget in self._tool_widgets.items()
        }
        assert self._plot_export_tool is not None
        assert self._data_export_tool is not None
        return {
            "current_tool": self._current_tool,
            "tool_states": tool_states,
            "plot_export": self._plot_export_tool.state(),
            "data_export": self._data_export_tool.state(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        """恢复右栏状态。"""
        tool_name = "导入"
        if state:
            tool_states = state.get("tool_states", {})
            if isinstance(tool_states, dict):
                for name, widget in self._tool_widgets.items():
                    widget_state = tool_states.get(name)
                    getattr(widget, "restore_state", lambda _state: None)(widget_state)
            assert self._plot_export_tool is not None
            assert self._data_export_tool is not None
            self._plot_export_tool.restore_state(state.get("plot_export"))
            self._data_export_tool.restore_state(state.get("data_export"))
            tool_name = str(state.get("current_tool", tool_name))
        self.set_current_tool(tool_name)
