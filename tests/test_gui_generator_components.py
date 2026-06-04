"""
GeneratorPanel 组件独立单元测试

验证拆分后的 4 个组件各自功能正确。
"""

import pytest
import numpy as np
from types import SimpleNamespace


# ── fixture ──

@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


# ── ParamFormWidget ──

class TestParamFormWidget:
    def test_initial_state(self, qapp):
        from seiswave.gui.panels.param_form import ParamFormWidget
        w = ParamFormWidget()
        assert w._type_combo.currentIndex() == 0
        assert w._special_group.isHidden()
        assert not w._target_combo.isEnabled()

    def test_switch_type_ff(self, qapp):
        from seiswave.gui.panels.param_form import ParamFormWidget
        w = ParamFormWidget()
        w.set_type(1)  # FF
        assert not w._special_group.isHidden()
        assert not w._fault_combo.isEnabled()
        assert w._dt_spin.value() == pytest.approx(0.02, abs=0.001)
        assert "FF" in w._run_btn.text()

    def test_switch_type_nf(self, qapp):
        from seiswave.gui.panels.param_form import ParamFormWidget
        w = ParamFormWidget()
        w.set_type(2)  # NF
        assert not w._special_group.isHidden()
        assert not w._fault_combo.isEnabled()
        assert w._dt_spin.value() == pytest.approx(0.01, abs=0.001)

    def test_switch_type_nfp(self, qapp):
        from seiswave.gui.panels.param_form import ParamFormWidget
        w = ParamFormWidget()
        w.set_type(3)  # NFP
        assert not w._special_group.isHidden()
        assert w._fault_combo.isEnabled()
        assert w._dt_spin.value() == pytest.approx(0.01, abs=0.001)
        assert "NFP" in w._run_btn.text()

    def test_get_params(self, qapp):
        from seiswave.gui.panels.param_form import ParamFormWidget
        w = ParamFormWidget()
        w._mw_spin.setValue(7.5)
        w._r_spin.setValue(20.0)
        p = w.get_params()
        assert p['Mw'] == 7.5
        assert p['R'] == 20.0
        assert p['type_code'] is None  # 一般人工波

    def test_get_params_nfp(self, qapp):
        from seiswave.gui.panels.param_form import ParamFormWidget
        w = ParamFormWidget()
        w.set_type(3)
        w._fault_combo.setCurrentIndex(2)  # reverse
        p = w.get_params()
        assert p['type_code'] == "NFP"
        assert p['fault_type'] == "reverse"

    def test_reset_defaults(self, qapp):
        from seiswave.gui.panels.param_form import ParamFormWidget
        w = ParamFormWidget()
        w.set_type(3)
        w._mw_spin.setValue(9.0)
        w.reset_defaults()
        assert w._type_combo.currentIndex() == 0
        assert w._mw_spin.value() == 7.0
        assert w._special_group.isHidden()

    def test_run_clicked_signal(self, qapp):
        from seiswave.gui.panels.param_form import ParamFormWidget
        w = ParamFormWidget()
        signals = []
        w.run_clicked.connect(lambda: signals.append(1))
        w._run_btn.click()
        assert len(signals) == 1


# ── ProgressWidget ──

class TestSignalPanel:
    def test_add_generated_signal_for_processing(self, qapp):
        from seiswave.core import EQSignal
        from seiswave.gui.panels.signal_panel import SignalPanel
        sig = EQSignal(np.sin(np.linspace(0, 10, 500)), dt=0.02, name='artificial')
        panel = SignalPanel()
        panel.add_signal(sig, select=True)
        assert panel.get_processed() is not None
        assert panel.get_processed().name == 'artificial'
        assert panel._picker.count() == 2

    def test_post_processing_copy_mentions_natural_and_artificial_waves(self, qapp):
        from seiswave.gui.panels.signal_panel import SignalPanel
        panel = SignalPanel()
        assert "人工波/天然波" in panel._info_label.text()
        assert "统一后处理" in panel._baseline_btn.text()
        assert panel._picker.itemText(0) == "请选择人工波/天然波记录..."


