"""
ProgressDialog 单元测试

覆盖：初始化、取消信号、进度更新、完成状态切换。
"""

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestProgressDialog:
    def test_initial_state(self, qapp):
        from seiswave.gui.widgets.progress_dialog import ProgressDialog

        dlg = ProgressDialog(title="测试中")
        assert dlg.windowTitle() == "测试中"
        assert dlg._progress.value() == 0
        assert dlg._label.text() == "正在准备..."
        assert dlg._cancel_btn.isEnabled() is True
        assert dlg.is_cancelled is False

    def test_update_progress(self, qapp):
        from seiswave.gui.widgets.progress_dialog import ProgressDialog

        dlg = ProgressDialog()
        dlg.update_progress(42, "进行中...")
        assert dlg._progress.value() == 42
        assert dlg._label.text() == "进行中..."

    def test_set_finished(self, qapp):
        from seiswave.gui.widgets.progress_dialog import ProgressDialog

        dlg = ProgressDialog()
        dlg.set_finished("全部完成")
        assert dlg._progress.value() == 100
        assert dlg._label.text() == "全部完成"
        assert dlg._cancel_btn.text() == "关闭"
        assert dlg._cancel_btn.isEnabled() is True

    def test_cancel_emits_signal_and_disables_button(self, qapp):
        from seiswave.gui.widgets.progress_dialog import ProgressDialog

        dlg = ProgressDialog()
        emitted = []
        dlg.cancelled.connect(lambda: emitted.append(1))
        dlg._on_cancel()

        assert dlg.is_cancelled is True
        assert dlg._cancel_btn.isEnabled() is False
        assert dlg._label.text() == "正在取消..."
        assert emitted == [1]
