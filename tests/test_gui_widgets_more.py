import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_sig(name="sig", dt=0.02, n=128):
    from seiswave.core import EQSignal

    t = np.arange(n) * dt
    acc = np.sin(2 * np.pi * 2.0 * t) * 0.1
    return EQSignal(acc, dt, name=name)


class TestPlotWidgetMore:
    def test_no_toolbar_until_needed(self, qapp, monkeypatch):
        from seiswave.gui.widgets.plot_widget import PlotWidget

        widget = PlotWidget(show_toolbar=False)
        assert widget.toolbar is None
        assert not hasattr(widget, "_hidden_toolbar")

        calls = []
        monkeypatch.setattr("seiswave.gui.widgets.plot_widget.NavigationToolbar2QT.home", lambda self: calls.append("home"))
        monkeypatch.setattr("seiswave.gui.widgets.plot_widget.NavigationToolbar2QT.pan", lambda self: calls.append("pan"))
        monkeypatch.setattr("seiswave.gui.widgets.plot_widget.NavigationToolbar2QT.zoom", lambda self: calls.append("zoom"))

        widget._action_home()
        widget._action_pan()
        widget._action_zoom()

        assert calls == ["home", "pan", "zoom"]
        assert hasattr(widget, "_hidden_toolbar")

    def test_action_save_writes_when_path_selected(self, qapp, monkeypatch, tmp_path):
        from seiswave.gui.widgets.plot_widget import PlotWidget

        widget = PlotWidget(show_toolbar=False)
        out = tmp_path / "plot.png"
        monkeypatch.setattr(
            "seiswave.gui.widgets.plot_widget.QFileDialog.getSaveFileName",
            lambda *a, **k: (str(out), "PNG (*.png)"),
        )

        saved = []
        monkeypatch.setattr(widget.canvas.fig, "savefig", lambda path, **k: saved.append((path, k)))
        widget._action_save()

        assert saved
        assert saved[0][0] == str(out)
        assert saved[0][1]["dpi"] == 300

    def test_action_save_skips_when_empty_path(self, qapp, monkeypatch):
        from seiswave.gui.widgets.plot_widget import PlotWidget

        widget = PlotWidget(show_toolbar=False)
        monkeypatch.setattr(
            "seiswave.gui.widgets.plot_widget.QFileDialog.getSaveFileName",
            lambda *a, **k: ("", "PNG (*.png)"),
        )

        called = []
        monkeypatch.setattr(widget.canvas.fig, "savefig", lambda *a, **k: called.append(True))
        widget._action_save()
        assert called == []

    def test_clear_refresh_set_dark_and_properties(self, qapp):
        from seiswave.gui.widgets.plot_widget import PlotWidget

        widget = PlotWidget(show_toolbar=True, compact_toolbar=True)
        assert widget.ax is widget.canvas.ax
        assert widget.fig is widget.canvas.fig
        assert widget.toolbar is not None

        widget.ax.plot([0, 1], [0, 1])
        widget.clear()
        widget.refresh()
        widget.set_dark(True)
        assert widget.canvas._dark is True


class TestWaveTableMore:
    def test_selection_double_click_getters_and_clear(self, qapp):
        from seiswave.gui.widgets.wave_table import WaveTable

        table = WaveTable()
        sig1 = _make_sig("wave1")
        sig2 = _make_sig("wave2")
        table.load_signals([sig1, sig2])

        selected = []
        dbl = []
        table.wave_selected.connect(selected.append)
        table.wave_double_clicked.connect(dbl.append)

        table.selectRow(1)
        qapp.processEvents()
        table._on_double_click(0, 0)

        assert table.get_signal(0) is sig1
        assert table.get_signal(10) is None
        assert table.get_selected_signal() is sig2
        assert selected == [1]
        assert dbl == [0]
        assert table.item(0, 1).textAlignment() != 0

        table.clear_all()
        assert table.rowCount() == 0
        assert table.get_selected_signal() is None

