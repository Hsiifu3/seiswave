#!/usr/bin/env python3
"""SeisWave 带日志启动器（用于稳定性调试）"""

import atexit
import logging
import os
import signal
import sys
import traceback
from datetime import datetime
from pathlib import Path
import faulthandler

# 确保从 scripts/ 运行时也能导入项目包
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

LOG_DIR = Path.home() / ".seiswave" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = LOG_DIR / f"seiswave_{timestamp}.log"
FAULT_LOG = LOG_DIR / f"fault_{timestamp}.log"
PID_FILE = LOG_DIR / "seiswave.pid"

_fault_file = None


def setup_logging() -> logging.Logger:
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.handlers.clear()

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return logging.getLogger("seiswave.launcher")


def setup_crash_handler() -> None:
    global _fault_file
    _fault_file = open(FAULT_LOG, "w", encoding="utf-8")
    faulthandler.enable(file=_fault_file, all_threads=True)

    original_excepthook = sys.excepthook

    def custom_excepthook(exc_type, exc_value, exc_tb):
        logger = logging.getLogger("seiswave.crash")
        logger.critical("=" * 60)
        logger.critical("未捕获异常")
        logger.critical("=" * 60)

        error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical(error_msg)

        with open(FAULT_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"Exception at {datetime.now()}\n")
            f.write(f"{'=' * 60}\n")
            f.write(error_msg)

        original_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = custom_excepthook


def write_pid() -> None:
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")


def cleanup_pid() -> None:
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
    except Exception:
        pass


def cleanup_fault_file() -> None:
    global _fault_file
    try:
        if _fault_file and not _fault_file.closed:
            _fault_file.flush()
            _fault_file.close()
    except Exception:
        pass


def signal_handler(signum, frame):
    logger = logging.getLogger("seiswave.signal")
    sig_name = signal.Signals(signum).name
    logger.warning("收到信号: %s (%s)", sig_name, signum)
    cleanup_pid()
    cleanup_fault_file()
    # 保留真实退出语义：128 + signal
    raise SystemExit(128 + signum)


def main() -> None:
    logger = setup_logging()
    setup_crash_handler()

    atexit.register(cleanup_pid)
    atexit.register(cleanup_fault_file)

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    write_pid()

    logger.info("=" * 60)
    logger.info("SeisWave 启动")
    logger.info("=" * 60)
    logger.info("Python: %s", sys.version.replace("\n", " "))
    logger.info("CWD: %s", os.getcwd())
    logger.info("LOG: %s", LOG_FILE)
    logger.info("FAULT: %s", FAULT_LOG)
    logger.info("PID: %s", os.getpid())

    try:
        from seiswave.__main__ import main as seiswave_main
        logger.info("启动 GUI 应用...")
        seiswave_main()
    except Exception:
        logger.exception("启动失败")
        raise
    finally:
        logger.info("SeisWave 退出")


if __name__ == "__main__":
    main()
