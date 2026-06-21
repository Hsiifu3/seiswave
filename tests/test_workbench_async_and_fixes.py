"""工作台异步层 + 审查修复(#1-#6)的回归测试。"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from seiswave.core.io import FileIO
from seiswave.core.signal_pool import SignalPool, SignalRecord
from seiswave.core.target_spectrum import TargetSpectrumService
from seiswave.gui.workbench.app_window import AppWindow
from seiswave.gui.workbench.tool_worker import ToolJobWorker
from seiswave.gui.workbench.tools.data_export_tool import _safe_stem
from seiswave.gui.workbench.target_dialog import TargetSpectrumDialog


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _make_record(name: str, dt: float = 0.01, scale: float = 1.0) -> SignalRecord:
    n = 801
    time = np.arange(n) * dt
    acc = scale * (
        0.18 * np.sin(2.0 * np.pi * 1.1 * time)
        + 0.06 * np.sin(2.0 * np.pi * 3.2 * time + 0.4)
    )
    return SignalRecord(acc=acc, dt=dt, name=name, kind="natural", meta={"source": "ut"})


def _build_window(dt: float = 0.01):
    periods = np.array([0.1, 0.2, 0.5, 1.0, 2.0], dtype=np.float64)
    pool = SignalPool()
    rec = _make_record("RSN-A", dt=dt)
    pool.add(rec)
    target = TargetSpectrumService(periods=periods)
    target.set_custom(periods, np.array([0.25, 0.40, 0.31, 0.22, 0.10]))
    window = AppWindow(pool=pool, target_service=target)
    pool.set_selection([rec.id])
    return window, pool, target, rec


# ---------------------------------------------------------------- #1 异步层

class TestAsyncHarness:
    def test_tool_job_worker_passes_progress_and_cancel(self, qapp):
        seen = {}

        def compute(progress_cb, is_cancelled):
            progress_cb(42, "halfway")
            seen["cancel_type"] = callable(is_cancelled)
            return {"ok": True}

        events = []
        worker = ToolJobWorker(compute)
        worker.signals.progress.connect(lambda p, t: events.append((p, t)))
        result = worker.execute()  # 直接同步执行（不起线程）

        assert result == {"ok": True}
        assert seen["cancel_type"] is True
        assert events == [(42, "halfway")]

    def test_tool_job_worker_cancel_flag(self, qapp):
        def compute(progress_cb, is_cancelled):
            if is_cancelled():
                raise InterruptedError("用户取消")
            return "done"

        worker = ToolJobWorker(compute)
        worker.cancel()
        with pytest.raises(InterruptedError, match="用户取消"):
            worker.execute()

    def test_artificial_build_job_matches_sync(self, qapp):
        window, pool, target, _ = _build_window()
        try:
            tool = window._tool_dock._tool_widgets["人工波生成"]
            tool._type_combo.setCurrentIndex(tool._type_combo.findData("general"))
            tool._n_spin.setValue(256)
            tool._iter_spin.setValue(2)
            before = len(pool.all())

            job = tool.build_job()
            assert job is not None
            compute, finalize = job
            payload = compute(lambda *_: None, lambda: False)
            children = finalize(payload)

            assert len(children) == 1
            assert len(pool.all()) == before + 1
            assert children[0].kind == "artificial"
        finally:
            window.close()

    def test_spectral_match_build_job_cancel(self, qapp):
        window, pool, target, _ = _build_window()
        try:
            tool = window._tool_dock._tool_widgets["谱拟合"]
            job = tool.build_job()
            assert job is not None
            compute, _finalize = job
            with pytest.raises(InterruptedError):
                compute(lambda *_: None, lambda: True)
        finally:
            window.close()

    def test_build_job_returns_none_without_target(self, qapp):
        window, pool, target, _ = _build_window()
        try:
            target.clear()
            tool = window._tool_dock._tool_widgets["谱拟合"]
            # 无目标谱：_prepare 弹警告并返回 None（这里 monkeypatch 掉弹窗）
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.warning = staticmethod(lambda *a, **k: None)
            assert tool.build_job() is None
        finally:
            window.close()

    def test_dock_progress_signal_wired(self, qapp):
        window, pool, target, _ = _build_window()
        try:
            received = []
            window._tool_dock.progress_changed.connect(
                lambda p, t: received.append((p, t))
            )
            window._tool_dock.progress_changed.emit(50, "测试")
            assert received == [(50, "测试")]
            # app_window 槽更新进度条
            window._on_tool_progress(50, "测试")
            assert window._progress_bar.value() == 50
        finally:
            window.close()


# ---------------------------------------------------------------- #2 滤波 Nyquist

class TestFilterNyquist:
    def test_filter_rejects_cutoff_above_nyquist(self, qapp, monkeypatch):
        window, pool, target, rec = _build_window(dt=0.02)  # Nyquist = 25 Hz
        try:
            tool = window._tool_dock._tool_widgets["滤波"]
            tool._f2_spin.setValue(25.0)  # >= Nyquist
            captured = {}
            from PySide6.QtWidgets import QMessageBox

            monkeypatch.setattr(
                QMessageBox, "critical",
                staticmethod(lambda *a, **k: captured.update(msg=a[-1])),
            )
            result = tool.run_tool()
            assert result == []  # 不崩、被兜底
            assert "奈奎斯特" in captured.get("msg", "")
        finally:
            window.close()

    def test_filter_accepts_valid_cutoff(self, qapp):
        window, pool, target, rec = _build_window(dt=0.01)  # Nyquist = 50 Hz
        try:
            tool = window._tool_dock._tool_widgets["滤波"]
            tool._f1_spin.setValue(0.2)
            tool._f2_spin.setValue(20.0)
            result = tool.run_tool()
            assert len(result) == 1
        finally:
            window.close()


# ---------------------------------------------------------------- #4 目录导入容错

class TestImportSkipOnError:
    def test_directory_import_skips_bad_file(self, qapp, tmp_path):
        window, pool, target, _ = _build_window()
        try:
            directory = tmp_path / "mix"
            directory.mkdir()
            good_time = np.arange(2001) * 0.01
            FileIO.write_at2(directory / "good.AT2", 0.1 * np.sin(good_time), 0.01)
            (directory / "bad.txt").write_text("not a valid waveform !!!\n@@@\n")

            tool = window._tool_dock._tool_widgets["导入"]
            tool._path_edit.setText(str(directory))
            tool._mode_combo.setCurrentIndex(tool._mode_combo.findData("directory"))
            idx = tool._pattern_combo.findData("all")
            if idx >= 0:
                tool._pattern_combo.setCurrentIndex(idx)

            before = len(pool.all())
            result = tool.run_tool()
            assert len(result) >= 1  # 好文件入库
            assert len(pool.all()) == before + len(result)
            assert len(getattr(tool, "_last_skipped", [])) == 1  # 坏文件被跳过
        finally:
            window.close()


# ---------------------------------------------------------------- #3 空选择导出谱

class TestSpectrumExportNoSelection:
    def test_export_spectrum_target_only(self, qapp, tmp_path, monkeypatch):
        window, pool, target, _ = _build_window()
        try:
            tool = window._tool_dock._data_export_tool
            periods = np.array([0.1, 0.2, 0.5, 1.0])
            # 模拟“设了目标谱但没选信号”：zetas 非空但 mean_spectra 为空
            snapshot = {
                "periods": periods,
                "target_sa": np.array([0.2, 0.3, 0.25, 0.15]),
                "zetas": [0.05],
                "mean_spectra": {},
            }
            monkeypatch.setattr(
                tool._preview_panel, "current_spectrum_snapshot", lambda: snapshot
            )
            path = tool._export_spectrum(Path(tmp_path), "t", "csv")
            assert path.exists()
            text = path.read_text()
            assert "target_sa" in text  # 目标谱列已写出，无 KeyError
        finally:
            window.close()


# ---------------------------------------------------------------- #6 文件名净化

class TestSafeStem:
    @pytest.mark.parametrize(
        "raw,expected_clean",
        [
            ("rec · 基线校正 (poly)", "rec___基线校正_(poly)"),
            ("a/b\\c", "a_b_c"),
            ("   ", "export"),
            ("name:*?", "name"),
        ],
    )
    def test_safe_stem(self, raw, expected_clean):
        assert _safe_stem(raw) == expected_clean


# ---------------------------------------------------------------- 目标谱设置入口

class TestTargetSpectrumDialog:
    def test_code_mode_sets_target(self, qapp):
        window, pool, target, _ = _build_window()
        try:
            target.clear()
            dlg = TargetSpectrumDialog(pool, target, window)
            dlg._mode_combo.setCurrentIndex(0)  # 规范设计谱
            dlg._apply()
            assert target.source() == "code"
            assert target.sa().size > 0
            assert "GB50011" in target.describe()
        finally:
            window.close()

    def test_record_mode_sets_target(self, qapp):
        window, pool, target, rec = _build_window()
        try:
            target.clear()
            dlg = TargetSpectrumDialog(pool, target, window)
            dlg._mode_combo.setCurrentIndex(1)  # 从选中信号
            dlg._apply()
            assert target.source() == "record"
            assert target.sa().size > 0
        finally:
            window.close()

    def test_custom_mode_empty_path_warns(self, qapp, monkeypatch):
        window, pool, target, _ = _build_window()
        try:
            target.clear()
            from PySide6.QtWidgets import QMessageBox

            monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: None))
            dlg = TargetSpectrumDialog(pool, target, window)
            dlg._mode_combo.setCurrentIndex(2)  # 自定义文件
            dlg._apply()  # 空路径 → 报错、不设置
            assert target.source() is None
        finally:
            window.close()

    def test_app_window_has_target_entry(self, qapp):
        window, pool, target, _ = _build_window()
        try:
            assert hasattr(window, "open_target_dialog")
        finally:
            window.close()