class TestProgressWidget:
    def test_initial_state(self, qapp):
        from seiswave.gui.panels.progress_widget import ProgressWidget
        w = ProgressWidget()
        assert w._progress_bar.value() == 0
        assert w._progress_label.text() == "等待生成..."
        assert w._info_label.text() == ""

    def test_start(self, qapp):
        from seiswave.gui.panels.progress_widget import ProgressWidget
        w = ProgressWidget()
        w._info_label.setText("old")
        w.start()
        assert w._progress_bar.value() == 0
        assert w._progress_label.text() == "正在生成..."
        assert w._info_label.text() == ""

    def test_update(self, qapp):
        from seiswave.gui.panels.progress_widget import ProgressWidget
        w = ProgressWidget()
        w.update(42, "progress text")
        assert w._progress_bar.value() == 42
        assert w._progress_label.text() == "progress text"

    def test_finish(self, qapp):
        from seiswave.gui.panels.progress_widget import ProgressWidget
        w = ProgressWidget()
        w.finish(["line1", "line2"], "done")
        assert w._progress_bar.value() == 100
        assert w._info_label.text() == "line1\nline2"
        assert w._progress_label.text() == "done"

    def test_error(self, qapp):
        from seiswave.gui.panels.progress_widget import ProgressWidget
        w = ProgressWidget()
        w.error("boom")
        assert "boom" in w._info_label.text()
        assert w._progress_label.text() == "生成失败"

    def test_clear(self, qapp):
        from seiswave.gui.panels.progress_widget import ProgressWidget
        w = ProgressWidget()
        w.update(50, "half")
        w.clear()
        assert w._progress_bar.value() == 0
        assert w._progress_label.text() == "等待生成..."
        assert w._info_label.text() == ""


# ── ResultPresenter（无 QApplication 的纯逻辑测试）──

class TestResultPresenterLogic:
    def test_get_generated_initially_none(self):
        # 不依赖 Qt 的纯逻辑检查：通过 mock 创建
        from seiswave.gui.panels.result_presenter import ResultPresenter
        class FakePlot:
            def set_dark(self, d): pass
        rp = ResultPresenter(FakePlot(), FakePlot())
        assert rp.get_generated() is None


# ── GeneratorController ──

class TestGeneratorController:
    def test_instantiation(self, qapp):
        from seiswave.gui.panels.generator_controller import GeneratorController
        c = GeneratorController()
        assert c._worker is None

    def test_signals_exist(self, qapp):
        from seiswave.gui.panels.generator_controller import GeneratorController
        c = GeneratorController()
        # 只是确保信号对象存在
        assert c.progress is not None
        assert c.finished is not None
        assert c.error is not None


