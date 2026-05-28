"""UI 生成状态验证（mock worker，验证界面不闪退）"""
import sys
import os
sys.path.insert(0, os.path.expanduser("~/Developer/seiswave"))

import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QEventLoop

from seiswave.gui.panels.generator_panel import GeneratorPanel
from seiswave.core.code_spec import CodeSpectrum
from seiswave.core.signal import EQSignal


def test_ui_generation_transitions():
    app = QApplication.instance() or QApplication(sys.argv)
    gp = GeneratorPanel(dark=False)
    gp.show()

    cs = CodeSpectrum()
    periods = np.logspace(-1, 1, 50)
    sa = cs.from_params(periods, 8, 2, 'II', 'frequent', 0.05)
    gp.set_code_spectrum(periods, sa)
    app.processEvents()

    # Mock: 拦截 worker 创建，直接 emit finished 信号
    original_run_general = gp._controller.run_general
    original_run_special = gp._controller.run_special

    mock_signals = {}

    def mock_run_general(param_form, code_periods, code_sa):
        # 模拟生成成功
        mock_sig = EQSignal(np.zeros(100), 0.02, name="mock_general")
        result = {
            'best': mock_sig,
            'all_results': [mock_sig],
            'best_index': 0,
        }
        QTimer.singleShot(100, lambda: gp._controller.finished.emit(result, "一般人工波"))

    def mock_run_special(param_form, code_periods, code_sa):
        params = param_form.get_params()
        label = params['type_label']
        t = np.arange(100) * 0.01
        acc = np.sin(2 * np.pi * 2.0 * t) * 0.1
        mock_sig = EQSignal(acc, 0.01, name=f"mock_{label}")
        # NFP mock: 添加脉冲参数
        if label == "近场脉冲 NFP":
            class _MockPulseParams:
                Tp = 2.5
                A = 50.0
                phi = 1.2
                t0 = 5.0
            mock_sig.pulse_params = _MockPulseParams()
            mock_sig.pulse_metrics = {
                'has_pulse': True,
                'confidence': 0.85,
                'pulse_period': 2.5,
                'pulse_amplitude': 50.0,
                'energy_ratio': 0.72,
            }
        QTimer.singleShot(100, lambda: gp._controller.finished.emit(mock_sig, label))

    gp._controller.run_general = mock_run_general
    gp._controller.run_special = mock_run_special

    def run_and_verify(type_index, label, expect_nfp=False):
        gp._param_form.set_type(type_index)
        app.processEvents()

        loop = QEventLoop()
        done = [False]

        def on_done(sig):
            done[0] = True
            mock_signals[label] = sig
            loop.quit()

        gp.wave_generated.connect(on_done)

        # 点击生成按钮
        assert gp._param_form._run_btn.isEnabled(), f"{label} 生成按钮应可用"
        gp._param_form._run_btn.click()
        app.processEvents()

        # 验证按钮被禁用、进度条启动、底部栏更新
        assert not gp._param_form._run_btn.isEnabled(), f"{label} 生成中按钮应被禁用"
        assert gp._bottom_bar._status.text() == "正在生成...", f"{label} 底部栏应显示正在生成"

        QTimer.singleShot(5000, loop.quit)  # 超时保险
        loop.exec()
        gp.wave_generated.disconnect(on_done)

        assert done[0], f"{label} 生成信号未收到"
        actual_status = gp._bottom_bar._status.text()
        assert gp._param_form._run_btn.isEnabled(), f"{label} 生成完成后按钮应恢复"
        assert actual_status == "生成完成", f"{label} 底部栏应显示生成完成, 实际: {actual_status}"
        assert gp._right_panel._lbl_type.text() != "--", f"{label} 右栏应显示结果"

        if expect_nfp:
            assert gp._right_panel._nfp_card.isVisible(), f"{label} NFP 卡片应可见"
            assert gp._right_panel._nfp_card._baker_bar.value() > 0, f"{label} Baker 置信度应 > 0"
        else:
            assert not gp._right_panel._nfp_card.isVisible(), f"{label} NFP 卡片应隐藏"

        print(f"✅ {label} UI 状态验证通过")

    # 1. 一般人工波
    run_and_verify(0, "一般人工波", expect_nfp=False)

    # 2. 远场 FF
    run_and_verify(1, "远场 FF", expect_nfp=False)

    # 3. 近场无脉冲 NF
    run_and_verify(2, "近场 NF", expect_nfp=False)

    # 4. 近场脉冲 NFP
    run_and_verify(3, "近场脉冲 NFP", expect_nfp=True)

    # 额外验证：切换回一般波时 NFP 卡片隐藏
    gp._param_form.set_type(0)
    app.processEvents()
    assert not gp._right_panel._nfp_card.isVisible()
    print("✅ 切换回一般波后 NFP 卡片正确隐藏")

    # 截图
    from PySide6.QtGui import QPixmap
    pixmap = QPixmap(gp.size())
    gp.render(pixmap)
    path = os.path.expanduser("~/Developer/seiswave/.specs/001-special-ground-motion/ui-verify-mock.png")
    pixmap.save(path)
    print(f"✅ Mock 验证截图已保存: {path}")

    print("\n🎉 全部 UI 生成状态验证通过（mock worker）")
    gp.close()
    app.quit()


if __name__ == "__main__":
    test_ui_generation_transitions()
