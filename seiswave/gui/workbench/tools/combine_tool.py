"""Combination validation/export tool."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from seiswave.core.combiner import Combiner, WaveGroup

from .common import ToolWidget, ensure_directory, selected_records_or_warn, target_or_warn, to_eqsignal


class CombineTool(ToolWidget):
    """Validate and export the final selected record set."""

    def __init__(self, pool, target_service, notify, parent=None) -> None:
        super().__init__(parent)
        self._pool = pool
        self._target_service = target_service
        self._notify = notify
        self._dir_edit: QLineEdit | None = None
        self._fmt_combo: QComboBox | None = None
        self._html_check: QCheckBox | None = None
        self._summary_label: QLabel | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel(
            "从当前选中信号组装最终波组，复用 Combiner 做平均谱/单条谱校核并导出。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        row = QHBoxLayout()
        self._dir_edit = QLineEdit()
        self._dir_edit.setPlaceholderText("输出目录")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_output_dir)
        row.addWidget(self._dir_edit, 1)
        row.addWidget(browse_btn)
        form.addRow("输出目录:", row)

        self._fmt_combo = QComboBox()
        self._fmt_combo.addItem("AT2", "at2")
        self._fmt_combo.addItem("TXT", "txt")
        self._fmt_combo.addItem("AT2 + TXT", "both")
        form.addRow("波形格式:", self._fmt_combo)

        self._html_check = QCheckBox("生成 HTML 报告")
        self._html_check.setChecked(True)
        form.addRow("报告:", self._html_check)

        layout.addLayout(form)

        self._summary_label = QLabel("等待校核...")
        self._summary_label.setWordWrap(True)
        layout.addWidget(self._summary_label)
        layout.addStretch(1)

    def _browse_output_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择组合输出目录")
        if path and self._dir_edit is not None:
            self._dir_edit.setText(path)

    def run_tool(self) -> dict[str, object] | None:
        try:
            records = selected_records_or_warn(self, self._pool, "组合校核")
            if not records:
                return None
            target = target_or_warn(self, self._target_service, "组合校核")
            if target is None:
                return None
            periods, target_sa = target
            combiner = self._build_combiner(records)
            validation = combiner.validate(float(np.max(target_sa)), target_sa, periods)
            output_dir = self._export_outputs(combiner, target_sa, periods)
            self._update_summary(validation, output_dir)
            status = "通过" if validation.passed else "未通过"
            self._notify(f"组合校核完成：{status}，共 {validation.n_groups} 组")
            return {
                "combiner": combiner,
                "validation": validation,
                "output_dir": output_dir,
            }
        except Exception as exc:
            QMessageBox.critical(self, "组合校核", str(exc))
            return None

    def _build_combiner(self, records):
        combiner = Combiner(output_dir=str(Path.cwd() / "output"))
        for record in records:
            sig = to_eqsignal(record)
            meta = record.meta
            group = WaveGroup(
                name=record.name,
                source="natural" if record.kind == "natural" else "artificial",
                rsn=int(meta.get("rsn", 0) or 0),
                event=str(meta.get("event", "")),
                station=str(meta.get("station", "")),
                scale_factor=float(meta.get("scale_factor", 1.0)),
                match_error=float(meta.get("match_rmse", 0.0)),
                h1=sig,
            )
            combiner.groups.append(group)
        return combiner

    def _export_outputs(self, combiner, target_sa, periods) -> str | None:
        assert self._fmt_combo is not None
        assert self._html_check is not None
        assert self._dir_edit is not None

        output_dir = None
        if self._dir_edit.text().strip():
            directory = ensure_directory(self, self._dir_edit.text(), "组合校核")
            if directory is None:
                return None
            combiner.output_dir = str(directory)
            output_dir = combiner.export(fmt=str(self._fmt_combo.currentData()))
            if self._html_check.isChecked():
                combiner.generate_html_report(target_sa, periods)
        return output_dir

    def _update_summary(self, validation, output_dir: str | None) -> None:
        assert self._summary_label is not None
        lines = [
            f"校核结果: {'通过' if validation.passed else '未通过'}",
            f"组数: {validation.n_groups}/{validation.n_required}",
            f"平均谱校核: {'通过' if validation.mean_check else '未通过'}",
        ]
        if validation.mean_ratios is not None and len(validation.mean_ratios) > 0:
            lines.append(f"平均谱最小比值: {float(np.min(validation.mean_ratios)):.3f}")
        if output_dir:
            lines.append(f"输出目录: {output_dir}")
        self._summary_label.setText("\n".join(lines))

    def state(self) -> dict[str, object]:
        assert self._dir_edit is not None
        assert self._fmt_combo is not None
        assert self._html_check is not None
        return {
            "output_dir": self._dir_edit.text(),
            "fmt": self._fmt_combo.currentData(),
            "html": self._html_check.isChecked(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        if state is None:
            state = {}
        assert self._dir_edit is not None
        assert self._fmt_combo is not None
        assert self._html_check is not None
        self._dir_edit.setText(str(state.get("output_dir", "")))
        index = self._fmt_combo.findData(state.get("fmt", "at2"))
        if index >= 0:
            self._fmt_combo.setCurrentIndex(index)
        self._html_check.setChecked(bool(state.get("html", True)))
