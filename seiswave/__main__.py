"""SeisWave 入口点。"""

from __future__ import annotations

import faulthandler
import logging
import multiprocessing
import os
import sys
import tempfile
import traceback
from collections.abc import Sequence
from pathlib import Path

from seiswave.gui.fonts import qt_font, setup_matplotlib_fonts


LOG_DIR = Path(tempfile.gettempdir())
FAULT_LOG_PATH = LOG_DIR / "seiswave_fault.log"
APP_LOG_PATH = LOG_DIR / "seiswave.log"

_fault_log = FAULT_LOG_PATH.open("w", encoding="utf-8")
faulthandler.enable(file=_fault_log, all_threads=True)

logging.basicConfig(
    filename=str(APP_LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger("seiswave")


def _excepthook(exc_type, exc_value, exc_tb):
    """把未捕获异常写入启动日志。"""
    msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical("Uncaught exception:\n%s", msg)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _excepthook


def _set_multiprocessing_mode() -> None:
    """统一桌面入口的多进程启动方式。"""
    try:
        multiprocessing.set_start_method("spawn", force=True)
    except RuntimeError:
        logger.debug("Multiprocessing start method already initialized")


def create_application(argv: Sequence[str] | None = None):
    """创建或复用 QApplication，并应用全局字体/样式配置。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        app = QApplication(list(argv or sys.argv))

    app.setApplicationName("SeisWave")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("SeisWave")
    app.setFont(qt_font())
    return app


def create_main_window():
    """创建 SeisWave 工作台主窗口。"""
    from seiswave.gui.workbench.app_window import AppWindow

    return AppWindow()


def _configure_auto_quit(app) -> None:
    """为离屏烟测提供自动退出钩子。"""
    raw_value = os.environ.get("SEISWAVE_AUTO_QUIT_MS", "").strip()
    if not raw_value:
        return

    try:
        delay_ms = max(0, int(raw_value))
    except ValueError:
        logger.warning("Ignored invalid SEISWAVE_AUTO_QUIT_MS=%r", raw_value)
        return

    from PySide6.QtCore import QTimer

    QTimer.singleShot(delay_ms, app.quit)


def main(argv: Sequence[str] | None = None) -> int:
    """启动 SeisWave 工作台。"""
    logger.info("SeisWave starting...")
    _set_multiprocessing_mode()
    app = create_application(argv)
    setup_matplotlib_fonts()
    window = create_main_window()
    window.show()
    _configure_auto_quit(app)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
