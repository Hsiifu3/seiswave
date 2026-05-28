import numpy as np
import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def sample_signal():
    from seiswave.core import EQSignal

    t = np.linspace(0, 10, 500)
    acc = 0.3 * np.sin(t) + 0.05 * np.cos(3 * t)
    return EQSignal(acc, dt=t[1] - t[0], name="sample")


class TestSignalPanelMore:
    def test_set_signal_updates_labels_and_trim_range(self, qapp, sample_signal):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        panel.set_signal(sample_signal)

        assert panel.get_processed() is not None
        assert "当前记录: sample" in panel._info_label.text()
        assert panel._trim_start.value() == 0.0
        assert panel._trim_end.value() == pytest.approx(sample_signal.duration)
        assert panel._lbl_pga_before.text() != "--"
        assert panel._lbl_pga_after.text() != "--"

    def test_set_signal_pool_empty_disables_actions(self, qapp):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        panel.set_signal_pool([])

        assert panel.get_processed() is None
        assert panel._baseline_btn.isEnabled() is False
        assert panel._filter_btn.isEnabled() is False
        assert panel._trim_btn.isEnabled() is False
        assert "暂无人工波/天然波记录" in panel._info_label.text()

    def test_apply_selection_invalid_shows_info(self, qapp, monkeypatch):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        infos = []
        monkeypatch.setattr("seiswave.gui.panels.signal_panel.QMessageBox.information",
                            lambda *a: infos.append(a[-1]))
        panel._apply_selection()
        assert infos == ["请先从下拉框选择记录"]

    def test_apply_baseline_without_signal_warns(self, qapp, monkeypatch):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        warnings = []
        monkeypatch.setattr("seiswave.gui.panels.signal_panel.QMessageBox.warning",
                            lambda *a: warnings.append(a[-1]))
        panel._apply_baseline()
        assert warnings == ["未选择记录，无法处理"]

    def test_apply_baseline_calls_correct_baseline(self, qapp, sample_signal, monkeypatch):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        panel.set_signal(sample_signal)
        called = {}
        emitted = []
        panel.signal_processed.connect(emitted.append)

        def fake_correct(sig, method, order, copy):
            called["args"] = (sig, method, order, copy)
            return sig

        monkeypatch.setattr("seiswave.core.filter.correct_baseline", fake_correct)
        panel._baseline_combo.setCurrentIndex(1)
        panel._poly_order_spin.setValue(4)
        panel._apply_baseline()

        assert called["args"][1:] == ("bilinear", 4, False)
        assert len(emitted) == 1

    def test_apply_filter_bandpass_success(self, qapp, sample_signal, monkeypatch):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        panel.set_signal(sample_signal)
        emitted = []
        panel.signal_processed.connect(emitted.append)
        captured = {}

        def fake_butterworth(acc, dt, ftype, order, freqs):
            captured["args"] = (dt, ftype, order, freqs)
            return acc * 0.5

        monkeypatch.setattr("seiswave.gui.panels.signal_panel.Filter.butterworth", fake_butterworth)
        panel._filter_type_combo.setCurrentIndex(0)
        panel._filter_order_spin.setValue(3)
        panel._f1_spin.setValue(0.2)
        panel._f2_spin.setValue(12.0)
        panel._apply_filter()

        assert captured["args"] == (sample_signal.dt, "bandpass", 3, (0.2, 12.0))
        assert len(emitted) == 1

    def test_apply_filter_lowpass_and_highpass(self, qapp, sample_signal, monkeypatch):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        panel.set_signal(sample_signal)
        calls = []

        def fake_butterworth(acc, dt, ftype, order, freqs):
            calls.append((ftype, freqs))
            return acc

        monkeypatch.setattr("seiswave.gui.panels.signal_panel.Filter.butterworth", fake_butterworth)

        panel._filter_type_combo.setCurrentIndex(1)
        panel._f2_spin.setValue(8.0)
        panel._apply_filter()

        panel._filter_type_combo.setCurrentIndex(2)
        panel._f1_spin.setValue(0.4)
        panel._apply_filter()

        assert calls[0] == ("lowpass", 8.0)
        assert calls[1] == ("highpass", 0.4)

    def test_apply_filter_error_shows_critical(self, qapp, sample_signal, monkeypatch):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        panel.set_signal(sample_signal)
        errors = []

        def boom(*args, **kwargs):
            raise RuntimeError("bad filter")

        monkeypatch.setattr("seiswave.gui.panels.signal_panel.Filter.butterworth", boom)
        monkeypatch.setattr("seiswave.gui.panels.signal_panel.QMessageBox.critical",
                            lambda *a: errors.append(a[-1]))
        panel._apply_filter()
        assert errors == ["bad filter"]

    def test_apply_trim_warns_for_invalid_range(self, qapp, sample_signal, monkeypatch):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        panel.set_signal(sample_signal)
        warnings = []
        monkeypatch.setattr("seiswave.gui.panels.signal_panel.QMessageBox.warning",
                            lambda *a: warnings.append(a[-1]))
        panel._trim_start.setValue(5.0)
        panel._trim_end.setValue(4.0)
        panel._apply_trim()
        assert warnings == ["结束时间必须大于起始时间"]

    def test_apply_trim_noop_when_indices_collapse(self, qapp, monkeypatch):
        from seiswave.core import EQSignal
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        signal = EQSignal(np.array([0.1, 0.2, 0.3, 0.4]), dt=1.0, name="coarse")
        panel.set_signal(signal)
        called = []
        monkeypatch.setattr(panel.get_processed(), "trim", lambda *a: called.append(a))
        panel._trim_start.setValue(0.10)
        panel._trim_end.setValue(0.20)
        panel._apply_trim()
        assert called == []

    def test_apply_trim_trims_and_emits(self, qapp, sample_signal, monkeypatch):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        panel.set_signal(sample_signal)
        emitted = []
        panel.signal_processed.connect(emitted.append)
        calls = []

        monkeypatch.setattr(panel.get_processed(), "trim", lambda i1, i2: calls.append((i1, i2)))
        panel._trim_start.setValue(0.2)
        panel._trim_end.setValue(1.0)
        panel._apply_trim()

        assert len(calls) == 1
        assert calls[0][0] < calls[0][1]
        assert len(emitted) == 1

    def test_apply_auto_trim_and_reset(self, qapp, sample_signal, monkeypatch):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        panel.set_signal(sample_signal)
        emitted = []
        panel.signal_processed.connect(emitted.append)
        calls = []

        monkeypatch.setattr(panel.get_processed(), "auto_trim", lambda a, b: calls.append((a, b)))
        panel._apply_auto_trim()
        assert calls == [(0.05, 0.95)]
        assert len(emitted) == 1

        old_processed = panel.get_processed()
        panel._reset()
        assert panel.get_processed() is not None
        assert panel.get_processed() is not old_processed

    def test_set_dark_delegates(self, qapp):
        from seiswave.gui.panels.signal_panel import SignalPanel

        panel = SignalPanel()
        calls = []
        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(panel._orig_plot, "set_dark", lambda dark: calls.append(("orig", dark)))
        monkeypatch.setattr(panel._proc_plot, "set_dark", lambda dark: calls.append(("proc", dark)))
        panel.set_dark(True)
        monkeypatch.undo()

        assert calls == [("orig", True), ("proc", True)]
