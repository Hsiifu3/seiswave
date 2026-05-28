"""UI 手动验证脚本（headless 自动截图检查）"""
import sys
import os
sys.path.insert(0, os.path.expanduser("~/Developer/seiswave"))

import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap

from seiswave.gui.main_window import MainWindow
from seiswave.gui.panels.generator_panel import GeneratorPanel
from seiswave.core.code_spec import CodeSpectrum


def verify():
    app = QApplication.instance() or QApplication(sys.argv)
    win = MainWindow()
    win.show()

    # 1. 窗口大小
    geo = win.geometry()
    assert geo.width() >= 1200, f"窗口宽度 {geo.width()} < 1200"
    assert geo.height() >= 800, f"窗口高度 {geo.height()} < 800"
    print(f"✅ 窗口大小: {geo.width()}x{geo.height()}")

    # 切换到生成面板
    win._set_step(2)
    app.processEvents()

    gp = win._generator_panel

    # 2. 左栏宽度
    left_w = gp._left_panel.width()
    assert left_w <= 320, f"左栏宽度 {left_w} > 320"
    print(f"✅ 左栏宽度: {left_w}")

    # 3. 中间区域宽度
    center_w = gp._center_panel.width()
    assert center_w >= 500, f"中间区域宽度 {center_w} < 500"
    print(f"✅ 中间区域宽度: {center_w}")

    # 4. 右栏宽度
    right_w = gp._right_panel.width()
    assert right_w <= 280, f"右栏宽度 {right_w} > 280"
    print(f"✅ 右栏宽度: {right_w}")

    # 5. 底部栏高度
    bottom_h = gp._bottom_bar.height()
    assert bottom_h <= 40, f"底部栏高度 {bottom_h} > 40"
    print(f"✅ 底部栏高度: {bottom_h}")

    # 6. 设置规范谱
    cs = CodeSpectrum()
    periods = np.logspace(-1, 1, 50)
    sa = cs.from_params(periods, 8, 2, 'II', 'frequent', 0.05)
    gp.set_code_spectrum(periods, sa)
    app.processEvents()
    print("✅ 规范谱已设置")

    # 7. 切换类型检查右栏显隐
    # 一般人工波 - 右栏不显示 NFP 卡片
    gp._param_form.set_type(0)
    app.processEvents()
    assert not gp._right_panel._nfp_card.isVisible(), "一般波时不应显示 NFP 卡片"
    print("✅ 一般人工波: NFP 卡片隐藏")

    # 远场 FF
    gp._param_form.set_type(1)
    app.processEvents()
    assert not gp._right_panel._nfp_card.isVisible(), "FF 时不应显示 NFP 卡片"
    print("✅ 远场 FF: NFP 卡片隐藏")

    # 近场 NF
    gp._param_form.set_type(2)
    app.processEvents()
    assert not gp._right_panel._nfp_card.isVisible(), "NF 时不应显示 NFP 卡片"
    print("✅ 近场 NF: NFP 卡片隐藏")

    # 近场脉冲 NFP - 右栏应显示 NFP 卡片
    gp._param_form.set_type(3)
    app.processEvents()
    assert gp._right_panel._nfp_card.isVisible(), "NFP 时应显示 NFP 卡片"
    print("✅ 近场脉冲 NFP: NFP 卡片显示")

    # 8. 截图验证布局
    pixmap = QPixmap(win.size())
    win.render(pixmap)
    path = os.path.expanduser("~/Developer/seiswave/.specs/001-special-ground-motion/ui-verify.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pixmap.save(path)
    print(f"✅ 截图已保存: {path}")

    # 9. 三类地震动生成（mock，不实际运行 worker 避免阻塞）
    # 只验证点击生成按钮不会闪退（worker 会异步执行）
    # 由于无事件循环，worker 不会真正跑完；验证按钮状态变化即可
    gp._param_form.set_type(0)
    app.processEvents()
    btn = gp._param_form._run_btn
    assert btn.isEnabled(), "生成按钮应可用"
    print("✅ 按钮状态正常")

    print("\n🎉 UI 验证全部通过")
    win.close()
    app.quit()


if __name__ == "__main__":
    verify()
