import numpy as np
import pytest
from types import SimpleNamespace
from PySide6.QtWidgets import QTableWidgetItem

from seiswave.core.peer_db import PeerRecord
from seiswave.core.selector import SelectionResult
from seiswave.gui.workers import (
    CombinerWorker,
    PeerIndexWorker,
    PeerLoadWorker,
    PeerSelectWorker,
    SelectorWorker,
    SpectraPrecomputeWorker,
)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_sig(name="sig", dt=0.02):
    from seiswave.core import EQSignal

    acc = np.sin(np.linspace(0, 2, 128)) * 0.1
    return EQSignal(acc, dt, name=name)


def _make_record(rsn=1, name="EQ"):
    return PeerRecord(
        rsn=rsn,
        event=name,
        station=f"STA{rsn}",
        component="H1",
        direction="H",
        dt=0.02,
        npts=200,
        pga=0.2,
        duration=10.0,
        eff_duration=8.0,
        sa=np.array([0.2, 0.3, 0.25]),
        acc=np.array([0.0, 0.1]),
    )


class TestMoreWorkers:
    def test_peer_load_worker_builds_index_and_precomputes(self, monkeypatch):
        class FakeDB:
            def __init__(self, data_dir=None):
                self.records = [1, 2, 3]
                self.precompute_calls = []
            def load_index(self):
                return False
            def build_index(self):
                self.built = True
            def __len__(self):
                return len(self.records)
            def load_spectra_cache(self, zeta):
                return False
            def precompute_spectra(self, periods, zeta, progress_cb=None):
                self.precompute_calls.append((periods, zeta))
                progress_cb(2, 4)

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerLoadWorker("/tmp/fake")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        db = worker.execute()

        assert isinstance(db, FakeDB)
        assert getattr(db, "built", False) is True
        assert db.precompute_calls
        assert progress[0] == (10, "检查索引缓存...")
        assert progress[-1] == (100, "加载完成")

    def test_peer_index_worker_uses_cache_shortcut(self, monkeypatch):
        class FakeDB:
            def __init__(self, data_dir=None):
                self.records = [1, 2]
            def load_index(self):
                return True
            def __len__(self):
                return len(self.records)

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerIndexWorker("/tmp/fake")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        db = worker.execute()

        assert isinstance(db, FakeDB)
        assert progress == [(5, "检查索引缓存..."), (100, "从缓存加载 2 条记录")]

    def test_spectra_precompute_worker_uses_cache_when_available(self):
        records = [SimpleNamespace(sa=np.array([1.0])), SimpleNamespace(sa=None)]
        db = SimpleNamespace(records=records, load_spectra_cache=lambda z: True)
        worker = SpectraPrecomputeWorker(db)
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        result = worker.execute()

        assert result is db
        assert progress == [(5, "检查反应谱缓存..."), (100, "从缓存加载 1 条反应谱")]

    def test_peer_select_worker_delegates_to_wave_selector(self, monkeypatch):
        result = ["r1", "r2"]

        class FakeSelector:
            def __init__(self, config):
                self.config = config
            def select(self, db, progress_cb=None):
                progress_cb(2, 5)
                return result

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        worker = PeerSelectWorker(config="cfg", database="db")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        out = worker.execute()

        assert out == result
        assert progress == [(40, "筛选 2/5")]

    def test_selector_worker_emits_completion_progress(self, monkeypatch):
        result = [1, 2, 3]

        class FakeSelector:
            def __init__(self, config):
                self.config = config
            def select(self, db, progress_cb=None):
                progress_cb(1, 4)
                return result

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        worker = SelectorWorker(config="cfg", database="db")
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        out = worker.execute()

        assert out == result
        assert progress[-1] == (100, "选波完成: 3 条")

    def test_peer_load_worker_raises_on_cancel_during_precompute(self, monkeypatch):
        class FakeDB:
            def __init__(self, data_dir=None):
                self.records = [1]
            def load_index(self):
                return True
            def __len__(self):
                return len(self.records)
            def load_spectra_cache(self, zeta):
                return False
            def precompute_spectra(self, periods, zeta, progress_cb=None):
                progress_cb(1, 2)

        monkeypatch.setattr("seiswave.core.peer_db.PeerDatabase", FakeDB)
        worker = PeerLoadWorker("/tmp/fake")
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_spectra_precompute_worker_raises_on_cancel(self):
        class FakeDB:
            def __init__(self):
                self.records = []
            def load_spectra_cache(self, zeta):
                return False
            def precompute_spectra(self, periods, zeta, progress_cb=None):
                progress_cb(1, 2)

        worker = SpectraPrecomputeWorker(FakeDB())
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_selector_worker_raises_on_cancel_from_progress_callback(self, monkeypatch):
        class FakeSelector:
            def __init__(self, config):
                self.config = config
            def select(self, db, progress_cb=None):
                progress_cb(1, 3)
                return []

        monkeypatch.setattr("seiswave.core.selector.WaveSelector", FakeSelector)
        worker = SelectorWorker(config="cfg", database="db")
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_combiner_worker_stops_when_cancelled_before_loop(self, monkeypatch):
        class FakeCombiner:
            def __init__(self, output_dir=None):
                self.output_dir = output_dir
            def add_natural(self, r, db):
                raise AssertionError("should not reach add_natural")

        monkeypatch.setattr("seiswave.core.combiner.Combiner", FakeCombiner)
        worker = CombinerWorker(
            results=["r1"],
            database="db",
            generated_waves=[],
            output_dir="/tmp/out",
        )
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_combiner_worker_adds_waves_and_generates_report(self, monkeypatch):
        class FakeCombiner:
            def __init__(self, output_dir=None):
                self.output_dir = output_dir
                self.natural = []
                self.artificial = []
            def add_natural(self, r, db):
                self.natural.append((r, db))
            def add_artificial(self, h1=None, name=None, index=None):
                self.artificial.append((h1, name, index))
            def export(self, fmt='at2'):
                self.fmt = fmt
            def generate_html_report(self, sa, periods):
                return "/tmp/fake_report.html"

        monkeypatch.setattr("seiswave.core.combiner.Combiner", FakeCombiner)
        sig = _make_sig("art")
        worker = CombinerWorker(
            results=["r1"],
            database="db",
            generated_waves=[sig],
            output_dir="/tmp/out",
            fmt="txt",
            target_sa=np.array([0.2, 0.3]),
            periods=np.array([0.1, 0.5]),
        )
        progress = []
        worker.signals.progress.connect(lambda pct, text: progress.append((pct, text)))
        out = worker.execute()

        assert out["output_dir"] == "/tmp/out"
        assert out["report_path"] == "/tmp/fake_report.html"
        assert out["combiner"].natural == [("r1", "db")]
        assert out["combiner"].artificial[0][2] == 0
        assert progress[-1] == (100, "组合输出完成")


