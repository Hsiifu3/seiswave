"""统一管理 SeisWave 的跨平台中英文字体。"""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont


def cjk_font() -> str:
    """返回当前平台优先使用的中文字体。"""
    if sys.platform.startswith("win"):
        return "SimSun"
    if sys.platform == "darwin":
        return "Songti SC"
    return "Noto Serif CJK SC"


def setup_matplotlib_fonts() -> None:
    """设置 Matplotlib 全局字体。"""
    import matplotlib

    matplotlib.rcParams["font.family"] = ["Times New Roman", cjk_font()]
    matplotlib.rcParams["axes.unicode_minus"] = False


def qt_font() -> QFont:
    """返回工作台默认 Qt 字体。"""
    font = QFont()
    font.setFamilies([cjk_font(), "Times New Roman"])
    font.setPointSize(12)
    return font
