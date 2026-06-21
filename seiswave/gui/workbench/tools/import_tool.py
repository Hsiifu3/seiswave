"""Signal import tool."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from seiswave.core.io import FileIO
from seiswave.core.signal_pool import SignalRecord

from .common import ToolWidget


class ImportTool(ToolWidget):
    """Import PEER / AT2 / TXT records into the shared signal pool."""

    def __init__(self, pool, notify, parent=None) -> None:
        super().__init__(parent)
        self._pool = pool
        self._notify = notify
        self._path_edit: QLineEdit | None = None
        self._mode_combo: QComboBox | None = None
        self._pattern_combo: QComboBox | None = None
        self._recursive_check: QCheckBox | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("选择目录或单个 AT2/TXT 文件")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse_btn)
        form.addRow("来源路径:", path_row)

        self._mode_combo = QComboBox()
        self._mode_combo.addItem("目录导入", "directory")
        self._mode_combo.addItem("单文件导入", "file")
        form.addRow("导入模式:", self._mode_combo)

        self._pattern_combo = QComboBox()
        self._pattern_combo.addItem("自动识别 AT2/TXT", "auto")
        self._pattern_combo.addItem("仅 PEER/AT2", "at2")
        self._pattern_combo.addItem("仅 TXT/DAT", "txt")
        form.addRow("目录筛选:", self._pattern_combo)

        self._recursive_check = QCheckBox("递归子目录")
        form.addRow("目录选项:", self._recursive_check)
        layout.addLayout(form)
        layout.addStretch(1)

    def _browse(self) -> None:
        assert self._mode_combo is not None
        if self._mode_combo.currentData() == "file":
            path, _ = QFileDialog.getOpenFileName(
                self,
                "选择 AT2/TXT 文件",
                "",
                "Ground Motion (*.AT2 *.at2 *.txt *.TXT *.dat *.DAT)",
            )
        else:
            path = QFileDialog.getExistingDirectory(self, "选择地震动目录")
        if path and self._path_edit is not None:
            self._path_edit.setText(path)

    def run_tool(self) -> list[SignalRecord]:
        try:
            assert self._path_edit is not None
            assert self._mode_combo is not None
            source_path = Path(self._path_edit.text().strip()).expanduser()
            if not source_path.exists():
                raise FileNotFoundError(f"导入路径不存在: {source_path}")

            if self._mode_combo.currentData() == "file":
                loaded = [self._load_file(source_path)]
            else:
                loaded = self._load_directory(source_path)

            records: list[SignalRecord] = []
            selection_ids: list[str] = []
            for eq_record in loaded:
                meta = dict(eq_record.metadata)
                meta.update(
                    {
                        "source": source_path.name,
                        "file_name": Path(eq_record.filepath or eq_record.name).name,
                        "filepath": str(eq_record.filepath or source_path),
                    }
                )
                record = SignalRecord(
                    acc=eq_record.acc,
                    dt=eq_record.dt,
                    name=eq_record.name,
                    kind="natural",
                    meta=meta,
                )
                selection_ids.append(self._pool.add(record))
                records.append(record)

            self._pool.set_selection(selection_ids)
            self._notify(f"已导入 {len(records)} 条信号")
            return records
        except Exception as exc:
            QMessageBox.critical(self, "导入", str(exc))
            return []

    def _load_directory(self, directory: Path):
        assert self._pattern_combo is not None
        assert self._recursive_check is not None
        pattern = str(self._pattern_combo.currentData())
        recursive = self._recursive_check.isChecked()

        if recursive:
            candidates = [path for path in directory.rglob("*") if path.is_file()]
        else:
            candidates = [path for path in directory.iterdir() if path.is_file()]

        def allowed(path: Path) -> bool:
            suffix = path.suffix.lower()
            if pattern == "at2":
                return suffix == ".at2"
            if pattern == "txt":
                return suffix in {".txt", ".dat"}
            return suffix in {".at2", ".txt", ".dat"}

        loaded = [self._load_file(path) for path in sorted(candidates) if allowed(path)]
        if not loaded:
            raise ValueError(f"目录中未找到可导入的 AT2/TXT 文件: {directory}")
        return loaded

    def _load_file(self, path: Path):
        suffix = path.suffix.lower()
        if suffix == ".at2":
            return FileIO.read_at2(str(path))
        if suffix in {".txt", ".dat"}:
            return FileIO._auto_read_txt(str(path))
        raise ValueError(f"不支持的导入格式: {path.suffix}")

    def state(self) -> dict[str, object]:
        assert self._path_edit is not None
        assert self._mode_combo is not None
        assert self._pattern_combo is not None
        assert self._recursive_check is not None
        return {
            "path": self._path_edit.text(),
            "mode": self._mode_combo.currentData(),
            "pattern": self._pattern_combo.currentData(),
            "recursive": self._recursive_check.isChecked(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        if state is None:
            state = {}
        assert self._path_edit is not None
        assert self._mode_combo is not None
        assert self._pattern_combo is not None
        assert self._recursive_check is not None
        self._path_edit.setText(str(state.get("path", "")))
        mode = str(state.get("mode", "directory"))
        index = self._mode_combo.findData(mode)
        if index >= 0:
            self._mode_combo.setCurrentIndex(index)
        pattern = str(state.get("pattern", "auto"))
        index = self._pattern_combo.findData(pattern)
        if index >= 0:
            self._pattern_combo.setCurrentIndex(index)
        self._recursive_check.setChecked(bool(state.get("recursive", False)))