class TestCombinePanel:
    def test_refresh_table_counts_natural_and_artificial(self, qapp):
        from seiswave.gui.panels.combine_panel import CombinePanel

        panel = CombinePanel()
        result = SelectionResult(record=_make_record(1), scale_factor=1.2, match_error=0.05, deviations={1.0: 0.1})
        panel.set_results([result], database="db")
        panel.add_generated_wave(_make_sig("art1"))

    def test_refresh_table_counts_natural_and_artificial(self, qapp):
        from seiswave.gui.panels.combine_panel import CombinePanel

        panel = CombinePanel()
        result = SelectionResult(record=_make_record(1), scale_factor=1.2, match_error=0.05, deviations={1.0: 0.1})
        panel.set_results([result], database="db")
        panel.add_generated_wave(_make_sig("art1"))

        # 简表已移除（详细列表见汇总面板），仅保留数量统计标签
        assert panel._count_label.text() == "天然波: 1  人工波: 1  合计: 2"
        assert not hasattr(panel, "_table")

    def test_do_validate_warns_without_target_or_waves(self, qapp, monkeypatch):
        from seiswave.gui.panels.combine_panel import CombinePanel

        panel = CombinePanel()
        warnings = []
        monkeypatch.setattr("seiswave.gui.panels.combine_panel.QMessageBox.warning", lambda *a: warnings.append(a[-1]))
        panel._do_validate()
        assert warnings == ["请先设置目标谱"]

        panel.set_code_spectrum(np.array([0.1, 0.5]), np.array([0.2, 0.3]))
        panel._do_validate()
        assert warnings[-1] == "没有可校核的波形"

    def test_do_validate_formats_result(self, qapp, monkeypatch):
        from seiswave.gui.panels.combine_panel import CombinePanel

        validate_result = SimpleNamespace(
            passed=True,
            n_groups=3,
            n_required=3,
            mean_check=True,
            mean_ratios=np.array([0.9, 1.1]),
            individual_checks=[("w1", (0.8, 1.2), True)],
            messages=["all good"],
        )
        panel = CombinePanel()
        panel.set_code_spectrum(np.array([0.1, 0.5]), np.array([0.2, 0.3]))
        panel._generated_waves = [_make_sig("art1")]
        monkeypatch.setattr(panel, "_build_combiner", lambda: SimpleNamespace(validate=lambda pga, sa, periods: validate_result))
        panel._do_validate()

        text = panel._validate_label.text()
        assert "校核结果: 通过" in text
        assert "平均谱最小比值: 0.900" in text
        assert "all good" in text

    def test_do_export_warns_without_dir(self, qapp, monkeypatch):
        from seiswave.gui.panels.combine_panel import CombinePanel

        panel = CombinePanel()
        panel._generated_waves = [_make_sig("art1")]
        warnings = []
        monkeypatch.setattr("seiswave.gui.panels.combine_panel.QMessageBox.warning", lambda *a: warnings.append(a[-1]))
        panel._do_export()
        assert warnings == ["请先选择输出目录"]

    def test_do_export_runs_combiner_and_reports_html(self, qapp, monkeypatch, tmp_path):
        from seiswave.gui.panels.combine_panel import CombinePanel

        fake_combiner = SimpleNamespace(
            groups=[1, 2],
            export=lambda fmt='at2': None,
            generate_html_report=lambda sa, periods: str(tmp_path / "report.html"),
        )
        infos = []
        panel = CombinePanel()
        panel._dir_edit.setText(str(tmp_path))
        panel._generated_waves = [_make_sig("art1")]
        panel.set_code_spectrum(np.array([0.1, 0.5]), np.array([0.2, 0.3]))
        monkeypatch.setattr(panel, "_build_combiner", lambda: fake_combiner)
        monkeypatch.setattr("seiswave.gui.panels.combine_panel.QMessageBox.information", lambda *a: infos.append(a[-1]))
        panel._do_export()

        assert panel._combiner is fake_combiner
        assert any("report.html" in msg for msg in infos)


