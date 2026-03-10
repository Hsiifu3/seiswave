"""
SeisWave 入口点

python -m seiswave 启动 GUI 应用。
"""

import sys
import logging
import traceback
import faulthandler

# faulthandler 捕获 C 层 segfault
_fault_log = open('/tmp/seiswave_fault.log', 'w')
faulthandler.enable(file=_fault_log, all_threads=True)

# 配置日志到文件
logging.basicConfig(
    filename='/tmp/seiswave.log',
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    force=True,
)
logger = logging.getLogger('seiswave')

# 全局异常捕获
def _excepthook(exc_type, exc_value, exc_tb):
    msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical(f"Uncaught exception:\n{msg}")
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = _excepthook


def main():
    logger.info("SeisWave starting...")
    import multiprocessing
    multiprocessing.set_start_method('spawn', force=True)

    # Matplotlib 字体配置：中文宋体(Songti SC) + 英文 Times New Roman + 负号修复
    import matplotlib
    matplotlib.rcParams['font.family'] = ['Times New Roman', 'Songti SC']
    matplotlib.rcParams['axes.unicode_minus'] = False

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    # 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    app = QApplication(sys.argv)
    app.setApplicationName("SeisWave")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("SeisWave")

    # 设置默认字体
    from PySide6.QtGui import QFont
    import platform
    font = QFont()
    if platform.system() == "Darwin":
        font.setFamilies([".AppleSystemUIFont", "PingFang SC", "Helvetica Neue"])
    elif platform.system() == "Windows":
        font.setFamilies(["Microsoft YaHei UI", "Segoe UI"])
    else:
        font.setFamilies(["Noto Sans CJK SC", "sans-serif"])
    font.setPointSize(13)
    app.setFont(font)

    from seiswave.gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
