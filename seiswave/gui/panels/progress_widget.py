"""进度与信息展示组件"""

import time
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QProgressBar, QLabel


class ProgressWidget(QWidget):
    """进度条 + 状态文本 + 结果信息"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── 实时进度区 ──
        progress_group = QGroupBox("迭代进度")
        progress_layout = QVBoxLayout(progress_group)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        progress_layout.addWidget(self._progress_bar)
        self._progress_label = QLabel("等待生成...")
        self._progress_label.setWordWrap(True)
        progress_layout.addWidget(self._progress_label)
        # 预计剩余时间
        self._eta_label = QLabel("")
        self._eta_label.setWordWrap(True)
        self._eta_label.setStyleSheet("color: #888; font-size: 11px;")
        progress_layout.addWidget(self._eta_label)
        layout.addWidget(progress_group)

        # ── 结果信息（支持富文本）──
        self._info_label = QLabel("")
        self._info_label.setWordWrap(True)
        layout.addWidget(self._info_label)

        layout.addStretch()

    # ── 状态控制 ──

    def start(self):
        """开始新任务"""
        self._progress_bar.setValue(0)
        self._progress_label.setText("正在生成...")
        self._eta_label.setText("")
        self._info_label.setText("")
        self._start_time = time.monotonic()

    def update(self, pct, text):
        """更新进度"""
        self._progress_bar.setValue(pct)
        self._progress_label.setText(text)
        # 预计剩余时间
        if hasattr(self, '_start_time') and pct > 0 and pct < 100:
            elapsed = time.monotonic() - self._start_time
            eta = elapsed * (100 - pct) / pct
            self._eta_label.setText(f"预计剩余: {eta:.0f}s")
        elif pct >= 100:
            self._eta_label.setText("")

    def finish(self, info_lines, progress_text=None):
        """任务完成"""
        self._progress_bar.setValue(100)
        self._eta_label.setText("")
        if info_lines:
            self._info_label.setText("\n".join(info_lines))
        if progress_text:
            self._progress_label.setText(progress_text)

    def error(self, msg):
        """显示错误"""
        self._info_label.setText(f"生成出错: {msg}")
        self._progress_label.setText("生成失败")
        self._eta_label.setText("")

    def clear(self):
        """清空所有状态"""
        self._progress_bar.setValue(0)
        self._progress_label.setText("等待生成...")
        self._eta_label.setText("")
        self._info_label.setText("")
