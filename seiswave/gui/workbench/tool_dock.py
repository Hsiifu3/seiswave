"""右侧工具参数占位容器。"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


TOOL_DESCRIPTIONS = {
    "导入": "Phase 3 将在这里接入 PEER/AT2/TXT 导入流程。",
    "自动选波": "Phase 3 将在这里接入目标谱驱动的一键自动选波。",
    "人工波生成": "Phase 3 将在这里接入一般/FF/NF/NFP 人工波生成参数。",
    "基线校正": "Phase 3 将在这里接入基线校正工具参数。",
    "滤波": "Phase 3 将在这里接入带通/高通滤波参数。",
    "谱拟合": "Phase 3 将在这里接入独立谱拟合/调整工具。",
    "反应谱": "Phase 3 将在这里接入多阻尼反应谱参数。",
    "组合校核": "Phase 3 将在这里接入波组组合与规范校核参数。",
}


class ToolDock(QWidget):
    """按当前工具切换说明文案的右栏容器。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_tool = "导入"
        self._title_label: QLabel | None = None
        self._body: QTextEdit | None = None
        self._run_button: QPushButton | None = None
        self._setup_ui()
        self.set_current_tool(self._current_tool)

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("工具参数")
        root.addWidget(group)

        layout = QVBoxLayout(group)
        self._title_label = QLabel()
        layout.addWidget(self._title_label)

        self._body = QTextEdit()
        self._body.setReadOnly(True)
        self._body.setMinimumHeight(220)
        layout.addWidget(self._body, 1)

        self._run_button = QPushButton("▶ 运行")
        self._run_button.setEnabled(False)
        layout.addWidget(self._run_button)

        quick_group = QGroupBox("快捷动作")
        quick_layout = QVBoxLayout(quick_group)
        for text in ("快捷出图（Phase 3）", "导出数据（Phase 3）"):
            button = QPushButton(text)
            button.setEnabled(False)
            quick_layout.addWidget(button)
        root.addWidget(quick_group)
        root.addStretch(1)

    def current_tool(self) -> str:
        """返回当前工具名。"""
        return self._current_tool

    def set_current_tool(self, tool_name: str) -> None:
        """切换右栏占位内容。"""
        self._current_tool = tool_name
        description = TOOL_DESCRIPTIONS.get(tool_name, "Phase 3 将在此接入具体参数。")
        if self._title_label is not None:
            self._title_label.setText(f"当前工具：{tool_name}")
        if self._body is not None:
            self._body.setPlainText(description)

    def state(self) -> dict[str, str]:
        """返回可序列化的右栏状态。"""
        return {"current_tool": self._current_tool}

    def restore_state(self, state: dict[str, str] | None) -> None:
        """恢复右栏状态。"""
        tool_name = "导入"
        if state:
            tool_name = state.get("current_tool", tool_name)
        self.set_current_tool(tool_name)
