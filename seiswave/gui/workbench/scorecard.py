"""工作台拟合记分卡。"""

from __future__ import annotations

from collections.abc import Sequence
from math import isnan

import numpy as np
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QGroupBox, QLabel, QVBoxLayout, QWidget

from seiswave.core.signal import EQSignal
from seiswave.core.signal_pool import SignalRecord
from seiswave.core.target_spectrum import TargetSpectrumService


METRIC_LABELS = {
    "mean_error_pct": "均值误差",
    "pga": "PGA",
    "pgv": "PGV",
    "pgd": "PGD",
    "arias": "Arias",
    "duration_sig": "显著持时",
}


METRIC_UNITS = {
    "mean_error_pct": "%",
    "pga": "g",
    "pgv": "g·s",
    "pgd": "g·s²",
    "arias": "m/s",
    "duration_sig": "s",
}


METRIC_DECIMALS = {
    "mean_error_pct": 2,
    "pga": 4,
    "pgv": 4,
    "pgd": 4,
    "arias": 4,
    "duration_sig": 2,
}


EMPTY_METRICS = {
    "selected_count": 0,
    "mean_error_pct": float("nan"),
    "pga": float("nan"),
    "pgv": float("nan"),
    "pgd": float("nan"),
    "arias": float("nan"),
    "duration_sig": float("nan"),
}



def _record_metrics(record: SignalRecord) -> dict[str, float]:
    sig = EQSignal(record.acc, record.dt, name=record.name)
    arias = sig.arias_intensity()
    arias_total = float(arias[-1]) if len(arias) else 0.0
    return {
        "pga": float(np.max(np.abs(record.acc))),
        "pgv": float(np.max(np.abs(record.vel()))),
        "pgd": float(np.max(np.abs(record.disp()))),
        "arias": arias_total,
        "duration_sig": float(sig.effective_duration),
    }



def compute_scorecard_metrics(
    records: Sequence[SignalRecord],
    target_service: TargetSpectrumService | None,
) -> dict[str, float]:
    """计算当前选中信号的拟合记分卡。"""
    if not records:
        return dict(EMPTY_METRICS)

    metrics = dict(EMPTY_METRICS)
    metrics["selected_count"] = len(records)
    per_record = [_record_metrics(record) for record in records]

    for key in ("pga", "pgv", "pgd", "arias", "duration_sig"):
        metrics[key] = float(np.mean([item[key] for item in per_record]))

    if target_service is None:
        return metrics

    target_sa = target_service.sa()
    if target_sa.size == 0:
        return metrics

    periods = target_service.periods()
    zeta = target_service.zeta()
    mean_sa = np.mean(
        [record.spectrum(periods, zeta=zeta).sa for record in records],
        axis=0,
    )
    denom = np.maximum(np.abs(target_sa), 1e-12)
    metrics["mean_error_pct"] = float(
        np.mean(np.abs(mean_sa - target_sa) / denom) * 100.0
    )
    return metrics


class Scorecard(QWidget):
    """中央预览区的拟合记分卡。"""

    metrics_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._metrics = dict(EMPTY_METRICS)
        self._value_labels: dict[str, QLabel] = {}
        self._summary_label: QLabel | None = None
        self._setup_ui()
        self._render_metrics()

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        group = QGroupBox("拟合记分卡")
        root.addWidget(group)

        layout = QVBoxLayout(group)
        self._summary_label = QLabel("未选择信号")
        layout.addWidget(self._summary_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        layout.addLayout(grid)

        for row, key in enumerate(METRIC_LABELS):
            name_label = QLabel(f"{METRIC_LABELS[key]}")
            value_label = QLabel("--")
            unit_label = QLabel(METRIC_UNITS[key])
            grid.addWidget(name_label, row, 0)
            grid.addWidget(value_label, row, 1)
            grid.addWidget(unit_label, row, 2)
            self._value_labels[key] = value_label

    def metrics(self) -> dict[str, float]:
        """返回最近一次计算的指标。"""
        return dict(self._metrics)

    def update_records(
        self,
        records: Sequence[SignalRecord],
        target_service: TargetSpectrumService | None,
    ) -> None:
        """根据选中信号与目标谱刷新记分卡。"""
        self._metrics = compute_scorecard_metrics(records, target_service)
        self._render_metrics()
        self.metrics_changed.emit(self.metrics())

    def _render_metrics(self) -> None:
        count = int(self._metrics["selected_count"])
        if self._summary_label is not None:
            if count == 0:
                self._summary_label.setText("未选择信号")
            else:
                self._summary_label.setText(f"已选 {count} 条信号（展示均值）")

        for key, label in self._value_labels.items():
            label.setText(self._format_metric(key, self._metrics[key]))

    def _format_metric(self, key: str, value: float) -> str:
        if isnan(value):
            return "--"
        decimals = METRIC_DECIMALS[key]
        return f"{value:.{decimals}f}"
