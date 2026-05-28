"""底部状态栏

- 高度 32px
- 左侧：状态文本
- 右侧：进度百分比
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QProgressBar, QSizePolicy,
)


class BottomBar(QWidget):
    """底部状态栏"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setFixedHeight(32)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(8)

        self._status = QLabel("就绪")
        self._status.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._status)

        layout.addStretch()

        self._progress_pct = QLabel("")
        self._progress_pct.setStyleSheet(
            "font-size: 11px; font-family: monospace;"
        )
        layout.addWidget(self._progress_pct)

    def set_status(self, text: str):
        self._status.setText(text)

    def set_progress_text(self, text: str):
        self._progress_pct.setText(text)

    def set_progress_value(self, pct: int):
        self._progress_pct.setText(f"{pct}%")

    def clear(self):
        self._status.setText("就绪")
        self._progress_pct.setText("")