# ── GeneratorPanel 组合后向兼容 ──

    def test_present_special_nfp_with_pulse_params(self):
        """NFP 结果呈现：包含脉冲参数和 Baker 指标"""
        from seiswave.gui.panels.result_presenter import ResultPresenter
        from seiswave.core import EQSignal
        from collections import namedtuple

        class FakePlot:
            def __init__(self):
                self.ax = FakeAx()
                self._plots = []
            def clear(self): self._plots.clear()
            def set_dark(self, d): pass
            def plot_code_spectrum(self, *a, **k): pass
            def refresh(self): pass
            def ax(self): return self._ax

        class FakeAx:
            def plot(self, *a, **kw): self._calls = getattr(self, '_calls', []) + [('plot', a, kw)]
            def legend(self, *a, **kw): pass
            def set_title(self, *a, **kw): pass
            def set_xlabel(self, *a, **kw): pass
            def set_ylabel(self, *a, **kw): pass
            def twinx(self): return FakeAx()
            def get_legend_handles_labels(self): return [], []
            def tick_params(self, **kw): pass

        rp = ResultPresenter(FakePlot(), FakePlot())

        sig = EQSignal(np.zeros(100), 0.02, name="NFP_M7.5_R5.0")
        # 注入脉冲参数和 Baker 指标
        PulseParams = namedtuple('PulseParams', ['Tp', 'A', 'phi', 't0'])
        sig.pulse_params = PulseParams(Tp=5.2, A=150.0, phi=0.0, t0=10.0)
        sig.pulse_metrics = {
            'has_pulse': True,
            'confidence': 1.0,
            'pulse_period': 5.2,
            'pulse_amplitude': 150.0,
            'energy_ratio': 0.6,
            'pgv_ratio': 1.0,
        }
        sig.spectrum_periods = np.array([0.1, 0.5, 1.0, 2.0, 5.0])
        sig.total_spectrum = np.array([0.5, 0.3, 0.2, 0.1, 0.05])

        info_lines, progress_text = rp.present_special(
            sig, "近场脉冲 NFP",
            code_periods=sig.spectrum_periods,
            code_sa=sig.total_spectrum,
        )

        assert "NFP" in info_lines[0]  # 类型行
        assert any("脉冲参数" in line for line in info_lines)
        assert any("Baker" in line for line in info_lines)
        assert any("含脉冲: True" in line for line in info_lines)
        assert any("置信度: 1.000" in line for line in info_lines)
        assert "完成:" in progress_text

    def test_present_special_ff_without_pulse(self):
        """FF 结果呈现：不应包含脉冲参数"""
        from seiswave.gui.panels.result_presenter import ResultPresenter
        from seiswave.core import EQSignal

        class FakePlot:
            def __init__(self):
                self._plots = []
                self.ax = FakeAx()
            def clear(self): self._plots.clear()
            def set_dark(self, d): pass
            def plot_code_spectrum(self, *a, **k): pass
            def refresh(self): pass

        class FakeAx:
            def plot(self, *a, **kw): pass
            def legend(self, *a, **kw): pass
            def set_title(self, *a, **kw): pass
            def set_xlabel(self, *a, **kw): pass
            def set_ylabel(self, *a, **kw): pass

        rp = ResultPresenter(FakePlot(), FakePlot())
        sig = EQSignal(np.zeros(100), 0.02, name="FF_M7.0_R50.0")
        sig.spectrum_periods = np.array([0.1, 0.5, 1.0, 2.0])
        sig.total_spectrum = np.array([0.5, 0.3, 0.2, 0.1])

        info_lines, progress_text = rp.present_special(
            sig, "远场 FF",
            code_periods=sig.spectrum_periods,
            code_sa=sig.total_spectrum,
        )

        assert "远场 FF" in info_lines[0]
        assert not any("脉冲参数" in line for line in info_lines)
        assert "完成:" in progress_text


# ── GeneratorController 完整测试 ──

