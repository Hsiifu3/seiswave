"""离屏渲染 SeisWave 主窗口各向导步骤, 截图以评估布局/挤压。"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import warnings; warnings.filterwarnings("ignore")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

app = QApplication(sys.argv)
from seiswave.gui.main_window import MainWindow
w = MainWindow()
w.resize(1280, 820)
w.show()
app.processEvents()

out_dir = "/tmp/seiswave_ui"
os.makedirs(out_dir, exist_ok=True)
names = ["step0_spectrum", "step1_select", "step2_generate", "step3_combine"]
for i, nm in enumerate(names):
    w._set_step(i)
    app.processEvents()
    for _ in range(3):
        app.processEvents()
    pm = w.grab()
    path = f"{out_dir}/{i}_{nm}.png"
    pm.save(path)
    print(f"saved {path}  ({pm.width()}x{pm.height()})", flush=True)

# 也单独截左侧 dock(设防参数)与生成面板的参数区
print("done", flush=True)
