"""Quick figure export widget."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QMessageBox
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .common import ensure_directory


class PlotExportTool(QWidget):
    """Export the current preview figures to disk."""

    VIEW_OPTIONS = {
        "all": ("全部视图", ("acc", "vel", "disp", "spectrum")),
        "acc": ("加速度", ("acc",)),
        "vel": ("速度", ("vel",)),
        "disp": ("位移", ("disp",)),
        "spectrum": ("反应谱", ("spectrum",)),
    }

    def __init__(self, preview_panel, notify, parent=None) -> None:
        super().__init__(parent)
        self._preview_panel = preview_panel
        self._notify = notify
        self._dir_edit: QLineEdit | None = None
        self._prefix_edit: QLineEdit | None = None
        self._view_combo: QComboBox | None = None
        self._format_combo: QComboBox | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()

        path_row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("输出目录")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_directory)
        path_row.addWidget(self._dir_edit, 1)
        path_row.addWidget(browse_btn)
        form.addRow("目录:", path_row)

        self._prefix_edit = QLineEdit("preview")
        form.addRow("文件前缀:", self._prefix_edit)

        self._view_combo = QComboBox()
        for key, (label, _views) in self.VIEW_OPTIONS.items():
            self._view_combo.addItem(label, key)
        form.addRow("图形:", self._view_combo)

        self._format_combo = QComboBox()
        for ext in ("png", "pdf", "svg"):
            self._format_combo.addItem(ext.upper(), ext)
        form.addRow("格式:", self._format_combo)
        layout.addLayout(form)

        export_btn = QPushButton("导出图")
        export_btn.clicked.connect(self.export)
        layout.addWidget(export_btn)

    def _browse_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择图像输出目录")
        if path and self._dir_edit is not None:
            self._dir_edit.setText(path)

    def export(self) -> list[Path]:
        try:
            assert self._dir_edit is not None
            assert self._prefix_edit is not None
            assert self._view_combo is not None
            assert self._format_combo is not None
            output_dir = ensure_directory(self, self._dir_edit.text(), "快捷出图")
            if output_dir is None:
                return []

            prefix = self._prefix_edit.text().strip() or "preview"
            format_name = str(self._format_combo.currentData())
            view_key = str(self._view_combo.currentData())
            _label, views = self.VIEW_OPTIONS[view_key]

            written: list[Path] = []
            for view_name in views:
                out_path = output_dir / f"{prefix}-{view_name}.{format_name}"
                written.append(
                    self._preview_panel.export_plot(view_name, out_path, dpi=300)
                )

            self._notify(f"已导出 {len(written)} 张图到 {output_dir}")
            return written
        except Exception as exc:
            QMessageBox.critical(self, "快捷出图", str(exc))
            return []

    def state(self) -> dict[str, object]:
        assert self._dir_edit is not None
        assert self._prefix_edit is not None
        assert self._view_combo is not None
        assert self._format_combo is not None
        return {
            "output_dir": self._dir_edit.text(),
            "prefix": self._prefix_edit.text(),
            "view": self._view_combo.currentData(),
            "format": self._format_combo.currentData(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        if state is None:
            state = {}
        assert self._dir_edit is not None
        assert self._prefix_edit is not None
        assert self._view_combo is not None
        assert self._format_combo is not None
        self._dir_edit.setText(str(state.get("output_dir", "")))
        self._prefix_edit.setText(str(state.get("prefix", "preview")))
        view = str(state.get("view", "all"))
        index = self._view_combo.findData(view)
        if index >= 0:
            self._view_combo.setCurrentIndex(index)
        format_name = str(state.get("format", "png"))
        index = self._format_combo.findData(format_name)
        if index >= 0:
            self._format_combo.setCurrentIndex(index)
