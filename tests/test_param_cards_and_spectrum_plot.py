import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestSpectrumPlot:
    def test_init_axes_log_and_linear(self, qapp):
        from seiswave.gui.widgets.spectrum_plot import SpectrumPlot

        log_plot = SpectrumPlot(log_x=True)
        assert log_plot.ax.get_xscale() == "log"
        assert log_plot.ax.get_xlabel() == "周期 T (s)"
        assert log_plot.ax.get_ylabel() == "加速度反应谱 Sa (g)"

        linear_plot = SpectrumPlot(log_x=False)
        assert linear_plot.ax.get_xscale() == "linear"

    def test_clear_restores_axes(self, qapp):
        from seiswave.gui.widgets.spectrum_plot import SpectrumPlot

        plot = SpectrumPlot(log_x=True)
        plot.ax.plot([0.1, 0.5], [1.0, 2.0])
        assert len(plot.ax.lines) == 1

        plot.clear()
        assert len(plot.ax.lines) == 0
        assert plot.ax.get_xscale() == "log"
        lo, hi = plot.ax.get_xlim()
        assert lo == pytest.approx(0.01)
        assert hi == pytest.approx(6.0)

    def test_plot_spectrum_and_code_spectrum(self, qapp):
        from seiswave.gui.widgets.spectrum_plot import SpectrumPlot

        plot = SpectrumPlot()
        periods = np.array([0.1, 0.5, 1.0])
        sa = np.array([1.0, 0.8, 0.5])

        plot.plot_spectrum(periods, sa, label="wave1")
        assert len(plot.ax.lines) == 1
        assert plot.ax.get_legend() is not None

        plot.plot_code_spectrum(periods, sa, label="规范谱")
        assert len(plot.ax.lines) == 2
        assert plot.ax.lines[-1].get_linestyle() == "--"

    def test_plot_comparison_with_mean(self, qapp):
        from seiswave.gui.widgets.spectrum_plot import SpectrumPlot

        plot = SpectrumPlot()
        periods = np.array([0.1, 0.5, 1.0])
        code_sa = np.array([1.0, 0.9, 0.7])
        waves = [
            np.array([0.9, 0.8, 0.6]),
            np.array([1.1, 1.0, 0.8]),
        ]

        plot.plot_comparison(periods, code_sa, waves, ["W1", "W2"])
        assert len(plot.ax.lines) == 4  # code + 2 waves + mean
        labels = [line.get_label() for line in plot.ax.lines]
        assert "规范谱" in labels
        assert "均值谱" in labels

    def test_plot_comparison_single_wave_no_mean(self, qapp):
        from seiswave.gui.widgets.spectrum_plot import SpectrumPlot

        plot = SpectrumPlot()
        periods = np.array([0.1, 0.5])
        code_sa = np.array([1.0, 0.9])
        waves = [np.array([0.8, 0.7])]

        plot.plot_comparison(periods, code_sa, waves)
        assert len(plot.ax.lines) == 2  # code + single wave

    def test_plot_envelope(self, qapp):
        from seiswave.gui.widgets.spectrum_plot import SpectrumPlot

        plot = SpectrumPlot()
        periods = np.array([0.1, 0.5, 1.0])
        code_sa = np.array([1.0, 0.8, 0.6])

        before = len(plot.ax.collections)
        plot.plot_envelope(periods, code_sa)
        after = len(plot.ax.collections)
        assert after == before + 1
        assert plot.ax.get_legend() is not None
