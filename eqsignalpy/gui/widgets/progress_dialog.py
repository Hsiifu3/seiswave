"""
进度对话框

显示后台计算进度，支持取消操作。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QProgressBar, QPushButton, QHBoxLayout,
)
from PySide6.QtCore import Qt


class ProgressDialog(QDialog):
    """计算进度对话框"""

    def __init__(self, title="计算中...", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(400, 140)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._cancelled = False
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        self._label = QLabel("正在准备...")
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        layout.addWidget(self._progress)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.setProperty("secondary", True)
        self._cancel_btn.clicked.connect(self._on_cancel)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

    def _on_cancel(self):
        self._cancelled = True
        self._label.setText("正在取消...")
        self._cancel_btn.setEnabled(False)

    @property
    def is_cancelled(self):
        return self._cancelled

    def update_progress(self, value: int, message: str = ""):
        self._progress.setValue(value)
        if message:
            self._label.setText(message)

    def set_finished(self, message: str = "完成"):
        self._progress.setValue(100)
        self._label.setText(message)
        self._cancel_btn.setText("关闭")
        self._cancel_btn.setEnabled(True)
        self._cancel_btn.clicked.disconnect()
        self._cancel_btn.clicked.connect(self.accept)
