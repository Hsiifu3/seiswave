"""Shared helpers for workbench tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtWidgets import QLabel, QMessageBox, QVBoxLayout, QWidget

from seiswave.core.signal import EQSignal
from seiswave.core.signal_pool import SignalPool, SignalRecord
from seiswave.core.target_spectrum import TargetSpectrumService


class ToolWidget(QWidget):
    """Base class for right-dock tools."""

    def run_label(self) -> str:
        return "▶ 运行"

    def supports_run(self) -> bool:
        return True

    def run_tool(self) -> object | None:
        raise NotImplementedError

    def state(self) -> dict[str, object]:
        return {}

    def restore_state(self, state: dict[str, object] | None) -> None:
        del state


class PlaceholderTool(ToolWidget):
    """Explicit placeholder for later Phase 3 tools."""

    def __init__(self, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(description)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)

    def supports_run(self) -> bool:
        return False

    def run_tool(self) -> None:
        return None


def ensure_directory(parent: QWidget, raw_path: str, title: str) -> Path | None:
    """Validate and create an output directory if needed."""
    path_text = raw_path.strip()
    if not path_text:
        QMessageBox.warning(parent, title, "请先设置输出目录")
        return None
    path = Path(path_text).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def selected_records_or_warn(
    parent: QWidget,
    pool: SignalPool,
    title: str,
) -> list[SignalRecord]:
    """Return selected records or show a warning."""
    records = pool.selection()
    if records:
        return records
    QMessageBox.warning(parent, title, "请先在左侧信号库中选择至少一条信号")
    return []


def target_or_warn(
    parent: QWidget,
    target_service: TargetSpectrumService,
    title: str,
) -> tuple[object, object] | None:
    """Return target periods / spectrum or show a warning."""
    periods = target_service.periods()
    sa = target_service.sa()
    if periods.size and sa.size:
        return periods, sa
    QMessageBox.warning(parent, title, "当前未设置目标谱")
    return None


def to_eqsignal(record: SignalRecord) -> EQSignal:
    """Create a mutable EQSignal copy from a pool record."""
    sig = EQSignal(record.acc.copy(), record.dt, name=record.name)
    sig.a2vd()
    return sig


def build_child_meta(record: SignalRecord, entry: dict[str, Any]) -> dict[str, Any]:
    """Append a provenance entry to a record's metadata."""
    meta = dict(record.meta)
    existing = meta.get("provenance", [])
    provenance = list(existing) if isinstance(existing, list) else [existing]
    provenance.append(dict(entry))
    meta["provenance"] = provenance
    return meta
