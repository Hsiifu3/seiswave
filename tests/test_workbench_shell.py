"""Phase 2 工作台主壳离屏测试。"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

from seiswave.core.signal import EQSignal
from seiswave.core.signal_pool import SignalPool, SignalRecord
from seiswave.core.target_spectrum import TargetSpectrumService
from seiswave.gui.workbench.app_window import AppWindow


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app



def _make_record(name: str, scale: float, kind: str = "natural") -> SignalRecord:
    time = np.linspace(0.0, 6.0, 601)
    acc = scale * (
        0.14 * np.sin(2.0 * np.pi * 1.2 * time)
        + 0.05 * np.sin(2.0 * np.pi * 3.4 * time + 0.2)
    )
    return SignalRecord(
        acc=acc,
        dt=float(time[1] - time[0]),
        name=name,
        kind=kind,
        meta={"source": "unit-test"},
    )



def _build_window() -> tuple[AppWindow, SignalPool, TargetSpectrumService, np.ndarray]:
    periods = np.array([0.1, 0.2, 0.5, 1.0, 2.0], dtype=np.float64)
    pool = SignalPool()
    record_a = _make_record("RSN-A", 1.0)
    record_b = _make_record("RSN-B", 0.8, kind="processed")
    pool.add(record_a)
    pool.add(record_b)
    target = TargetSpectrumService(periods=periods)
    return AppWindow(pool=pool, target_service=target), pool, target, periods


class TestWorkbenchShell:
    def test_main_window_builds_without_errors(self, qapp):
        window, pool, target, periods = _build_window()
        try:
            target.set_code(
                "GB50011",
                periods=periods,
                intensity=8,
                group=2,
                site_class="II",
                level="basic",
            )
            qapp.processEvents()

            assert window.windowTitle() == "SeisWave — 工作台"
            assert window._signal_pool_panel is not None
            assert window._preview_panel is not None
            assert window._tool_dock is not None
            assert window._signal_pool_panel._list.count() == 2
            assert window._tool_dock.current_tool() == "导入"
        finally:
            window.close()

    def test_selection_draws_motion_and_spectrum_plots(self, qapp):
        window, pool, target, periods = _build_window()
        try:
            target.set_custom(periods, np.array([0.30, 0.42, 0.36, 0.22, 0.12]))
            selected = pool.all()[0]
            pool.set_selection([selected.id])
            qapp.processEvents()

            preview = window._preview_panel
            assert len(preview._acc_plot.ax.lines) == 1
            assert len(preview._vel_plot.ax.lines) == 1
            assert len(preview._disp_plot.ax.lines) == 1
            assert len(preview.spectrum_axes()) == 1
            assert len(preview.spectrum_axes()[0].lines) == 2
        finally:
            window.close()

    def test_scorecard_metrics_match_expected_values(self, qapp):
        window, pool, target, periods = _build_window()
        try:
            selected = pool.all()[0]
            target.set_from_record(selected, periods=periods, zeta=0.05)
            pool.set_selection([selected.id])
            qapp.processEvents()

            metrics = window._preview_panel._scorecard.metrics()
            sig = EQSignal(selected.acc, selected.dt, name=selected.name)
            # 记分卡 Arias 以 m/s 显示：acc 由 g 换算为 m/s² 后积分
            sig_si = EQSignal(selected.acc * 9.80665, selected.dt, name=selected.name)
            expected_arias = float(sig_si.arias_intensity()[-1])

            assert metrics["mean_error_pct"] == pytest.approx(0.0, abs=1e-8)
            assert metrics["pga"] == pytest.approx(np.max(np.abs(selected.acc)))
            assert metrics["pgv"] == pytest.approx(np.max(np.abs(selected.vel())))
            assert metrics["pgd"] == pytest.approx(np.max(np.abs(selected.disp())))
            assert metrics["arias"] == pytest.approx(expected_arias)
            assert metrics["duration_sig"] == pytest.approx(sig.effective_duration)
        finally:
            window.close()

    def test_project_round_trip_restores_pool_target_and_ui_state(self, qapp, tmp_path):
        window, pool, target, periods = _build_window()
        try:
            target.set_code(
                "GB50011",
                periods=periods,
                intensity=8,
                group=2,
                site_class="II",
                level="rare",
            )
            pool.set_selection([pool.all()[1].id])
            window.set_current_tool("谱拟合")
            window._preview_panel.restore_state(
                {"triple_log": True, "damping_mode": "multi"}
            )
            qapp.processEvents()

            json_path = tmp_path / "phase2-project.json"
            window.save_project_to(json_path)

            new_pool = SignalPool()
            new_target = TargetSpectrumService(periods=periods)
            new_window = AppWindow(pool=new_pool, target_service=new_target)
            try:
                new_window.load_project_from(json_path)
                qapp.processEvents()

                assert [record.id for record in new_pool.all()] == [
                    record.id for record in pool.all()
                ]
                assert new_pool.selection_ids() == [pool.all()[1].id]
                assert new_target.source() == "code"
                np.testing.assert_allclose(new_target.periods(), target.periods())
                np.testing.assert_allclose(new_target.sa(), target.sa())
                assert new_window._tool_dock.current_tool() == "谱拟合"
                assert new_window._preview_panel.state() == {
                    "triple_log": True,
                    "logx": False,
                    "damping_mode": "multi",
                }
            finally:
                new_window.close()
        finally:
            window.close()
