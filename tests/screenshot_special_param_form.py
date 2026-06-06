"""离屏截图验证 FF/NF/NFP 的新控件（目标谱来源 + 近场系数标签）。"""
import sys
import os

# 设置离屏渲染
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, "/Users/yachiyo/Developer/seiswave")

from PySide6.QtWidgets import QApplication
from seiswave.gui.panels.param_form import ParamFormWidget


def main():
    app = QApplication([])
    form = ParamFormWidget()

    # 切到 NF、R=3 → 应显示 ×1.5
    form._type_combo.setCurrentIndex(2)  # "近场无脉冲 NF"
    form._r_spin.setValue(3.0)

    # 抓 param_form 截图
    pixmap = form.grab()
    out_path = "/tmp/seiswave_special_param_form_nf_r3.png"
    pixmap.save(out_path)
    print(f"saved {out_path}  (NF R=3 → 近场系数应显示 ×1.5)")

    # FF R=50 → ×1.0 (远场无放大)
    form._type_combo.setCurrentIndex(1)  # "远场 FF"
    form._r_spin.setValue(50.0)
    pixmap2 = form.grab()
    out_path2 = "/tmp/seiswave_special_param_form_ff_r50.png"
    pixmap2.save(out_path2)
    print(f"saved {out_path2}  (FF R=50 → 近场系数应显示 ×1.0 远场无放大)")

    # 验证 get_params 有 spectrum_source
    params = form.get_params()
    assert "spectrum_source" in params, "get_params 缺 spectrum_source"
    assert params["spectrum_source"] in ("code", "gmpe"), f"spectrum_source={params['spectrum_source']} 非法"
    print(f"get_params['spectrum_source'] = {params['spectrum_source']} ✓")


if __name__ == "__main__":
    main()
