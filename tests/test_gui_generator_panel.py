"""
GUI 生成面板单元测试

验证：
1. 地震动类型切换时参数面板正确显示/隐藏
2. 默认选中"一般人工波"，向后兼容
3. GM_TYPE_CODES 映射正确
4. SpecialGroundMotionWorker 可正确实例化
"""

import pytest
import numpy as np


# ── 无需 QApplication 的纯逻辑测试 ──

class TestGMTypeMapping:
    """验证类型映射常量"""

    def test_labels_length(self):
        from seiswave.gui.panels.generator_panel import GM_TYPE_LABELS, GM_TYPE_CODES
        assert len(GM_TYPE_LABELS) == 4
        assert len(GM_TYPE_CODES) == 4

    def test_default_is_general(self):
        from seiswave.gui.panels.generator_panel import GM_TYPE_LABELS
        assert GM_TYPE_LABELS[0] == "一般人工波"

    def test_code_mapping(self):
        from seiswave.gui.panels.generator_panel import GM_TYPE_CODES
        assert GM_TYPE_CODES["一般人工波"] is None
        assert GM_TYPE_CODES["远场 FF"] == "FF"
        assert GM_TYPE_CODES["近场无脉冲 NF"] == "NF"
        assert GM_TYPE_CODES["近场脉冲 NFP"] == "NFP"


# ── 需要 QApplication 的 GUI 测试 ──

@pytest.fixture(scope="module")
def qapp():
    """提供共享的 QApplication 实例"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestGeneratorPanelUI:
    """验证 GeneratorPanel UI 状态切换"""

    def test_panel_imports(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        assert panel is not None

    def test_default_type_is_general(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        assert panel._type_combo.currentText() == "一般人工波"

    def test_special_group_hidden_by_default(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        assert panel._special_group.isHidden()

    def test_switch_to_ff_shows_special(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        panel._type_combo.setCurrentIndex(1)  # 远场 FF
        assert not panel._special_group.isHidden()

    def test_switch_to_nf_shows_special(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        panel._type_combo.setCurrentIndex(2)  # 近场无脉冲 NF
        assert not panel._special_group.isHidden()

    def test_switch_to_nfp_shows_special_and_fault(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        panel._type_combo.setCurrentIndex(3)  # 近场脉冲 NFP
        assert not panel._special_group.isHidden()
        assert panel._fault_combo.isEnabled()

    def test_switch_back_to_general_hides_special(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        panel._type_combo.setCurrentIndex(1)
        assert not panel._special_group.isHidden()
        panel._type_combo.setCurrentIndex(0)
        assert panel._special_group.isHidden()

    def test_ff_nf_fault_combo_disabled(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        panel._type_combo.setCurrentIndex(1)  # FF
        assert not panel._fault_combo.isEnabled()
        panel._type_combo.setCurrentIndex(2)  # NF
        assert not panel._fault_combo.isEnabled()

    def test_dt_default_changes_with_type(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)

        panel._type_combo.setCurrentIndex(0)  # general
        assert panel._dt_spin.value() == pytest.approx(0.02, abs=0.001)

        panel._type_combo.setCurrentIndex(1)  # FF
        assert panel._dt_spin.value() == pytest.approx(0.02, abs=0.001)

        panel._type_combo.setCurrentIndex(2)  # NF
        assert panel._dt_spin.value() == pytest.approx(0.01, abs=0.001)

        panel._type_combo.setCurrentIndex(3)  # NFP
        assert panel._dt_spin.value() == pytest.approx(0.01, abs=0.001)

    def test_button_text_changes(self, qapp):
        from seiswave.gui.panels.generator_panel import GeneratorPanel
        panel = GeneratorPanel(dark=False)
        panel._type_combo.setCurrentIndex(3)
        assert "NFP" in panel._run_btn.text()


class TestSpecialGroundMotionWorker:
    """验证 SpecialGroundMotionWorker 基础行为"""

    def test_worker_instantiation(self, qapp):
        from seiswave.gui.workers import SpecialGroundMotionWorker
        worker = SpecialGroundMotionWorker(
            gm_type="FF", Mw=7.0, R=50.0, Vs30=760.0,
            fault_type="strike_slip", n=1024, dt=0.02,
        )
        assert worker._gm_type == "FF"
        assert worker._Mw == 7.0

    def test_worker_ff_execution_mock(self, qapp, monkeypatch):
        """用 mock 验证 worker 执行路径正确，不触发真实生成"""
        from seiswave.gui.workers import SpecialGroundMotionWorker
        from seiswave.core.signal import EQSignal

        mock_signal = EQSignal(np.zeros(100), 0.02, name="mock_ff")

        def mock_create_ground_motion(**kwargs):
            # 验证关键参数透传正确
            assert kwargs['type'] == "FF"
            assert kwargs['Mw'] == 7.5
            assert kwargs['R'] == 10.0
            assert kwargs['Vs30'] == 360.0
            assert kwargs['fault_type'] == "reverse"
            return mock_signal

        monkeypatch.setattr(
            'seiswave.core.generator.create_ground_motion',
            mock_create_ground_motion
        )

        worker = SpecialGroundMotionWorker(
            gm_type="FF", Mw=7.5, R=10.0, Vs30=360.0,
            fault_type="reverse", n=1024, dt=0.02,
        )
        result = worker.execute()
        assert result is mock_signal
        assert result.name == "mock_ff"