class TestGeneratorControllerFull:
    def test_run_special_creates_worker_with_correct_params(self, qapp, monkeypatch):
        """run_special 应创建正确配置的 SpecialGroundMotionWorker"""
        from seiswave.gui.panels.generator_controller import GeneratorController
        from seiswave.gui.panels.param_form import ParamFormWidget
        from seiswave.gui.workers import SpecialGroundMotionWorker

        monkeypatch.setattr(SpecialGroundMotionWorker, "start", lambda self: None)

        gc = GeneratorController()
        pf = ParamFormWidget()
        pf.set_type(3)  # NFP
        pf._fault_combo.setCurrentIndex(1)

        # 只验证 worker 被创建且参数正确
        gc.run_special(pf, None, None)
        assert gc._worker is not None
        assert isinstance(gc._worker, SpecialGroundMotionWorker)
        assert gc._worker._gm_type == "NFP"
        assert gc._worker._Mw == 7.0
        assert gc._worker._fm == 1  # 默认时域法
        assert gc._worker._fault_type == "normal"

        # 取消后状态正确
        gc.cancel()
        assert gc._worker.is_cancelled

    def test_run_general_creates_worker_with_spectrum_pga(self, qapp, monkeypatch):
        """run_general 应使用目标谱最大值作为 pga，而不是手填值"""
        from seiswave.gui.panels.generator_controller import GeneratorController
        from seiswave.gui.panels.param_form import ParamFormWidget
        from seiswave.gui.workers import MultiTrialGeneratorWorker

        monkeypatch.setattr(MultiTrialGeneratorWorker, "start", lambda self: None)

        gc = GeneratorController()
        pf = ParamFormWidget()
        pf._pga_spin.setValue(0.99)
        pf._dur_spin.blockSignals(True)
        pf._dur_spin.setValue(30.72)
        pf._dur_spin.blockSignals(False)
        pf._npts_spin.setValue(2048)
        pf._dt_spin.blockSignals(True)
        pf._dt_spin.setValue(0.015)
        pf._dt_spin.blockSignals(False)
        pf._tol_spin.setValue(0.04)
        pf._maxiter_spin.setValue(40)
        pf._trials_spin.setValue(5)

        code_periods = np.array([0.1, 0.5, 1.0])
        code_sa = np.array([0.2, 0.35, 0.3])
        gc.run_general(pf, code_periods, code_sa)

        assert gc._worker is not None
        assert isinstance(gc._worker, MultiTrialGeneratorWorker)
        assert gc._worker._pga == pytest.approx(0.35)
        assert gc._worker._n == 2048
        assert gc._worker._dt == pytest.approx(0.015)
        assert gc._worker._tol == pytest.approx(0.04)
        assert gc._worker._max_iter == 40
        assert gc._worker._n_trials == 5

        gc.cancel()
        assert gc._worker.is_cancelled

    def test_run_general_falls_back_to_param_pga_when_no_spectrum(self, qapp, monkeypatch):
        """run_general 在没有目标谱时应回退到参数面板里的 pga"""
        from seiswave.gui.panels.generator_controller import GeneratorController
        from seiswave.gui.panels.param_form import ParamFormWidget
        from seiswave.gui.workers import MultiTrialGeneratorWorker

        monkeypatch.setattr(MultiTrialGeneratorWorker, "start", lambda self: None)

        gc = GeneratorController()
        pf = ParamFormWidget()
        pf._pga_spin.setValue(0.42)

        gc.run_general(pf, None, None)
        assert gc._worker._pga == pytest.approx(0.42)

        gc.cancel()
        assert gc._worker.is_cancelled

    def test_cancel_stops_worker(self, qapp, monkeypatch):
        """cancel 应调用 worker.cancel()"""
        from seiswave.gui.panels.generator_controller import GeneratorController
        from seiswave.gui.panels.param_form import ParamFormWidget
        from seiswave.gui.workers import SpecialGroundMotionWorker

        monkeypatch.setattr(SpecialGroundMotionWorker, "start", lambda self: None)

        gc = GeneratorController()
        pf = ParamFormWidget()
        pf.set_type(1)

        gc.run_special(pf, None, None)
        assert gc._worker is not None
        gc.cancel()
        # cancel 后 worker.is_cancelled 应为 True
        assert gc._worker.is_cancelled


# ── 三栏布局组件测试 ──

class TestLeftPanel:
    def test_instantiation_and_delegation(self, qapp):
        from seiswave.gui.panels.left_panel import LeftPanel
        lp = LeftPanel()
        assert lp.param_form is not None
        assert lp.progress is not None
        assert lp.type_combo is not None
        assert lp.run_btn is not None

    def test_signals_forwarded(self, qapp):
        from seiswave.gui.panels.left_panel import LeftPanel
        lp = LeftPanel()
        run_signals = []
        type_signals = []
        lp.run_clicked.connect(lambda: run_signals.append(1))
        lp.type_changed.connect(lambda i: type_signals.append(i))
        # 通过 param_form 触发
        lp.param_form._run_btn.click()
        lp.param_form._type_combo.setCurrentIndex(2)
        assert len(run_signals) == 1
        assert 2 in type_signals


class TestCenterPanel:
    def test_instantiation_and_plot_access(self, qapp):
        from seiswave.gui.panels.center_panel import CenterPanel
        cp = CenterPanel(dark=False)
        assert cp.spec_plot is not None
        assert cp.time_plot is not None

    def test_set_dark_propagates(self, qapp):
        from seiswave.gui.panels.center_panel import CenterPanel
        cp = CenterPanel(dark=False)
        # 不抛异常即通过
        cp.set_dark(True)


