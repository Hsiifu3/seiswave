"""Quick data export widget."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
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

from seiswave.core.io import FileIO
from seiswave.gui.workbench.scorecard import compute_scorecard_metrics

from .common import ensure_directory, selected_records_or_warn


def _safe_stem(name: str) -> str:
    """净化文件名干：替换路径分隔符、空白与中点等不便落盘的字符。"""
    cleaned = []
    for ch in str(name):
        if ch in '/\\:*?"<>|':
            cleaned.append("_")
        elif ch.isspace() or ch == "·":
            cleaned.append("_")
        else:
            cleaned.append(ch)
    stem = "".join(cleaned).strip("._")
    return stem or "export"


class DataExportTool(QWidget):
    """Export time histories, spectra, and summary tables."""

    def __init__(self, pool, target_service, preview_panel, notify, parent=None) -> None:
        super().__init__(parent)
        self._pool = pool
        self._target_service = target_service
        self._preview_panel = preview_panel
        self._notify = notify
        self._dir_edit: QLineEdit | None = None
        self._prefix_edit: QLineEdit | None = None
        self._content_combo: QComboBox | None = None
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

        self._prefix_edit = QLineEdit("export")
        form.addRow("文件前缀:", self._prefix_edit)

        self._content_combo = QComboBox()
        self._content_combo.addItem("加速度时程", "acc")
        self._content_combo.addItem("速度时程", "vel")
        self._content_combo.addItem("位移时程", "disp")
        self._content_combo.addItem("反应谱", "spectrum")
        self._content_combo.addItem("批量结果表", "scorecard")
        form.addRow("内容:", self._content_combo)

        self._format_combo = QComboBox()
        self._format_combo.addItem("CSV", "csv")
        self._format_combo.addItem("TXT", "txt")
        self._format_combo.addItem("AT2", "at2")
        form.addRow("格式:", self._format_combo)
        layout.addLayout(form)

        export_btn = QPushButton("导出数据")
        export_btn.clicked.connect(self.export)
        layout.addWidget(export_btn)

    def _browse_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择数据输出目录")
        if path and self._dir_edit is not None:
            self._dir_edit.setText(path)

    def export(self) -> list[Path]:
        try:
            assert self._dir_edit is not None
            assert self._prefix_edit is not None
            assert self._content_combo is not None
            assert self._format_combo is not None
            output_dir = ensure_directory(self, self._dir_edit.text(), "导出数据")
            if output_dir is None:
                return []

            prefix = self._prefix_edit.text().strip() or "export"
            content = str(self._content_combo.currentData())
            format_name = str(self._format_combo.currentData())

            if content == "scorecard":
                if format_name != "csv":
                    raise ValueError("批量结果表仅支持导出为 CSV")
                written = [self._export_scorecard_csv(output_dir, prefix)]
            elif content == "spectrum":
                if format_name == "at2":
                    raise ValueError("反应谱不支持导出为 AT2")
                written = [self._export_spectrum(output_dir, prefix, format_name)]
            else:
                records = selected_records_or_warn(self, self._pool, "导出数据")
                if not records:
                    return []
                written = [
                    self._export_series(
                        output_dir,
                        prefix,
                        content,
                        format_name,
                        record,
                    )
                    for record in records
                ]

            self._notify(f"已导出 {len(written)} 个数据文件到 {output_dir}")
            return written
        except Exception as exc:
            QMessageBox.critical(self, "导出数据", str(exc))
            return []

    def _export_series(
        self,
        output_dir: Path,
        prefix: str,
        content: str,
        format_name: str,
        record,
    ) -> Path:
        values, label = self._series_values(record, content)
        stem = _safe_stem(f"{prefix}-{record.name or record.id}-{content}")
        path = output_dir / f"{stem}.{format_name}"

        if format_name == "csv":
            FileIO.write_csv(path, time=np.arange(record.n) * record.dt, **{label: values})
            return path

        if format_name == "txt":
            data = np.column_stack([np.arange(record.n) * record.dt, values])
            np.savetxt(
                path,
                data,
                fmt="%15.7E",
                delimiter="  ",
                header=f"time  {label}\ndt={record.dt}  npts={record.n}",
                comments="# ",
            )
            return path

        header_label = {
            "acc": "ACCELERATION (G)",
            "vel": "VELOCITY",
            "disp": "DISPLACEMENT",
        }[content]
        FileIO.write_at2(
            path,
            np.asarray(values, dtype=np.float64),
            record.dt,
            metadata={
                "header1": "SEISWAVE WORKBENCH EXPORT",
                "header2": f"{record.name or record.id}, {content}",
                "header3": header_label,
            },
        )
        return path

    def _series_values(self, record, content: str) -> tuple[np.ndarray, str]:
        if content == "acc":
            return np.asarray(record.acc, dtype=np.float64), "acc"
        if content == "vel":
            return np.asarray(record.vel(), dtype=np.float64), "vel"
        if content == "disp":
            return np.asarray(record.disp(), dtype=np.float64), "disp"
        raise ValueError(f"未知导出内容: {content}")

    def _export_spectrum(
        self,
        output_dir: Path,
        prefix: str,
        format_name: str,
    ) -> Path:
        snapshot = self._preview_panel.current_spectrum_snapshot()
        periods = np.asarray(snapshot["periods"], dtype=np.float64)
        if periods.size == 0:
            raise ValueError("当前无反应谱可导出")

        columns: dict[str, np.ndarray] = {"period": periods}
        target_sa = np.asarray(snapshot["target_sa"], dtype=np.float64)
        if target_sa.size:
            columns["target_sa"] = target_sa

        mean_spectra = snapshot.get("mean_spectra", {})
        for zeta in snapshot["zetas"]:
            if float(zeta) not in mean_spectra:
                continue  # 未选信号时只导出目标谱列，跳过缺失的均值谱
            suffix = f"{int(round(float(zeta) * 100)):02d}pct"
            mean_spectrum = mean_spectra[float(zeta)]
            columns[f"sa_{suffix}"] = np.asarray(mean_spectrum["sa"], dtype=np.float64)
            columns[f"sv_{suffix}"] = np.asarray(mean_spectrum["sv"], dtype=np.float64)
            columns[f"sd_{suffix}"] = np.asarray(mean_spectrum["sd"], dtype=np.float64)

        if len(columns) == 1:  # 只有 period，没有任何谱数据
            raise ValueError("当前无反应谱或目标谱可导出，请先选择信号或设置目标谱")

        path = output_dir / f"{prefix}-spectrum.{format_name}"
        if format_name == "csv":
            FileIO.write_csv(path, **columns)
            return path

        header = " ".join(columns.keys())
        data = np.column_stack([columns[key] for key in columns])
        np.savetxt(path, data, fmt="%15.7E", header=header, comments="# ")
        return path

    def _export_scorecard_csv(self, output_dir: Path, prefix: str) -> Path:
        records = selected_records_or_warn(self, self._pool, "导出结果表")
        if not records:
            raise ValueError("当前无已选信号可导出结果表")

        path = output_dir / f"{prefix}-scorecard.csv"
        fieldnames = [
            "id",
            "name",
            "kind",
            "parent_id",
            "mean_error_pct",
            "pga",
            "pgv",
            "pgd",
            "arias",
            "duration_sig",
        ]
        with path.open("w", newline="", encoding="utf-8") as file_obj:
            writer = csv.DictWriter(file_obj, fieldnames=fieldnames)
            writer.writeheader()
            for record in records:
                metrics = compute_scorecard_metrics([record], self._target_service)
                writer.writerow(
                    {
                        "id": record.id,
                        "name": record.name,
                        "kind": record.kind,
                        "parent_id": record.parent_id or "",
                        "mean_error_pct": f"{metrics['mean_error_pct']:.6f}",
                        "pga": f"{metrics['pga']:.6f}",
                        "pgv": f"{metrics['pgv']:.6f}",
                        "pgd": f"{metrics['pgd']:.6f}",
                        "arias": f"{metrics['arias']:.6f}",
                        "duration_sig": f"{metrics['duration_sig']:.6f}",
                    }
                )
        return path

    def state(self) -> dict[str, object]:
        assert self._dir_edit is not None
        assert self._prefix_edit is not None
        assert self._content_combo is not None
        assert self._format_combo is not None
        return {
            "output_dir": self._dir_edit.text(),
            "prefix": self._prefix_edit.text(),
            "content": self._content_combo.currentData(),
            "format": self._format_combo.currentData(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        if state is None:
            state = {}
        assert self._dir_edit is not None
        assert self._prefix_edit is not None
        assert self._content_combo is not None
        assert self._format_combo is not None
        self._dir_edit.setText(str(state.get("output_dir", "")))
        self._prefix_edit.setText(str(state.get("prefix", "export")))
        content = str(state.get("content", "acc"))
        index = self._content_combo.findData(content)
        if index >= 0:
            self._content_combo.setCurrentIndex(index)
        format_name = str(state.get("format", "csv"))
        index = self._format_combo.findData(format_name)
        if index >= 0:
            self._format_combo.setCurrentIndex(index)
