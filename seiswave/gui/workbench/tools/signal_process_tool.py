"""Baseline-correction and filtering tools."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

from .common import ToolWidget, build_child_meta, selected_records_or_warn, to_eqsignal


class SignalProcessTool(ToolWidget):
    """Apply baseline correction or filtering to selected signals."""

    def __init__(self, pool, notify, mode: str, parent=None) -> None:
        super().__init__(parent)
        if mode not in {"baseline", "filter"}:
            raise ValueError(f"未知处理模式: {mode}")
        self._pool = pool
        self._notify = notify
        self._mode = mode
        self._baseline_combo: QComboBox | None = None
        self._poly_order_spin: QSpinBox | None = None
        self._filter_type_combo: QComboBox | None = None
        self._filter_order_spin: QSpinBox | None = None
        self._f1_spin: QDoubleSpinBox | None = None
        self._f2_spin: QDoubleSpinBox | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()

        if self._mode == "baseline":
            self._baseline_combo = QComboBox()
            self._baseline_combo.addItem("多项式去趋势", "poly")
            self._baseline_combo.addItem("双线性去趋势", "bilinear")
            form.addRow("方法:", self._baseline_combo)

            self._poly_order_spin = QSpinBox()
            self._poly_order_spin.setRange(1, 6)
            self._poly_order_spin.setValue(2)
            form.addRow("多项式阶数:", self._poly_order_spin)
        else:
            self._filter_type_combo = QComboBox()
            self._filter_type_combo.addItem("带通", "bandpass")
            self._filter_type_combo.addItem("高通", "highpass")
            self._filter_type_combo.addItem("低通", "lowpass")
            form.addRow("类型:", self._filter_type_combo)

            self._filter_order_spin = QSpinBox()
            self._filter_order_spin.setRange(2, 8)
            self._filter_order_spin.setValue(4)
            form.addRow("阶数:", self._filter_order_spin)

            self._f1_spin = QDoubleSpinBox()
            self._f1_spin.setRange(0.01, 100.0)
            self._f1_spin.setDecimals(3)
            self._f1_spin.setValue(0.1)
            form.addRow("低截止 (Hz):", self._f1_spin)

            self._f2_spin = QDoubleSpinBox()
            self._f2_spin.setRange(0.05, 100.0)
            self._f2_spin.setDecimals(3)
            self._f2_spin.setValue(25.0)
            form.addRow("高截止 (Hz):", self._f2_spin)

        layout.addLayout(form)
        layout.addStretch(1)

    def run_tool(self) -> list[object]:
        title = "基线校正" if self._mode == "baseline" else "滤波"
        records = selected_records_or_warn(self, self._pool, title)
        if not records:
            return []

        children = []
        child_ids = []
        for record in records:
            signal = to_eqsignal(record)
            if self._mode == "baseline":
                signal, suffix, meta = self._apply_baseline(record, signal)
            else:
                signal, suffix, meta = self._apply_filter(record, signal)
            child = self._pool.derive(
                record,
                signal.acc,
                suffix,
                kind="processed",
                meta=meta,
            )
            children.append(child)
            child_ids.append(child.id)

        self._pool.set_selection(child_ids)
        self._notify(f"{title}完成，新增 {len(children)} 条处理后信号")
        return children

    def _apply_baseline(self, record, signal):
        assert self._baseline_combo is not None
        assert self._poly_order_spin is not None
        method = str(self._baseline_combo.currentData())
        order = int(self._poly_order_spin.value())
        signal.baseline_correction(method=method, order=order)
        suffix = f"基线校正 ({method})"
        meta = build_child_meta(
            record,
            {
                "operation": "baseline_correction",
                "method": method,
                "order": order,
            },
        )
        meta.update({"source": "baseline_correction", "operation": "baseline_correction"})
        return signal, suffix, meta

    def _apply_filter(self, record, signal):
        assert self._filter_type_combo is not None
        assert self._filter_order_spin is not None
        assert self._f1_spin is not None
        assert self._f2_spin is not None
        ftype = str(self._filter_type_combo.currentData())
        order = int(self._filter_order_spin.value())
        f1 = float(self._f1_spin.value())
        f2 = float(self._f2_spin.value())
        signal.filter(ftype=ftype, order=order, f1=f1, f2=f2)
        suffix = f"滤波 ({ftype})"
        meta = build_child_meta(
            record,
            {
                "operation": "filter",
                "ftype": ftype,
                "order": order,
                "f1": f1,
                "f2": f2,
            },
        )
        meta.update({"source": "filter", "operation": "filter"})
        return signal, suffix, meta

    def state(self) -> dict[str, object]:
        if self._mode == "baseline":
            assert self._baseline_combo is not None
            assert self._poly_order_spin is not None
            return {
                "mode": self._mode,
                "method": self._baseline_combo.currentData(),
                "order": self._poly_order_spin.value(),
            }

        assert self._filter_type_combo is not None
        assert self._filter_order_spin is not None
        assert self._f1_spin is not None
        assert self._f2_spin is not None
        return {
            "mode": self._mode,
            "ftype": self._filter_type_combo.currentData(),
            "order": self._filter_order_spin.value(),
            "f1": self._f1_spin.value(),
            "f2": self._f2_spin.value(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        if state is None:
            state = {}
        if self._mode == "baseline":
            assert self._baseline_combo is not None
            assert self._poly_order_spin is not None
            method = str(state.get("method", "poly"))
            index = self._baseline_combo.findData(method)
            if index >= 0:
                self._baseline_combo.setCurrentIndex(index)
            self._poly_order_spin.setValue(int(state.get("order", 2)))
            return

        assert self._filter_type_combo is not None
        assert self._filter_order_spin is not None
        assert self._f1_spin is not None
        assert self._f2_spin is not None
        ftype = str(state.get("ftype", "bandpass"))
        index = self._filter_type_combo.findData(ftype)
        if index >= 0:
            self._filter_type_combo.setCurrentIndex(index)
        self._filter_order_spin.setValue(int(state.get("order", 4)))
        self._f1_spin.setValue(float(state.get("f1", 0.1)))
        self._f2_spin.setValue(float(state.get("f2", 25.0)))
