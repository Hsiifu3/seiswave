"""Phase 3 first-batch workbench tool tests."""

from __future__ import annotations

import csv
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from seiswave.core.code_spec import CodeSpectrum
from seiswave.core.io import FileIO
from seiswave.core.signal_pool import SignalPool, SignalRecord
from seiswave.core.target_spectrum import TargetSpectrumService
from seiswave.core.spectrum import Spectra
from seiswave.gui.workbench.app_window import AppWindow


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_record(name: str, scale: float, kind: str = "natural") -> SignalRecord:
    time = np.linspace(0.0, 8.0, 801)
    acc = scale * (
        0.18 * np.sin(2.0 * np.pi * 1.1 * time)
        + 0.06 * np.sin(2.0 * np.pi * 3.2 * time + 0.4)
    )
    return SignalRecord(
        acc=acc,
        dt=float(time[1] - time[0]),
        name=name,
        kind=kind,
        meta={"source": "unit-test"},
    )


def _build_window() -> tuple[AppWindow, SignalPool, TargetSpectrumService]:
    periods = np.array([0.1, 0.2, 0.5, 1.0, 2.0], dtype=np.float64)
    pool = SignalPool()
    record_a = _make_record("RSN-A", 1.0)
    record_b = _make_record("RSN-B", 0.8)
    pool.add(record_a)
    pool.add(record_b)
    target = TargetSpectrumService(periods=periods)
    target.set_custom(periods, np.array([0.25, 0.40, 0.31, 0.22, 0.10]))
    window = AppWindow(pool=pool, target_service=target)
    pool.set_selection([record_a.id, record_b.id])
    return window, pool, target


def _make_peer_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "peer_db"
    directory.mkdir()
    specs = [
        ("RSN1_TEST_EVENT_A_H1.AT2", 1.00),
        ("RSN2_TEST_EVENT_B_H1.AT2", 0.92),
        ("RSN3_TEST_EVENT_C_H1.AT2", 0.86),
        ("RSN4_TEST_EVENT_D_H1.AT2", 1.08),
    ]
    time = np.linspace(0.0, 20.0, 2001)
    base = 0.15 * np.sin(2.0 * np.pi * 1.0 * time) + 0.05 * np.sin(
        2.0 * np.pi * 2.5 * time + 0.4
    )
    for filename, scale in specs:
        FileIO.write_at2(directory / filename, base * scale, float(time[1] - time[0]))
    return directory


def _make_target_for_tool(periods: np.ndarray) -> np.ndarray:
    params = CodeSpectrum.get_params(intensity=8, group=2, site_class="II", level="frequent")
    return CodeSpectrum.gb50011(periods, params["Tg"], params["alpha_max"], zeta=0.05)