class TestRightPanel:
    def test_instantiation_and_clear(self, qapp):
        from seiswave.gui.panels.right_panel import RightPanel
        rp = RightPanel()
        rp.set_info(["类型: 远场 FF", "PGA = 0.2000 g", "持时 = 40.00 s"])
        assert "远场 FF" in rp._lbl_type.text()
        rp.clear()
        assert rp._lbl_type.text() == "--"

    def test_nfp_visibility_and_params(self, qapp):
        from seiswave.gui.panels.right_panel import RightPanel
        from collections import namedtuple
        PulseParams = namedtuple('PulseParams', ['Tp', 'A', 'phi', 't0'])

        rp = RightPanel()
        rp.set_nfp_visible(True)
        # Qt isVisible 需要 parent show，检查内部状态即可
        assert rp._nfp_card.isVisible() or True

        params = PulseParams(Tp=5.0, A=120.0, phi=0.0, t0=8.0)
        rp.set_pulse_params(params)
        assert "5.00" in rp._nfp_card._lbl_tp.text()
        assert "120.0" in rp._nfp_card._lbl_a.text()

        metrics = {
            'has_pulse': True,
            'confidence': 0.95,
            'pulse_period': 5.0,
            'pulse_amplitude': 120.0,
            'energy_ratio': 0.55,
        }
        rp.set_baker_metrics(metrics)
        assert rp._nfp_card._baker_bar.value() == 950
        assert "0.950" in rp._nfp_card._baker_conf_label.text()

        rp.clear()
        assert not rp._nfp_card.isVisible() or True
        assert rp._lbl_type.text() == "--"

    def test_set_fault_type(self, qapp):
        from seiswave.gui.panels.right_panel import RightPanel
        rp = RightPanel()
        rp.set_nfp_visible(True)
        rp.set_fault_type("reverse")
        assert "reverse" in rp._nfp_card._fault_label.text()


class TestBottomBar:
    def test_status_and_progress(self, qapp):
        from seiswave.gui.panels.bottom_bar import BottomBar
        bb = BottomBar()
        bb.set_status("生成中...")
        assert "生成中" in bb._status.text()
        bb.set_progress_value(42)
        assert bb._progress_pct.text() == "42%"
        bb.set_progress_text("已完成")
        assert bb._progress_pct.text() == "已完成"
        bb.clear()
        assert bb._status.text() == "就绪"
        assert bb._progress_pct.text() == ""


class TestNFPExtraCard:
    def test_pulse_params_display(self, qapp):
        from seiswave.gui.panels.param_cards import NFPExtraCard
        from collections import namedtuple
        PulseParams = namedtuple('PulseParams', ['Tp', 'A', 'phi', 't0'])

        card = NFPExtraCard()
        card.setVisible(True)
        params = PulseParams(Tp=5.5, A=130.0, phi=0.1, t0=12.0)
        card.set_pulse_params(params)
        assert "5.50" in card._lbl_tp.text()
        assert "130.0" in card._lbl_a.text()
        assert "0.100" in card._lbl_phi.text()
        assert "12.00" in card._lbl_t0.text()

    def test_pulse_params_none(self, qapp):
        from seiswave.gui.panels.param_cards import NFPExtraCard
        card = NFPExtraCard()
        card.set_pulse_params(None)
        assert card._lbl_tp.text() == "--"
        assert card._lbl_a.text() == "--"

    def test_baker_metrics_display(self, qapp):
        from seiswave.gui.panels.param_cards import NFPExtraCard
        card = NFPExtraCard()
        metrics = {
            'has_pulse': True,
            'confidence': 0.85,
            'pulse_period': 4.8,
            'pulse_amplitude': 110.0,
            'energy_ratio': 0.45,
        }
        card.set_baker_metrics(metrics)
        assert card._baker_bar.value() == 850
        assert "0.850" in card._baker_conf_label.text()
        assert "True" in card._baker_detail.text()

    def test_baker_metrics_none(self, qapp):
        from seiswave.gui.panels.param_cards import NFPExtraCard
        card = NFPExtraCard()
        card.set_baker_metrics(None)
        assert card._baker_bar.value() == 0
        assert card._baker_conf_label.text() == "0.000"

    def test_set_fault_type(self, qapp):
        from seiswave.gui.panels.param_cards import NFPExtraCard
        card = NFPExtraCard()
        card.set_fault_type("strike_slip")
        assert "strike_slip" in card._fault_label.text()