class TestSelectorPanel:
    def test_source_switch_and_imported_signals(self, qapp, monkeypatch):
        from seiswave.gui.panels.selector_panel import SelectorPanel

        class FakeSpec:
            def __init__(self):
                self.sa = np.array([0.2] * 200)

        monkeypatch.setattr("seiswave.gui.panels.selector_panel.Spectra.compute", lambda acc, dt, periods, zeta: FakeSpec())
        panel = SelectorPanel()
        sig = _make_sig("imported")
        panel.set_imported_signals([sig])
        panel._source_combo.setCurrentIndex(1)

        assert len(panel._imported_db.records) == 1
        assert "导入候选库：1 条" in panel._db_label.text()
        assert panel.get_database() is panel._imported_db

    def test_apply_filter_uses_database_filter(self, qapp):
        from seiswave.gui.panels.selector_panel import SelectorPanel

        panel = SelectorPanel()
        rec = _make_record(5, "EventX")

        class FakeDB:
            def __len__(self):
                return 1
            def filter(self, **kwargs):
                return [rec]

        panel._db = FakeDB()
        panel._rsn_filter.setText("5")
        panel._event_filter.setText("Event")
        panel._apply_filter()
        assert panel._browse_table.rowCount() == 1
        assert panel._browse_table.item(0, 1).text() == "EventX"

    def test_run_selection_warns_for_missing_inputs(self, qapp, monkeypatch):
        from seiswave.gui.panels.selector_panel import SelectorPanel

        panel = SelectorPanel()
        warnings = []
        monkeypatch.setattr("seiswave.gui.panels.selector_panel.QMessageBox.warning", lambda *a: warnings.append(a[-1]))
        panel._run_selection()
        assert warnings == ["请先设置规范谱参数"]

        panel.set_code_spectrum(np.array([0.1, 0.5]), np.array([0.2, 0.3]))

        class EmptyDB:
            def __len__(self):
                return 0

        panel._db = EmptyDB()
        panel._run_selection()
        assert warnings[-1] == "当前数据源无候选记录"

    def test_selection_done_populates_result_table_and_emits(self, qapp):
        from seiswave.gui.panels.selector_panel import SelectorPanel

        panel = SelectorPanel()
        rec = _make_record(8, "EQ8")
        result = SelectionResult(record=rec, scale_factor=1.1, match_error=0.02, deviations={1.0: 0.1, 2.0: 0.2})
        panel.set_code_spectrum(np.array([0.1, 0.5, 1.0]), np.array([0.2, 0.3, 0.25]))
        panel._db = SimpleNamespace(spectra_periods=np.array([0.1, 0.5, 1.0]))
        emitted = []
        panel.selection_done.connect(lambda items: emitted.append(items))
        panel._on_selection_done([result])

        assert panel.get_results() == [result]
        assert panel._result_table.rowCount() == 1
        assert panel._stat_label.text() == "选中 1 条地震波"
        assert emitted == [[result]]

    def test_selection_error_updates_label(self, qapp, monkeypatch):
        from seiswave.gui.panels.selector_panel import SelectorPanel

        panel = SelectorPanel()
        errors = []
        monkeypatch.setattr("seiswave.gui.panels.selector_panel.QMessageBox.critical", lambda *a: errors.append(a[-1]))
        panel._on_selection_error("boom")
        assert panel._stat_label.text() == "选波出错: boom"
        assert errors == ["选波失败:\nboom"]


