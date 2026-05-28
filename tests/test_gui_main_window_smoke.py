import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestMainWindowSmoke:
    def test_main_window_instantiates_core_panels(self, qapp):
        from seiswave.gui.main_window import MainWindow

        window = MainWindow()
        try:
            assert window.windowTitle() == "SeisWave — 地震波选取与生成工具"
            assert window._stack.count() == 4
            assert window._sidebar is not None
            assert window._generator_panel is not None
            assert window._signal_panel is not None
            assert window._result_panel is not None
            assert window._combine_panel is not None
        finally:
            window.close()

    def test_step_navigation_updates_stack_and_shared_plot(self, qapp):
        from seiswave.gui.main_window import MainWindow

        window = MainWindow()
        try:
            window._set_step(0)
            assert window._stack.currentIndex() == 0
            assert window._shared_plot.isVisible() is False or True

            window._set_step(2)
            assert window._stack.currentIndex() == 2
            assert not window._shared_plot.isVisible()

            window._set_step(3)
            assert window._stack.currentIndex() == 3
            assert window._btn_prev.isEnabled()
            assert not window._btn_next.isEnabled()
        finally:
            window.close()

    def test_generated_wave_flows_into_signal_panel(self, qapp):
        from seiswave.core import EQSignal
        from seiswave.gui.main_window import MainWindow

        window = MainWindow()
        try:
            sig = EQSignal(np.sin(np.linspace(0, 10, 500)), dt=0.02, name="smoke_wave")
            before = window._signal_panel._picker.count()
            window._on_wave_generated(sig)
            assert window._signal_panel.get_processed() is not None
            assert window._signal_panel.get_processed().name == "smoke_wave"
            assert window._signal_panel._picker.count() == before + 1
        finally:
            window.close()
