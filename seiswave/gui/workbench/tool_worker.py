"""在 GUI 线程之外运行工具重计算的后台 Worker。

工具通过 ``build_job()`` 返回 ``(compute, finalize)``：

- ``compute(progress_cb, is_cancelled)`` 在 QThread 里执行纯计算（numpy/core），
  期间用 ``progress_cb(pct, text)`` 上报进度、用 ``is_cancelled()`` 协作式取消；
- ``finalize(payload)`` 回到 GUI 线程写回 SignalPool、刷新预览、弹通知。

校验（选择/目标谱/QMessageBox）必须留在 GUI 线程，于 ``build_job()`` 内完成。
"""

from __future__ import annotations

from typing import Callable

from seiswave.gui.workers import BaseWorker


class ToolJobWorker(BaseWorker):
    """把工具的 compute 回调放到 QThread 中执行。"""

    def __init__(self, compute: Callable, parent=None) -> None:
        super().__init__(parent)
        self._compute = compute

    def execute(self):
        return self._compute(self._emit_progress, lambda: self.is_cancelled)

    def _emit_progress(self, pct: float, text: str = "") -> None:
        self.signals.progress.emit(int(pct), str(text))


__all__ = ["ToolJobWorker"]
