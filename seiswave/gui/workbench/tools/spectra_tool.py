"""Reaction-spectrum tool."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QVBoxLayout

from .common import ToolWidget


class SpectraTool(ToolWidget):
    """Configure the central spectrum preview."""

    def __init__(self, preview_panel, parent=None) -> None:
        super().__init__(parent)
        self._preview_panel = preview_panel
        self._triple_log_check: QCheckBox | None = None
        self._damping_combo: QComboBox | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel("对当前选中信号计算 Sa/Sv/Sd，并把显示配置推送到中央预览区。")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self._triple_log_check = QCheckBox("Sa/Sv/Sd 三联对数图")
        form.addRow("图形模式:", self._triple_log_check)

        self._damping_combo = QComboBox()
        self._damping_combo.addItem("单阻尼 5%", "single")
        self._damping_combo.addItem("多阻尼 2% / 5% / 10%", "multi")
        form.addRow("阻尼显示:", self._damping_combo)
        layout.addLayout(form)
        layout.addStretch(1)

    def run_tool(self) -> dict[str, object]:
        assert self._triple_log_check is not None
        assert self._damping_combo is not None
        self._preview_panel.set_spectrum_options(
            triple_log=self._triple_log_check.isChecked(),
            damping_mode=str(self._damping_combo.currentData()),
        )
        return self._preview_panel.current_spectrum_snapshot()

    def state(self) -> dict[str, object]:
        assert self._triple_log_check is not None
        assert self._damping_combo is not None
        return {
            "triple_log": self._triple_log_check.isChecked(),
            "damping_mode": self._damping_combo.currentData(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        if state is None:
            state = {}
        assert self._triple_log_check is not None
        assert self._damping_combo is not None
        self._triple_log_check.setChecked(bool(state.get("triple_log", False)))
        mode = str(state.get("damping_mode", "single"))
        index = self._damping_combo.findData(mode)
        if index >= 0:
            self._damping_combo.setCurrentIndex(index)
