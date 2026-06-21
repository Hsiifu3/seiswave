"""Independent spectral-matching tool."""

from __future__ import annotations

from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QMessageBox, QSpinBox, QVBoxLayout

from seiswave.core.generator import WaveGenerator
from seiswave.core.spectral_match import match_to_target

from .common import (
    ToolWidget,
    build_child_meta,
    selected_records_or_warn,
    target_or_warn,
    to_eqsignal,
)


class SpectralMatchTool(ToolWidget):
    """Match selected records to the active target spectrum."""

    def __init__(self, pool, target_service, notify, parent=None) -> None:
        super().__init__(parent)
        self._pool = pool
        self._target_service = target_service
        self._notify = notify
        self._zeta_spin: QDoubleSpinBox | None = None
        self._tol_spin: QDoubleSpinBox | None = None
        self._iter_spin: QSpinBox | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()

        self._zeta_spin = QDoubleSpinBox()
        self._zeta_spin.setRange(0.01, 0.30)
        self._zeta_spin.setDecimals(3)
        self._zeta_spin.setValue(0.05)
        form.addRow("阻尼比 ζ:", self._zeta_spin)

        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.01, 0.50)
        self._tol_spin.setDecimals(3)
        self._tol_spin.setValue(0.05)
        form.addRow("容差:", self._tol_spin)

        self._iter_spin = QSpinBox()
        self._iter_spin.setRange(1, 100)
        self._iter_spin.setValue(10)
        form.addRow("迭代上限:", self._iter_spin)

        layout.addLayout(form)
        layout.addStretch(1)

    def run_tool(self) -> list[object]:
        try:
            records = selected_records_or_warn(self, self._pool, "谱拟合")
            if not records:
                return []
            target = target_or_warn(self, self._target_service, "谱拟合")
            if target is None:
                return []
            periods, target_sa = target
            assert self._zeta_spin is not None
            assert self._tol_spin is not None
            assert self._iter_spin is not None
            zeta = float(self._zeta_spin.value())
            tol = float(self._tol_spin.value())
            max_iter = int(self._iter_spin.value())

            children = []
            child_ids = []
            for record in records:
                signal = to_eqsignal(record)
                matched = match_to_target(
                    signal.acc,
                    signal.dt,
                    periods,
                    target_sa,
                    zeta=zeta,
                    tol=tol,
                    max_iter=max_iter,
                )
                spec = record.spectrum(periods, zeta=zeta)
                fit_before = WaveGenerator.fit_error(spec.sa, target_sa)

                from seiswave.core.spectrum import Spectra

                fit_after = WaveGenerator.fit_error(
                    Spectra.compute(matched, signal.dt, periods, zeta=zeta).sa,
                    target_sa,
                )
                child = self._pool.derive(
                    record,
                    matched,
                    "谱拟合",
                    kind="processed",
                    meta=self._build_meta(
                        record,
                        periods,
                        target_sa,
                        zeta,
                        tol,
                        max_iter,
                        fit_before,
                        fit_after,
                    ),
                )
                children.append(child)
                child_ids.append(child.id)

            self._pool.set_selection(child_ids)
            self._notify(f"谱拟合完成，新增 {len(children)} 条信号")
            return children
        except Exception as exc:
            QMessageBox.critical(self, "谱拟合", str(exc))
            return []

    def _build_meta(
        self,
        record,
        periods,
        target_sa,
        zeta,
        tol,
        max_iter,
        fit_before,
        fit_after,
    ) -> dict[str, object]:
        meta = build_child_meta(
            record,
            {
                "operation": "spectral_match",
                "zeta": zeta,
                "tol": tol,
                "max_iter": max_iter,
                "target_source": self._target_service.source(),
            },
        )
        meta.update(
            {
                "source": "spectral_match",
                "operation": "spectral_match",
                "target_description": self._target_service.describe(),
                "target_meta": self._target_service.meta(),
                "match_rmse_before": float(fit_before["mean_error"]),
                "match_rmse_after": float(fit_after["mean_error"]),
                "generated_periods": periods.tolist(),
                "generated_target_sa": target_sa.tolist(),
            }
        )
        return meta

    def state(self) -> dict[str, object]:
        assert self._zeta_spin is not None
        assert self._tol_spin is not None
        assert self._iter_spin is not None
        return {
            "zeta": self._zeta_spin.value(),
            "tol": self._tol_spin.value(),
            "max_iter": self._iter_spin.value(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        if state is None:
            state = {}
        assert self._zeta_spin is not None
        assert self._tol_spin is not None
        assert self._iter_spin is not None
        self._zeta_spin.setValue(float(state.get("zeta", 0.05)))
        self._tol_spin.setValue(float(state.get("tol", 0.05)))
        self._iter_spin.setValue(int(state.get("max_iter", 10)))
