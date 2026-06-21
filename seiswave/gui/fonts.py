"""统一管理 SeisWave 的跨平台中英文字体。"""

from __future__ import annotations

import sys
from collections.abc import Iterable

from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication


def _available_font_families() -> set[str]:
    """返回当前 Qt 可见的字体家族；无图形上下文时安全降级。"""
    if QGuiApplication.instance() is None:
        return set()
    try:
        return {str(family) for family in QFontDatabase.families()}
    except Exception:
        return set()


def _pick_font(candidates: Iterable[str], available: set[str]) -> str:
    """从候选列表中挑选首个已安装字体；若未知则退回首选。"""
    candidate_list = list(candidates)
    if not candidate_list:
        raise ValueError("字体候选列表不能为空")
    if not available:
        return candidate_list[0]
    for family in candidate_list:
        if family in available:
            return family
    return candidate_list[-1]


def _cjk_candidates() -> tuple[str, ...]:
    """返回当前平台的中文字体优先链。"""
    if sys.platform.startswith("win"):
        return ("SimSun", "Noto Serif CJK SC", "Noto Sans CJK SC")
    if sys.platform == "darwin":
        return ("Songti SC", "Noto Serif CJK SC", "Noto Sans CJK SC")
    return ("Noto Serif CJK SC", "Noto Sans CJK SC")


def _latin_candidates() -> tuple[str, ...]:
    """返回英文字体优先链。"""
    return ("Times New Roman", "Times", "DejaVu Serif")


def cjk_font() -> str:
    """返回当前平台优先使用的中文字体。"""
    return _pick_font(_cjk_candidates(), _available_font_families())


def latin_font() -> str:
    """返回当前平台优先使用的英文字体。"""
    return _pick_font(_latin_candidates(), _available_font_families())


def setup_matplotlib_fonts() -> None:
    """设置 Matplotlib 全局字体。"""
    import matplotlib

    matplotlib.rcParams["font.family"] = [latin_font(), cjk_font()]
    matplotlib.rcParams["font.serif"] = [latin_font(), cjk_font()]
    matplotlib.rcParams["axes.unicode_minus"] = False


def qt_font() -> QFont:
    """返回工作台默认 Qt 字体。"""
    font = QFont()
    font.setFamilies([cjk_font(), latin_font()])
    font.setPointSize(12)
    return font
