"""
SeisWave 入口点

python -m seiswave 启动 GUI 应用。
"""

import sys


def main():
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
    font = QFont()
    font.setPointSize(13)
    app.setFont(font)

    from seiswave.gui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
