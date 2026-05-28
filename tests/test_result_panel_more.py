import os
import csv
import numpy as np
import pytest
from types import SimpleNamespace

from seiswave.core.combiner import Combiner
from seiswave.core.peer_db import PeerRecord
from seiswave.core.selector import SelectionResult


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


def _make_record(rsn=1, name="EQ"):
    return PeerRecord(
        rsn=rsn, event=name, station=f"STA{rsn}",
        component="H1", direction="H",
        dt=0.02, npts=200, pga=0.2,
        duration=10.0, eff_duration=8.0,
        sa=np.array([0.2, 0.3, 0.25]),
        acc=np.array([0.0, 0.1]),
    )


class TestResultPanelMore:
    def test_add_generated_wave_and_update_total(self, qapp):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        sig = _make_sig("art1")
        panel.add_generated_wave(sig)
        panel._n_art_spin.setValue(3)
        panel._update_total()

        assert panel._generated_waves == [sig]
        assert "共 3 组" in panel._total_label.text()

    def test_set_code_spectrum(self, qapp):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        periods = np.array([0.1, 0.5, 1.0])
        sa = np.array([0.2, 0.3, 0.25])
        panel.set_code_spectrum(periods, sa)

        assert np.array_equal(panel._code_periods, periods)
        assert np.array_equal(panel._code_sa, sa)

    def test_generate_report_with_no_data_warns(self, qapp, monkeypatch):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        warnings = []
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.warning", lambda *a: warnings.append(a[-1]))
        panel._generate_report()
        assert warnings == ["没有选波结果"]

    def test_generate_report_creates_text_and_saves(self, qapp, monkeypatch, tmp_path):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        rec = _make_record(5, "EQ5")
        result = SelectionResult(record=rec, scale_factor=1.2, match_error=0.03, deviations={1.0: 0.1})
        panel.set_results([result])
        panel.add_generated_wave(_make_sig("art1"))
        panel.set_code_spectrum(np.array([0.1, 0.5]), np.array([0.2, 0.3]))
        panel._dir_edit.setText(str(tmp_path))

        infos = []
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.information", lambda *a: infos.append(a[-1]))
        panel._generate_report()

        preview = panel._preview.toPlainText()
        assert "SeisWave 地震动选波与人工波组合报告" in preview
        assert "RSN5" in preview
        assert "art1" in preview

        report_path = tmp_path / "selection_report.txt"
        assert report_path.exists()
        assert "SeisWave" in report_path.read_text(encoding="utf-8")
        assert any("selection_report.txt" in msg for msg in infos)

    def test_do_export_with_spectra_csv_and_plot(self, qapp, monkeypatch, tmp_path):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        sig = _make_sig("art1")
        panel.add_generated_wave(sig)
        panel._dir_edit.setText(str(tmp_path))
        panel._wave_fmt_combo.setCurrentIndex(1)  # txt
        panel.set_code_spectrum(np.array([0.1, 0.5, 1.0]), np.array([0.2, 0.3, 0.25]))

        # bypass matplotlib completely to avoid backend issues
        monkeypatch.setattr(panel, "_export_comparison_plot", lambda out_dir, combiner: None)
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.information", lambda *a: None)
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.critical", lambda *a: None)
        panel._do_export()

        spectra_csv = tmp_path / "spectra_comparison.csv"
        assert spectra_csv.exists()
        content = spectra_csv.read_text()
        assert "T(s)" in content
        assert "Code_Sa(g)" in content

        assert panel._combiner is not None

    def test_do_export_exception_shows_critical(self, qapp, monkeypatch):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        panel._dir_edit.setText("/tmp/fake")
        panel.add_generated_wave(_make_sig("art1"))

        errors = []
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.critical", lambda *a: errors.append(a[-1]))
        monkeypatch.setattr(panel, "_combiner", None)
        # force Combiner to raise on export
        original_export = Combiner.export
        def bad_export(*a, **k):
            raise RuntimeError("disk full")
        monkeypatch.setattr(Combiner, "export", bad_export)

        panel._do_export()
        assert any("disk full" in str(e) for e in errors)

        # restore
        monkeypatch.setattr(Combiner, "export", original_export)

    def test_do_export_warns_without_dir(self, qapp, monkeypatch):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        panel.add_generated_wave(_make_sig("art1"))
        warnings = []
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.warning", lambda *a: warnings.append(a[-1]))
        panel._do_export()
        assert warnings == ["请先选择输出目录"]

    def test_do_export_warns_without_data(self, qapp, monkeypatch):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        panel._dir_edit.setText("/tmp/fake")
        warnings = []
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.warning", lambda *a: warnings.append(a[-1]))
        panel._do_export()
        assert warnings == ["没有可导出的数据"]

    def test_do_export_adds_natural_waves_with_database(self, qapp, monkeypatch, tmp_path):
        from types import SimpleNamespace
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        rec = _make_record(1, "EQ1")
        result = SelectionResult(record=rec, scale_factor=1.0, match_error=0.02, deviations={0.5: 0.05})
        panel.set_results([result], database=object())
        panel._dir_edit.setText(str(tmp_path))
        panel._wave_fmt_combo.setCurrentIndex(0)

        added = []

        class DummyCombiner:
            def __init__(self, output_dir):
                self.output_dir = output_dir
                self.groups = [SimpleNamespace(name="G1", h1=_make_sig("art1"))]

            def add_natural(self, r, db):
                added.append((r.record.rsn, db))

            def add_artificial(self, h1, index):
                added.append((h1.name, index))

            def export(self, fmt="at2"):
                return None

            def report_text(self):
                return "dummy report"

        monkeypatch.setattr("seiswave.gui.panels.result_panel.Combiner", DummyCombiner)
        monkeypatch.setattr(panel, "_export_comparison_plot", lambda out_dir, combiner: None)
        monkeypatch.setattr(panel, "_export_spectra_csv", lambda out_dir, combiner: None)
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.information", lambda *a: None)
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.critical", lambda *a: None)
        panel._do_export()

        assert panel._combiner is not None
        assert added[0][0] == 1

    def test_generate_report_preview_and_save_extra(self, qapp, monkeypatch, tmp_path):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        rec = _make_record(2, "EQ2")
        result = SelectionResult(record=rec, scale_factor=1.0, match_error=0.02, deviations={0.5: 0.05})
        panel.set_results([result])
        panel.add_generated_wave(_make_sig("art1"))
        panel.set_code_spectrum(np.array([0.1, 0.5]), np.array([0.2, 0.3]))
        panel._dir_edit.setText(str(tmp_path))

        infos = []
        monkeypatch.setattr("seiswave.gui.panels.result_panel.QMessageBox.information", lambda *a: infos.append(a[-1]))
        panel._generate_report()

        preview = panel._preview.toPlainText()
        assert "SeisWave" in preview
        assert ("EQ2" in preview) or ("RSN2" in preview)
        assert "art1" in preview
        assert any("report" in str(msg).lower() for msg in infos)