class TestSpectrumPanel:
    def test_code_switch_updates_visibility_and_isolation_flags(self, qapp):
        from seiswave.gui.panels.spectrum_panel import SpectrumPanel

        panel = SpectrumPanel()
        panel._on_code_changed(1)
        assert panel._gb_group.isHidden() is False
        assert panel._iso_group.isHidden() is False
        assert panel.is_isolation_mode() is False

        panel._code_combo.setCurrentIndex(1)
        panel._on_code_changed(1)
        t_before, t_after = panel.get_isolation_periods()
        assert panel.is_isolation_mode() is True
        assert (t_before, t_after) == (1.0, 3.0)

        panel._on_code_changed(2)
        assert panel._gb_group.isHidden() is True
        assert panel._custom_group.isHidden() is False

    def test_custom_spectrum_with_insufficient_data_clears_plot(self, qapp, monkeypatch):
        from seiswave.gui.panels.spectrum_panel import SpectrumPanel

        panel = SpectrumPanel()
        calls = {"clear": 0, "refresh": 0}
        monkeypatch.setattr(panel._plot, "clear", lambda: calls.__setitem__("clear", calls["clear"] + 1))
        monkeypatch.setattr(panel._plot, "refresh", lambda: calls.__setitem__("refresh", calls["refresh"] + 1))
        panel._code_combo.setCurrentIndex(2)
        panel._on_code_changed(2)
        panel._custom_table.setRowCount(1)
        panel._custom_table.setItem(0, 0, None)
        panel._custom_table.setItem(0, 1, None)
        panel._update_spectrum()

        assert calls["clear"] >= 1
        assert calls["refresh"] >= 1
        assert "请输入自定义谱数据或导入 CSV" in panel._info_label.text()

    def test_compute_custom_spectrum_ignores_bad_rows(self, qapp, monkeypatch):
        from seiswave.gui.panels.spectrum_panel import SpectrumPanel

        captured = {}

        def fake_from_custom(periods, sa, full_periods):
            captured["periods"] = periods.copy()
            captured["sa"] = sa.copy()
            return np.ones_like(full_periods) * 0.42

        monkeypatch.setattr("seiswave.gui.panels.spectrum_panel.CodeSpectrum.from_custom", fake_from_custom)
        panel = SpectrumPanel()
        panel._custom_table.setRowCount(3)
        panel._custom_table.setItem(0, 0, QTableWidgetItem("0.1"))
        panel._custom_table.setItem(0, 1, QTableWidgetItem("0.2"))
        panel._custom_table.setItem(1, 0, QTableWidgetItem("bad"))
        panel._custom_table.setItem(1, 1, QTableWidgetItem("0.3"))
        panel._custom_table.setItem(2, 0, QTableWidgetItem("0.5"))
        panel._custom_table.setItem(2, 1, QTableWidgetItem("0.6"))

        sa = panel._compute_custom_spectrum()
        assert np.allclose(sa, 0.42)
        assert np.allclose(captured["periods"], np.array([0.1, 0.5]))
        assert np.allclose(captured["sa"], np.array([0.2, 0.6]))

    def test_import_csv_populates_table_and_export_writes_csv(self, qapp, monkeypatch, tmp_path):
        from seiswave.gui.panels.spectrum_panel import SpectrumPanel

        writes = []
        monkeypatch.setattr("seiswave.gui.panels.spectrum_panel.QFileDialog.getOpenFileName", lambda *a, **k: ("/tmp/spec.csv", "csv"))
        monkeypatch.setattr("seiswave.gui.panels.spectrum_panel.CodeSpectrum.from_csv", lambda path: (np.array([0.1, 0.5]), np.array([0.2, 0.4])))
        monkeypatch.setattr("seiswave.core.FileIO.write_csv", lambda path, **cols: writes.append((path, cols)))
        monkeypatch.setattr("seiswave.gui.panels.spectrum_panel.QFileDialog.getSaveFileName", lambda *a, **k: (str(tmp_path / "out.csv"), "csv"))

        panel = SpectrumPanel()
        panel._import_csv()
        assert panel._custom_table.rowCount() == 2
        assert panel._custom_table.item(1, 1).text() == "0.400000"

        panel._export_spectrum()
        assert writes
        assert writes[0][0].endswith("out.csv")
        assert "T" in writes[0][1] and "Sa" in writes[0][1]

    def test_set_dark_recomputes_and_delegates(self, qapp, monkeypatch):
        from seiswave.gui.panels.spectrum_panel import SpectrumPanel

        panel = SpectrumPanel()
        called = {"dark": [], "update": 0}
        monkeypatch.setattr(panel._plot, "set_dark", lambda dark: called["dark"].append(dark))
        monkeypatch.setattr(panel, "_update_spectrum", lambda *a: called.__setitem__("update", called["update"] + 1))
        panel.set_dark(True)

        assert called["dark"] == [True]
        assert called["update"] == 1


