import warnings
from functools import lru_cache
from pathlib import Path
import subprocess

from pyparsing.warnings import PyparsingDeprecationWarning


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IGNORED_TRACKED_TESTS = {
    "tests/test_fortran.py",
}


# Matplotlib currently imports deprecated pyparsing compatibility helpers on
# Python 3.9. Re-apply the filter in pytest_configure because pytest's warning
# plugin can reorder filters after module import.
def _suppress_matplotlib_pyparsing_warnings() -> None:
    warnings.filterwarnings("ignore", category=PyparsingDeprecationWarning)


_suppress_matplotlib_pyparsing_warnings()


def pytest_configure(config):
    _suppress_matplotlib_pyparsing_warnings()


@lru_cache(maxsize=1)
def _tracked_test_files() -> set[str]:
    """返回已纳入 git 的正式测试文件集合。"""
    try:
        result = subprocess.run(
            ["git", "ls-files", "tests"],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def pytest_ignore_collect(collection_path, config):
    """忽略未纳入版本控制的实验脚本与手工诊断测试。"""
    path = Path(str(collection_path))
    if path.is_dir() or path.suffix != ".py":
        return False

    try:
        relative = path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return False

    if not relative.startswith("tests/"):
        return False

    if relative in IGNORED_TRACKED_TESTS:
        return True

    tracked_files = _tracked_test_files()
    if tracked_files and relative not in tracked_files:
        return True

    return False
