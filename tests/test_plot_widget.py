"""
PlotWidget / PlotCanvas 单元测试

覆盖：初始化、clear/refresh/set_dark、右键菜单 action。
不测试实际 GUI 交互，用 mock 绕过。
"""

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestPlotCanvas:
    def test_init(self, qapp):
        from seiswave.gui.widgets.plot_widget import PlotCanvas

        canvas = PlotCanvas(dark=False, width=6, height=4, dpi=80)
        assert canvas.fig is not None
        assert canvas.ax is not None
        assert canvas._dark is False

    def test_clear(self, qapp):
        from seiswave.gui.widgets.plot_widget import PlotCanvas

        canvas = PlotCanvas(dark=False)
        canvas.ax.plot([1, 2, 3], [4, 5, 6])
        canvas.clear()
        assert len(canvas.ax.lines) == 0

    def test_set_dark(self, qapp):
        from seiswave.gui.widgets.plot_widget import PlotCanvas

        canvas = PlotCanvas(dark=False)
        canvas.set_dark(True)
        assert canvas._dark is True
        assert canvas.fig.get_facecolor() is not None


class TestPlotWidget:
    def test_init_without_toolbar(self, qapp):
        from seiswave.gui.widgets.plot_widget import PlotWidget

        w = PlotWidget(show_toolbar=False)
        assert w.toolbar is None
        assert w.canvas is not None

    def test_init_with_toolbar(self, qapp):
        from seiswave.gui.widgets.plot_widget import PlotWidget

        w = PlotWidget(show_toolbar=True, compact_toolbar=True)
        assert w.toolbar is not None

    def test_actions_call_toolbar(self, qapp, monkeypatch):
        from seiswave.gui.widgets.plot_widget import PlotWidget

        w = PlotWidget(show_toolbar=False)
        called = {"home": 0, "pan": 0, "zoom": 0}

        class FakeTB:
            def home(self):
                called["home"] += 1
            def pan(self):
                called["pan"] += 1
            def zoom(self):
                called["zoom"] += 1

        monkeypatch.setattr(w, "_ensure_toolbar", lambda: FakeTB())
        w._action_home()
        w._action_pan()
        w._action_zoom()

        assert called == {"home": 1, "pan": 1, "zoom": 1}

    def test_ensure_toolbar_creates_hidden(self, qapp):
        from seiswave.gui.widgets.plot_widget import PlotWidget

        w = PlotWidget(show_toolbar=False)
        assert w.toolbar is None
        tb = w._ensure_toolbar()
        assert tb is not None
        assert tb.isVisible() is False

    def test_ensure_toolbar_returns_existing(self, qapp):
        from seiswave.gui.widgets.plot_widget import PlotWidget

        w = PlotWidget(show_toolbar=True)
        tb1 = w._ensure_toolbar()
        tb2 = w._ensure_toolbar()
        assert tb1 is tb2