class TestSpectrumSidebar:
    def test_code_switch_and_params(self, qapp):
        from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar

        sb = SpectrumSidebar()
        sb._on_code_changed(1)
        assert sb._gb_group.isHidden() is False
        assert sb._iso_group.isHidden() is False
        assert sb._custom_group.isHidden() is True

        sb._on_code_changed(2)
        assert sb._gb_group.isHidden() is True
        assert sb._iso_group.isHidden() is True
        assert sb._custom_group.isHidden() is False

        sb._on_code_changed(0)
        assert sb._gb_group.isHidden() is False
        assert sb._iso_group.isHidden() is True

    def test_get_gb_params(self, qapp):
        from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar

        sb = SpectrumSidebar()
        sb._intensity_combo.setCurrentIndex(3)
        sb._group_combo.setCurrentIndex(1)
        sb._site_combo.setCurrentIndex(2)
        sb._level_combo.setCurrentIndex(1)
        sb._zeta_spin.setValue(0.03)

        params = sb._get_gb_params()
        assert params['intensity'] == 8
        assert params['group'] == 2
        assert params['site_class'] == 'II'
        assert params['level'] == 'basic'
        assert params['zeta'] == 0.03

    def test_update_spectrum_emits_signal(self, qapp, monkeypatch):
        from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar

        sb = SpectrumSidebar()
        emitted = []
        sb.spectrum_changed.connect(lambda p, sa: emitted.append((len(p), len(sa))))
        sb._update_spectrum()

        assert len(emitted) == 1
        assert emitted[0][0] == emitted[0][1]
        assert emitted[0][0] > 0

    def test_update_spectrum_ignores_bad_custom(self, qapp, monkeypatch):
        from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar

        sb = SpectrumSidebar()
        sb._code_combo.setCurrentIndex(2)
        sb._on_code_changed(2)
        sb._custom_table.setRowCount(1)
        sb._update_spectrum()
        assert "请输入自定义谱数据或导入 CSV" in sb._info_label.text()

    def test_custom_row_add_and_delete(self, qapp):
        from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar

        sb = SpectrumSidebar()
        sb._code_combo.setCurrentIndex(2)
        sb._on_code_changed(2)
        sb._add_custom_row()
        sb._add_custom_row()
        assert sb._custom_table.rowCount() == 2

        sb._custom_table.selectRow(0)
        sb._del_custom_row()
        assert sb._custom_table.rowCount() == 1

    def test_import_csv_populates_table(self, qapp, monkeypatch):
        from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar

        sb = SpectrumSidebar()
        sb._code_combo.setCurrentIndex(2)
        sb._on_code_changed(2)
        monkeypatch.setattr("seiswave.gui.panels.spectrum_sidebar.QFileDialog.getOpenFileName", lambda *a, **k: ("/tmp/spec.csv", "csv"))
        monkeypatch.setattr("seiswave.gui.panels.spectrum_sidebar.CodeSpectrum.from_csv", lambda path: (np.array([0.1, 0.5]), np.array([0.2, 0.4])))
        sb._import_csv()
        assert sb._custom_table.rowCount() == 2
        assert sb._custom_table.item(1, 1).text() == "0.400000"

    def test_export_spectrum(self, qapp, monkeypatch, tmp_path):
        from seiswave.gui.panels.spectrum_sidebar import SpectrumSidebar

        sb = SpectrumSidebar()
        sb._current_sa = np.array([0.2, 0.3])
        sb._periods = np.array([0.1, 0.5])
        writes = []
        monkeypatch.setattr("seiswave.core.FileIO.write_csv", lambda path, **cols: writes.append((path, list(cols.keys()))))
        monkeypatch.setattr("seiswave.gui.panels.spectrum_sidebar.QFileDialog.getSaveFileName", lambda *a, **k: (str(tmp_path / "out.csv"), "csv"))
        sb._export_spectrum()
        assert writes
        assert "T" in writes[0][1] and "Sa" in writes[0][1]