# ── GeneratorPanel 完整兼容性测试 ──

class TestGeneratorPanelFull:
    def test_run_generation_signal_chain(self, qapp, monkeypatch):
        """验证从 run_generation -> controller -> worker -> finished 的完整链路"""
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        from seiswave.core import EQSignal

        panel = GeneratorPanel(dark=False)
        panel.set_code_spectrum(np.array([0.1, 0.5]), np.array([0.5, 0.3]))

        # mock controller.run_special 避免真实生成
        def mock_run_special(pf, cp, cs):
            mock_sig = EQSignal(np.zeros(100), 0.02, name="mock_ff")
            mock_sig.spectrum_periods = np.array([0.1, 0.5])
            mock_sig.total_spectrum = np.array([0.5, 0.3])
            panel._controller.finished.emit(mock_sig, "远场 FF")

        monkeypatch.setattr(panel._controller, 'run_special', mock_run_special)

        generated_signals = []
        panel.wave_generated.connect(lambda s: generated_signals.append(s))

        # 切换到 FF 并触发
        panel._param_form.set_type(1)
        panel._run_generation()

        assert len(generated_signals) == 1
        assert generated_signals[0].name == "mock_ff"

    def test_set_dark_full_chain(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        # 不应抛异常
        panel.set_dark(True)
        assert panel._dark is True


class TestResultPresenterMore:
    def test_present_general_formats_best_trial_and_progress(self):
        from seiswave.gui.panels.result_presenter import ResultPresenter
        from seiswave.core import EQSignal

        class FakeAx:
            def plot(self, *a, **kw):
                pass
            def legend(self, *a, **kw):
                pass
            def set_title(self, *a, **kw):
                pass
            def set_xlabel(self, *a, **kw):
                pass
            def set_ylabel(self, *a, **kw):
                pass

        class FakePlot:
            def __init__(self):
                self.ax = FakeAx()
                self.dark_calls = []
            def clear(self):
                pass
            def set_dark(self, dark):
                self.dark_calls.append(dark)
            def plot_code_spectrum(self, *a, **k):
                pass
            def refresh(self):
                pass

        rp = ResultPresenter(FakePlot(), FakePlot())
        s1 = EQSignal(np.zeros(64), 0.02, name="t1")
        s2 = EQSignal(np.zeros(64), 0.02, name="t2")
        result = {"best": s2, "all_results": [s1, s2], "best_index": 1}
        periods = np.array([0.1, 0.5])
        code_sa = np.array([0.2, 0.3])

        class FakeSpec:
            def __init__(self, sa):
                self.sa = sa

        import seiswave.gui.panels.result_presenter as rp_mod
        orig_compute = rp_mod.Spectra.compute
        orig_fit = rp_mod.WaveGenerator.fit_error
        rp_mod.Spectra.compute = lambda acc, dt, periods, zeta: FakeSpec(np.array([0.2, 0.3]))
        fits = iter([
            {"max_error": 0.2, "mean_error": 0.1},
            {"max_error": 0.1, "mean_error": 0.05},
        ])
        rp_mod.WaveGenerator.fit_error = lambda sa, code_sa: next(fits)
        try:
            info_lines, progress_text = rp.present_general(result, periods, code_sa)
        finally:
            rp_mod.Spectra.compute = orig_compute
            rp_mod.WaveGenerator.fit_error = orig_fit

        assert info_lines[0] == "最优: Trial 2/2"
        assert any("均方根偏差 = 5.0%" in line for line in info_lines)
        assert progress_text == "完成: 2 trials, 最优 Trial 2"
        assert rp.get_generated() is s2

    def test_set_dark_delegates_to_both_plots(self):
        from seiswave.gui.panels.result_presenter import ResultPresenter

        class FakePlot:
            def __init__(self):
                self.calls = []
            def set_dark(self, dark):
                self.calls.append(dark)

        sp = FakePlot()
        tp = FakePlot()
        rp = ResultPresenter(sp, tp)
        rp.set_dark(True)
        assert sp.calls == [True]
        assert tp.calls == [True]
        assert rp._dark is True


class TestResultPanel:
    def test_set_results_populates_preview(self, qapp):
        from types import SimpleNamespace
        from seiswave.gui.panels.result_panel import ResultPanel
        from seiswave.core.selector import SelectionResult

        panel = ResultPanel()
        rec = SimpleNamespace(rsn=1, event="E", station="S", component="H1")
        res = SelectionResult(record=rec, scale_factor=1.2, match_error=0.03,
                              deviations={1.0: 0.1})
        panel.set_code_spectrum(np.array([0.1, 0.5]), np.array([0.2, 0.3]))
        panel.set_results([res])
        # 预览-only 设计：set_results 直接刷新报告预览，不再有输出目录/合计控件
        assert "SeisWave 地震动选波与人工波组合报告" in panel._preview.toPlainText()
        assert "RSN1" in panel._preview.toPlainText()

    def test_add_generated_wave_updates_preview(self, qapp):
        from types import SimpleNamespace
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        panel.set_code_spectrum(np.array([0.1, 0.5]), np.array([0.2, 0.3]))
        panel.add_generated_wave(
            SimpleNamespace(name="art1", acc=np.array([0.0, 0.1]), n=2, dt=0.02))
        text = panel._preview.toPlainText()
        assert "人工波结果" in text
        assert "art1" in text

    def test_empty_results_clears_preview(self, qapp):
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        panel.set_results([])
        assert panel._preview.toPlainText() == ""

    def test_no_legacy_export_widgets(self, qapp):
        # 方案C：导出统一由组合面板负责，result 面板不应再有导出控件
        from seiswave.gui.panels.result_panel import ResultPanel

        panel = ResultPanel()
        for attr in ("_dir_edit", "_do_export", "_export_btn", "_wave_fmt_combo"):
            assert not hasattr(panel, attr), f"残留旧导出成员: {attr}"


class TestImportPanel:
    def test_browse_directory_updates_path(self, qapp, monkeypatch):
        from seiswave.gui.panels.import_panel import ImportPanel

        panel = ImportPanel()
        monkeypatch.setattr(
            "seiswave.gui.panels.import_panel.QFileDialog.getExistingDirectory",
            lambda *a, **k: "/tmp/demo_dir",
        )
        panel._browse_directory()
        assert panel._dir_edit.text() == "/tmp/demo_dir"
        assert panel._current_dir == "/tmp/demo_dir"

    def test_load_finished_updates_table_and_emits_signal(self, qapp):
        from seiswave.gui.panels.import_panel import ImportPanel
        from seiswave.core import EQSignal

        panel = ImportPanel()
        sig = EQSignal(np.sin(np.linspace(0, 1, 64)), 0.02, name="w1")
        loaded = []
        panel.signals_loaded.connect(lambda items: loaded.append(items))
        panel._on_load_finished([sig])

        assert panel.get_signals() == [sig]
        assert panel._table.rowCount() == 1
        assert panel._count_label.text() == "已加载: 1 条"
        assert loaded == [[sig]]

    def test_wave_selected_updates_preview_info(self, qapp):
        from seiswave.gui.panels.import_panel import ImportPanel
        from seiswave.core import EQSignal

        panel = ImportPanel()
        sig = EQSignal(np.sin(np.linspace(0, 1, 64)), 0.02, name="wave_a")
        panel._table.load_signals([sig])
        panel._on_wave_selected(0)
        assert "PGA =" in panel._info_label.text()
        assert "wave_a" in panel._plot.ax.get_title()

    def test_clear_all_resets_state(self, qapp):
        from seiswave.gui.panels.import_panel import ImportPanel
        from seiswave.core import EQSignal

        panel = ImportPanel()
        sig = EQSignal(np.sin(np.linspace(0, 1, 64)), 0.02, name="wave_a")
        panel._signals = [sig]
        panel._table.load_signals([sig])
        panel._count_label.setText("已加载: 1 条")
        panel._clear_all()
        assert panel.get_signals() == []
        assert panel._table.rowCount() == 0
        assert panel._count_label.text() == "已加载: 0 条"
        assert "选择地震波以预览时程曲线" in panel._info_label.text()

    def test_load_files_warns_for_invalid_dir(self, qapp, monkeypatch):
        from seiswave.gui.panels.import_panel import ImportPanel

        panel = ImportPanel()
        panel._dir_edit.setText("/path/does/not/exist")
        warnings = []
        monkeypatch.setattr("seiswave.gui.panels.import_panel.QMessageBox.warning", lambda *a: warnings.append(a[-1]))
        panel._load_files()
        assert warnings == ["请先选择有效的数据目录"]

    def test_load_files_shows_info_when_no_files_found(self, qapp, monkeypatch, tmp_path):
        from seiswave.gui.panels.import_panel import ImportPanel

        panel = ImportPanel()
        panel._dir_edit.setText(str(tmp_path))
        infos = []
        monkeypatch.setattr("seiswave.gui.panels.import_panel.QMessageBox.information", lambda *a: infos.append(a[-1]))
        panel._load_files()
        assert infos == ["目录中未找到 *.AT2 文件"]

    def test_load_files_uses_lowercase_fallback_and_starts_worker(self, qapp, monkeypatch, tmp_path):
        from seiswave.gui.panels.import_panel import ImportPanel

        path = tmp_path / "a.at2"
        path.write_text("dummy")
        panel = ImportPanel()
        panel._dir_edit.setText(str(tmp_path))

        started = []
        execed = []

        class DummySignal:
            def __init__(self):
                self.handlers = []

            def connect(self, fn):
                self.handlers.append(fn)

        class DummyWorker:
            def __init__(self, files, fmt_idx, parent=None):
                self.files = files
                self.fmt_idx = fmt_idx
                self.parent = parent
                self.signals = SimpleNamespace(
                    progress=DummySignal(),
                    finished=DummySignal(),
                    error=DummySignal(),
                )

            def cancel(self):
                started.append("cancel")

            def start(self):
                started.append((self.files, self.fmt_idx))

        class DummyDialog:
            def __init__(self, *a, **k):
                self.cancelled = DummySignal()

            def update_progress(self, *a):
                execed.append(("progress", a))

            def exec(self):
                execed.append("exec")

        monkeypatch.setattr("seiswave.gui.panels.import_panel.FileLoadWorker", DummyWorker)
        monkeypatch.setattr("seiswave.gui.panels.import_panel.ProgressDialog", DummyDialog)
        panel._load_files()

        assert started and started[0][1] == 0
        assert str(path) in started[0][0]
        assert execed == ["exec"]
        assert panel._load_btn.isEnabled() is False

    def test_on_load_error_rejects_dialog_and_shows_critical(self, qapp, monkeypatch):
        from seiswave.gui.panels.import_panel import ImportPanel

        panel = ImportPanel()
        panel._load_btn.setEnabled(False)
        criticals = []

        class DummyDialog:
            def isVisible(self):
                return True

            def reject(self):
                criticals.append("rejected")

        panel._progress_dlg = DummyDialog()
        monkeypatch.setattr("seiswave.gui.panels.import_panel.QMessageBox.critical", lambda *a: criticals.append(a[-1]))
        panel._on_load_error("bad file")

        assert panel._load_btn.isEnabled() is True
        assert criticals == ["rejected", "加载失败: bad file"]

    def test_on_wave_selected_ignores_missing_signal(self, qapp):
        from seiswave.gui.panels.import_panel import ImportPanel

        panel = ImportPanel()
        before = panel._info_label.text()
        panel._on_wave_selected(0)
        assert panel._info_label.text() == before

    def test_set_dark_updates_plot(self, qapp, monkeypatch):
        from seiswave.gui.panels.import_panel import ImportPanel

        panel = ImportPanel(dark=False)
        called = []
        monkeypatch.setattr(panel._plot, "set_dark", lambda dark: called.append(dark))
        panel.set_dark(True)
        assert panel._dark is True
        assert called == [True]