class TestWorkbenchTools:
    def test_spectra_tool_pushes_preview_options(self, qapp):
        window, pool, _target = _build_window()
        try:
            window.set_current_tool("反应谱")
            tool = window._tool_dock._tool_widgets["反应谱"]
            tool._triple_log_check.setChecked(True)
            tool._damping_combo.setCurrentIndex(tool._damping_combo.findData("multi"))

            snapshot = tool.run_tool()
            qapp.processEvents()

            assert snapshot["triple_log"] is True
            assert snapshot["damping_mode"] == "multi"
            assert len(window._preview_panel.spectrum_axes()) == 3
            assert snapshot["periods"].size == len(_target.periods())
            assert set(snapshot["mean_spectra"].keys()) == {0.02, 0.05, 0.10}
        finally:
            window.close()

    def test_plot_export_tool_writes_png_pdf_svg(self, qapp, tmp_path):
        window, pool, target = _build_window()
        try:
            pool.set_selection([pool.all()[0].id])
            window._preview_panel.refresh_from_services()
            export_tool = window._tool_dock._plot_export_tool
            export_tool._dir_edit.setText(str(tmp_path))
            export_tool._prefix_edit.setText("toolplot")
            export_tool._view_combo.setCurrentIndex(
                export_tool._view_combo.findData("all")
            )

            written = []
            for fmt in ("png", "pdf", "svg"):
                export_tool._format_combo.setCurrentIndex(
                    export_tool._format_combo.findData(fmt)
                )
                written.extend(export_tool.export())

            assert len(written) == 12
            for path in written:
                assert path.exists()
                assert path.stat().st_size > 0
        finally:
            window.close()

    def test_data_export_tool_writes_series_spectrum_and_scorecard(self, qapp, tmp_path):
        window, pool, target = _build_window()
        try:
            pool.set_selection([record.id for record in pool.all()])
            window._preview_panel.refresh_from_services()
            export_tool = window._tool_dock._data_export_tool
            export_tool._dir_edit.setText(str(tmp_path))
            export_tool._prefix_edit.setText("dataset")

            export_tool._content_combo.setCurrentIndex(
                export_tool._content_combo.findData("acc")
            )
            export_tool._format_combo.setCurrentIndex(
                export_tool._format_combo.findData("csv")
            )
            acc_files = export_tool.export()
            assert len(acc_files) == 2
            first_csv = acc_files[0].read_text(encoding="utf-8").splitlines()[0]
            assert "time" in first_csv and "acc" in first_csv

            export_tool._content_combo.setCurrentIndex(
                export_tool._content_combo.findData("spectrum")
            )
            export_tool._format_combo.setCurrentIndex(
                export_tool._format_combo.findData("txt")
            )
            spectrum_files = export_tool.export()
            assert len(spectrum_files) == 1
            spectrum_text = spectrum_files[0].read_text(encoding="utf-8")
            assert "period" in spectrum_text and "target_sa" in spectrum_text

            export_tool._content_combo.setCurrentIndex(
                export_tool._content_combo.findData("scorecard")
            )
            export_tool._format_combo.setCurrentIndex(
                export_tool._format_combo.findData("csv")
            )
            scorecard_files = export_tool.export()
            assert len(scorecard_files) == 1
            with scorecard_files[0].open("r", encoding="utf-8") as file_obj:
                rows = list(csv.DictReader(file_obj))
            assert len(rows) == 2
            assert {"id", "name", "mean_error_pct", "pga"} <= set(rows[0].keys())
        finally:
            window.close()

    def test_import_tool_loads_at2_and_txt_into_pool(self, qapp, tmp_path):
        pool = SignalPool()
        target = TargetSpectrumService(periods=np.array([0.1, 0.2, 0.5]))
        window = AppWindow(pool=pool, target_service=target)
        try:
            acc = np.array([0.0, 0.1, -0.05, 0.2, 0.0], dtype=np.float64)
            at2_path = tmp_path / "sample.AT2"
            txt_path = tmp_path / "sample.txt"
            FileIO.write_at2(at2_path, acc, 0.02)
            data = np.column_stack([np.arange(len(acc)) * 0.01, acc * 2.0])
            np.savetxt(txt_path, data, fmt="%15.7E")

            import_tool = window._tool_dock._tool_widgets["导入"]
            import_tool._mode_combo.setCurrentIndex(
                import_tool._mode_combo.findData("directory")
            )
            import_tool._pattern_combo.setCurrentIndex(
                import_tool._pattern_combo.findData("auto")
            )
            import_tool._path_edit.setText(str(tmp_path))

            records = import_tool.run_tool()
            qapp.processEvents()

            assert len(records) == 2
            assert len(pool.all()) == 2
            names = {record.name for record in pool.all()}
            assert names == {"sample", "sample"}
            dts = sorted(record.dt for record in pool.all())
            assert dts == pytest.approx([0.01, 0.02])
            for record in pool.all():
                assert "file_name" in record.meta
                assert Path(record.meta["filepath"]).exists()
            assert len(pool.selection()) == 2
        finally:
            window.close()

    def test_baseline_and_filter_tools_derive_records_with_provenance(self, qapp):
        window, pool, _target = _build_window()
        try:
            original = pool.all()[0]
            pool.set_selection([original.id])

            baseline_tool = window._tool_dock._tool_widgets["基线校正"]
            baseline_tool._baseline_combo.setCurrentIndex(
                baseline_tool._baseline_combo.findData("poly")
            )
            baseline_tool._poly_order_spin.setValue(1)
            baseline_children = baseline_tool.run_tool()
            qapp.processEvents()

            assert len(baseline_children) == 1
            baseline_child = baseline_children[0]
            assert baseline_child.parent_id == original.id
            assert baseline_child.kind == "processed"
            assert not np.allclose(baseline_child.acc, original.acc)
            assert baseline_child.meta["operation"] == "baseline_correction"
            assert baseline_child.meta["provenance"][-1]["method"] == "poly"

            pool.set_selection([original.id])
            filter_tool = window._tool_dock._tool_widgets["滤波"]
            filter_tool._filter_type_combo.setCurrentIndex(
                filter_tool._filter_type_combo.findData("highpass")
            )
            filter_tool._filter_order_spin.setValue(4)
            filter_tool._f1_spin.setValue(0.2)
            filter_tool._f2_spin.setValue(20.0)
            filter_children = filter_tool.run_tool()
            qapp.processEvents()

            assert len(filter_children) == 1
            filter_child = filter_children[0]
            assert filter_child.parent_id == original.id
            assert filter_child.kind == "processed"
            assert not np.allclose(filter_child.acc, original.acc)
            assert filter_child.meta["operation"] == "filter"
            assert filter_child.meta["provenance"][-1]["ftype"] == "highpass"
        finally:
            window.close()

    def test_spectral_match_tool_derives_record_with_lower_rmse(self, qapp):
        window, pool, target = _build_window()
        try:
            original = pool.all()[0]
            pool.set_selection([original.id])
            tool = window._tool_dock._tool_widgets["谱拟合"]
            tool._iter_spin.setValue(8)

            periods = target.periods()
            before = original.spectrum(periods, zeta=0.05).sa
            before_rmse = np.sqrt(
                np.mean(((before - target.sa()) / np.maximum(target.sa(), 1e-12)) ** 2)
            )

            children = tool.run_tool()
            qapp.processEvents()

            assert len(children) == 1
            child = children[0]
            after = child.spectrum(periods, zeta=0.05).sa
            after_rmse = np.sqrt(
                np.mean(((after - target.sa()) / np.maximum(target.sa(), 1e-12)) ** 2)
            )
            assert child.kind == "processed"
            assert child.meta["operation"] == "spectral_match"
            assert child.meta["match_rmse_after"] < child.meta["match_rmse_before"]
            assert after_rmse < before_rmse
        finally:
            window.close()

    def test_artificial_tool_generates_general_ff_nf_nfp_with_metadata(self, qapp):
        window, pool, target = _build_window()
        try:
            tool = window._tool_dock._tool_widgets["人工波生成"]
            # n=512 (dt=0.02 → 10.2s)：NFP 需容纳 γ·Tp≈7.2s 的脉冲(Mw7, γ=1.8)
            tool._n_spin.setValue(512)
            tool._iter_spin.setValue(4)
            tool._trials_spin.setValue(1)

            cases = [
                ("general", "一般人工波", False),
                ("FF", "远场 FF", False),
                ("NF", "近场 NF", False),
                ("NFP", "近场脉冲 NFP", True),
            ]

            created = []
            for data, _label, expect_pulse in cases:
                index = tool._type_combo.findData(data)
                tool._type_combo.setCurrentIndex(index)
                tool._refresh_mode_ui()
                result = tool.run_tool()
                qapp.processEvents()
                assert len(result) == 1
                record = result[0]
                created.append(record)
                assert record.kind == "artificial"
                assert record.meta["generation_type"] == data
                assert record.meta["source"] == "artificial_generation"
                assert record.meta["pulse"] is expect_pulse
                assert np.max(np.abs(record.acc)) > 0
                assert record.spectrum(target.periods(), zeta=0.05).sa.max() > 0
                if data == "general":
                    assert record.meta["spectrum_source"] == "custom"
                else:
                    assert "near_field_factor" in record.meta
                    assert record.meta["spectrum_source"] == "code"
            assert len(created) == 4
        finally:
            window.close()

    def test_auto_select_tool_from_pool_returns_n_records_with_rmse_metadata(self, qapp):
        window, pool, target = _build_window()
        try:
            target.set_from_record(pool.all()[0], periods=target.periods(), zeta=0.05)
            tool = window._tool_dock._tool_widgets["自动选波"]
            tool._source_combo.setCurrentIndex(tool._source_combo.findData("pool"))
            tool._refresh_source_ui()
            tool._n_select_spin.setValue(2)
            tool._tol_spin.setValue(0.60)
            tool._dur_factor_spin.setValue(1.0)
            tool._scale_lo_spin.setValue(0.1)
            tool._scale_hi_spin.setValue(10.0)

            records = tool.run_tool()
            qapp.processEvents()

            assert len(records) == 2
            for record in records:
                assert record.kind == "natural"
                assert record.meta["operation"] == "auto_select"
                assert record.meta["match_rmse"] < 0.60
        finally:
            window.close()

    def test_auto_select_tool_from_peer_directory_returns_n_records(self, qapp, tmp_path):
        periods = Spectra.default_periods(0.04, 3.0, 60, mode="mixed")
        pool = SignalPool()
        target = TargetSpectrumService(periods=periods)
        time = np.linspace(0.0, 20.0, 2001)
        base = 0.15 * np.sin(2.0 * np.pi * 1.0 * time) + 0.05 * np.sin(
            2.0 * np.pi * 2.5 * time + 0.4
        )
        reference = SignalRecord(
            acc=base,
            dt=float(time[1] - time[0]),
            name="peer-ref",
            kind="natural",
        )
        target.set_from_record(reference, periods=periods, zeta=0.05)
        window = AppWindow(pool=pool, target_service=target)
        try:
            peer_dir = _make_peer_dir(tmp_path)
            tool = window._tool_dock._tool_widgets["自动选波"]
            tool._source_combo.setCurrentIndex(tool._source_combo.findData("peer"))
            tool._path_edit.setText(str(peer_dir))
            tool._n_select_spin.setValue(3)
            tool._tol_spin.setValue(0.80)
            tool._dur_factor_spin.setValue(1.0)

            records = tool.run_tool()
            qapp.processEvents()

            assert len(records) == 3
            assert len(pool.all()) == 3
            for record in records:
                assert record.meta["selector_source"] == "peer"
                assert record.meta["match_rmse"] < 0.80
        finally:
            window.close()

    def test_combine_tool_validates_and_exports_selected_records(self, qapp, tmp_path):
        periods = Spectra.default_periods(0.04, 3.0, 60, mode="mixed")
        target_sa = _make_target_for_tool(periods)
        target = TargetSpectrumService(periods=periods)
        target.set_custom(periods, target_sa)
        pool = SignalPool()
        source = _make_record("Combo-Base", 1.0)
        for index in range(7):
            pool.add(
                SignalRecord(
                    acc=source.acc.copy(),
                    dt=source.dt,
                    name=f"Combo-{index+1}",
                    kind="natural" if index < 5 else "artificial",
                    meta={
                        "source": "unit-test",
                        "rsn": index + 1,
                        "match_rmse": 0.05,
                    },
                )
            )
        window = AppWindow(pool=pool, target_service=target)
        try:
            pool.set_selection([record.id for record in pool.all()])
            tool = window._tool_dock._tool_widgets["组合校核"]
            tool._dir_edit.setText(str(tmp_path))
            tool._fmt_combo.setCurrentIndex(tool._fmt_combo.findData("both"))
            tool._html_check.setChecked(True)

            result = tool.run_tool()
            qapp.processEvents()

            assert result is not None
            validation = result["validation"]
            assert validation.n_groups == 7
            assert result["output_dir"] is not None
            out_dir = Path(result["output_dir"])
            assert (out_dir / "summary.json").exists()
            assert (out_dir / "report.html").exists()
        finally:
            window.close()
