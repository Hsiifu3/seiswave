"""Artificial ground-motion generation tool."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

import numpy as np

from seiswave.core.generator import WaveGenerator, create_ground_motion
from seiswave.core.signal_pool import SignalRecord

from .common import ToolWidget, target_or_warn


def _target_meta(target_service) -> dict[str, object]:
    return {
        "target_source": target_service.source(),
        "target_description": target_service.describe(),
        "target_meta": target_service.meta(),
        "zeta": target_service.zeta(),
    }


class ArtificialTool(ToolWidget):
    """Generate general / FF / NF / NFP motions into the shared pool."""

    def __init__(self, pool, target_service, notify, parent=None) -> None:
        super().__init__(parent)
        self._pool = pool
        self._target_service = target_service
        self._notify = notify
        self._type_combo: QComboBox | None = None
        self._n_spin: QSpinBox | None = None
        self._dt_spin: QDoubleSpinBox | None = None
        self._zeta_spin: QDoubleSpinBox | None = None
        self._tol_spin: QDoubleSpinBox | None = None
        self._iter_spin: QSpinBox | None = None
        self._trials_spin: QSpinBox | None = None
        self._fm_combo: QComboBox | None = None
        self._mw_spin: QDoubleSpinBox | None = None
        self._r_spin: QDoubleSpinBox | None = None
        self._vs30_spin: QDoubleSpinBox | None = None
        self._fault_combo: QComboBox | None = None
        self._gamma_spin: QDoubleSpinBox | None = None
        self._gmpe_check: QCheckBox | None = None
        self._region_combo: QComboBox | None = None
        self._axis_combo: QComboBox | None = None
        self._hint_label: QLabel | None = None
        self._setup_ui()
        self._refresh_mode_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._hint_label = QLabel(
            "一般人工波使用当前目标谱；FF/NF/NFP 默认复用当前目标谱，"
            "可切换到情景/危险性谱（第五代区划 GMPE，非规范设计谱）。"
        )
        self._hint_label.setWordWrap(True)
        layout.addWidget(self._hint_label)

        form = QFormLayout()

        self._type_combo = QComboBox()
        self._type_combo.addItem("一般人工波", "general")
        self._type_combo.addItem("远场 FF", "FF")
        self._type_combo.addItem("近场 NF", "NF")
        self._type_combo.addItem("近场脉冲 NFP", "NFP")
        self._type_combo.currentIndexChanged.connect(self._refresh_mode_ui)
        form.addRow("类型:", self._type_combo)

        self._n_spin = QSpinBox()
        self._n_spin.setRange(64, 32768)
        self._n_spin.setSingleStep(128)
        self._n_spin.setValue(512)
        form.addRow("点数 n:", self._n_spin)

        self._dt_spin = QDoubleSpinBox()
        self._dt_spin.setRange(0.001, 0.2)
        self._dt_spin.setDecimals(4)
        self._dt_spin.setSingleStep(0.005)
        self._dt_spin.setValue(0.02)
        form.addRow("步长 dt (s):", self._dt_spin)

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
        self._iter_spin.setRange(1, 200)
        self._iter_spin.setValue(8)
        form.addRow("迭代上限:", self._iter_spin)

        self._trials_spin = QSpinBox()
        self._trials_spin.setRange(1, 20)
        self._trials_spin.setValue(1)
        form.addRow("n_trials:", self._trials_spin)

        self._fm_combo = QComboBox()
        self._fm_combo.addItem("时域法 fm=1", 1)
        self._fm_combo.addItem("频域法 fm=0", 0)
        self._fm_combo.setCurrentIndex(0)
        form.addRow("匹配算法:", self._fm_combo)

        self._mw_spin = QDoubleSpinBox()
        self._mw_spin.setRange(4.5, 8.5)
        self._mw_spin.setDecimals(2)
        self._mw_spin.setValue(7.0)
        form.addRow("Mw:", self._mw_spin)

        self._r_spin = QDoubleSpinBox()
        self._r_spin.setRange(0.0, 300.0)
        self._r_spin.setDecimals(2)
        self._r_spin.setValue(10.0)
        form.addRow("R (km):", self._r_spin)

        self._vs30_spin = QDoubleSpinBox()
        self._vs30_spin.setRange(150.0, 2000.0)
        self._vs30_spin.setDecimals(1)
        self._vs30_spin.setValue(760.0)
        form.addRow("Vs30:", self._vs30_spin)

        self._fault_combo = QComboBox()
        self._fault_combo.addItem("走滑 strike_slip", "strike_slip")
        self._fault_combo.addItem("正断层 normal", "normal")
        self._fault_combo.addItem("逆断层 reverse", "reverse")
        form.addRow("断层类型:", self._fault_combo)

        self._gamma_spin = QDoubleSpinBox()
        self._gamma_spin.setRange(1.0, 3.0)
        self._gamma_spin.setDecimals(1)
        self._gamma_spin.setSingleStep(0.1)
        self._gamma_spin.setValue(1.8)
        self._gamma_spin.setToolTip(
            "MP(2003) 脉冲振荡参数 γ：脉冲半周期数。默认 1.8 为文献标定均值，"
            "范围约 1–3。仅近场脉冲 NFP 有效。"
        )
        form.addRow("脉冲 γ (NFP):", self._gamma_spin)

        self._gmpe_check = QCheckBox("情景/危险性谱（第五代区划 GMPE，非规范设计谱）")
        self._gmpe_check.toggled.connect(self._refresh_mode_ui)
        form.addRow("特殊谱源:", self._gmpe_check)

        self._region_combo = QComboBox()
        self._region_combo.addItem("东部强震区", "east_strong")
        self._region_combo.addItem("中强地震区", "moderate")
        self._region_combo.addItem("新疆区", "xinjiang")
        self._region_combo.addItem("青藏区", "tibet")
        form.addRow("分区:", self._region_combo)

        self._axis_combo = QComboBox()
        self._axis_combo.addItem("长轴", "major")
        self._axis_combo.addItem("短轴", "minor")
        form.addRow("椭圆轴:", self._axis_combo)

        layout.addLayout(form)
        layout.addStretch(1)

    def _refresh_mode_ui(self) -> None:
        assert self._type_combo is not None
        assert self._trials_spin is not None
        assert self._fm_combo is not None
        assert self._mw_spin is not None
        assert self._r_spin is not None
        assert self._vs30_spin is not None
        assert self._fault_combo is not None
        assert self._gmpe_check is not None
        assert self._region_combo is not None
        assert self._axis_combo is not None

        gm_type = str(self._type_combo.currentData())
        is_general = gm_type == "general"
        is_special = not is_general

        self._trials_spin.setEnabled(is_general)
        self._mw_spin.setEnabled(is_special)
        self._r_spin.setEnabled(is_special)
        self._vs30_spin.setEnabled(is_special)
        self._fault_combo.setEnabled(is_special)
        self._gmpe_check.setEnabled(is_special)
        self._region_combo.setEnabled(is_special and self._gmpe_check.isChecked())
        self._axis_combo.setEnabled(is_special and self._gmpe_check.isChecked())
        if self._gamma_spin is not None:
            self._gamma_spin.setEnabled(gm_type == "NFP")  # γ 仅 NFP 有效

        if is_special and gm_type == "NFP":
            self._fm_combo.setCurrentIndex(self._fm_combo.findData(0))

    def run_tool(self) -> list[SignalRecord]:
        prepared = self._prepare()
        if prepared is None:
            return []
        try:
            payload = self._compute(prepared, lambda *_: None, lambda: False)
            return self._finalize(payload)
        except Exception as exc:
            QMessageBox.critical(self, "人工波生成", str(exc))
            return []

    def build_job(self):
        prepared = self._prepare()
        if prepared is None:
            return None
        compute = lambda progress, is_cancelled: self._compute(prepared, progress, is_cancelled)
        return compute, self._finalize

    def _prepare(self):
        """GUI 线程：快照参数 + 校验目标谱。"""
        assert self._type_combo is not None
        assert self._n_spin is not None
        assert self._dt_spin is not None
        assert self._zeta_spin is not None
        assert self._tol_spin is not None
        assert self._iter_spin is not None
        assert self._trials_spin is not None
        assert self._fm_combo is not None
        assert self._mw_spin is not None
        assert self._r_spin is not None
        assert self._vs30_spin is not None
        assert self._fault_combo is not None
        assert self._gmpe_check is not None
        assert self._region_combo is not None
        assert self._axis_combo is not None

        gm_type = str(self._type_combo.currentData())
        ctx = {
            "gm_type": gm_type,
            "n": int(self._n_spin.value()),
            "dt": float(self._dt_spin.value()),
            "zeta": float(self._zeta_spin.value()),
            "tol": float(self._tol_spin.value()),
            "max_iter": int(self._iter_spin.value()),
            "n_trials": int(self._trials_spin.value()),
            "fm": int(self._fm_combo.currentData()),
            "Mw": float(self._mw_spin.value()),
            "R": float(self._r_spin.value()),
            "Vs30": float(self._vs30_spin.value()),
            "fault_type": str(self._fault_combo.currentData()),
            "region": str(self._region_combo.currentData()),
            "axis": str(self._axis_combo.currentData()),
            "gamma": float(self._gamma_spin.value()) if self._gamma_spin is not None else 1.8,
        }
        if gm_type == "general":
            target = target_or_warn(self, self._target_service, "人工波生成")
            if target is None:
                return None
            ctx["periods"], ctx["target_sa"] = target
            ctx["spectrum_source"] = "code"
        else:
            spectrum_source = "gmpe" if self._gmpe_check.isChecked() else "code"
            ctx["spectrum_source"] = spectrum_source
            ctx["code_periods"] = None
            ctx["code_sa"] = None
            if spectrum_source == "code":
                target = target_or_warn(self, self._target_service, "人工波生成")
                if target is None:
                    return None
                ctx["code_periods"], ctx["code_sa"] = target
        return ctx

    def _compute(self, ctx, progress_cb, is_cancelled):
        progress_cb(15, "人工波生成中…")
        if is_cancelled():
            raise InterruptedError("用户取消")
        gm_type = ctx["gm_type"]
        if gm_type == "general":
            target_sa = ctx["target_sa"]
            sig = WaveGenerator.generate(
                target_spectrum=np.asarray(target_sa, dtype=np.float64),
                periods=np.asarray(ctx["periods"], dtype=np.float64),
                n=ctx["n"],
                dt=ctx["dt"],
                zeta=ctx["zeta"],
                pga=float(np.max(target_sa)),
                tol=ctx["tol"],
                max_iter=ctx["max_iter"],
                n_trials=ctx["n_trials"],
                fm=ctx["fm"],
            )
            sig.name = f"一般人工波_{sig.n}x{sig.dt:.3f}"
        else:
            sig = create_ground_motion(
                gm_type,
                Mw=ctx["Mw"],
                R=ctx["R"],
                Vs30=ctx["Vs30"],
                fault_type=ctx["fault_type"],
                n=ctx["n"],
                dt=ctx["dt"],
                zeta=ctx["zeta"],
                tol=ctx["tol"],
                max_iter=ctx["max_iter"],
                fm=ctx["fm"],
                spectrum_source=ctx["spectrum_source"],
                code_periods=ctx["code_periods"],
                code_sa=ctx["code_sa"],
                region=ctx["region"],
                axis=ctx["axis"],
                gamma=ctx["gamma"],
            )
        progress_cb(95, "写入信号库…")
        return {"sig": sig, "gm_type": gm_type}

    def _finalize(self, payload) -> list[SignalRecord]:
        result = payload["sig"]
        gm_type = payload["gm_type"]
        child = SignalRecord(
            acc=np.asarray(result.acc, dtype=np.float64).copy(),
            dt=float(result.dt),
            name=result.name,
            kind="artificial",
            meta=self._build_meta(result, gm_type),
        )
        child_id = self._pool.add(child)
        self._pool.set_selection([child_id])
        self._notify(f"人工波生成完成，已入池 1 条 {result.name}")
        return [child]

    def _build_meta(self, sig, gm_type: str) -> dict[str, object]:
        assert self._trials_spin is not None
        assert self._fm_combo is not None
        meta = {
            "source": "artificial_generation",
            "generation_type": gm_type,
            "n_trials": int(self._trials_spin.value()),
            "fm": int(self._fm_combo.currentData()),
            "pga": float(np.max(np.abs(sig.acc))),
            **_target_meta(self._target_service),
        }
        meta["spectrum_source"] = getattr(
            sig,
            "spectrum_source",
            self._target_service.source(),
        )
        meta["near_field_factor"] = float(
            getattr(sig, "near_field_factor", 1.0)
        )
        meta["pulse"] = bool(getattr(sig, "pulse_params", None) is not None)
        pulse_params = getattr(sig, "pulse_params", None)
        if pulse_params is not None:
            meta["pulse_gamma"] = float(getattr(pulse_params, "gamma", 1.8))
            meta["pulse_Tp"] = float(getattr(pulse_params, "Tp", 0.0))
        if hasattr(sig, "pulse_metrics") and getattr(sig, "pulse_metrics"):
            meta["pulse_metrics"] = dict(sig.pulse_metrics)
        if hasattr(sig, "spectrum_periods") and hasattr(sig, "total_spectrum"):
            meta["generated_periods"] = np.asarray(sig.spectrum_periods).tolist()
            meta["generated_target_sa"] = np.asarray(sig.total_spectrum).tolist()
        return meta

    def state(self) -> dict[str, object]:
        assert self._type_combo is not None
        assert self._n_spin is not None
        assert self._dt_spin is not None
        assert self._zeta_spin is not None
        assert self._tol_spin is not None
        assert self._iter_spin is not None
        assert self._trials_spin is not None
        assert self._fm_combo is not None
        assert self._mw_spin is not None
        assert self._r_spin is not None
        assert self._vs30_spin is not None
        assert self._fault_combo is not None
        assert self._gmpe_check is not None
        assert self._region_combo is not None
        assert self._axis_combo is not None
        return {
            "type": self._type_combo.currentData(),
            "n": self._n_spin.value(),
            "dt": self._dt_spin.value(),
            "zeta": self._zeta_spin.value(),
            "tol": self._tol_spin.value(),
            "max_iter": self._iter_spin.value(),
            "n_trials": self._trials_spin.value(),
            "fm": self._fm_combo.currentData(),
            "Mw": self._mw_spin.value(),
            "R": self._r_spin.value(),
            "Vs30": self._vs30_spin.value(),
            "fault_type": self._fault_combo.currentData(),
            "gmpe": self._gmpe_check.isChecked(),
            "region": self._region_combo.currentData(),
            "axis": self._axis_combo.currentData(),
            "gamma": self._gamma_spin.value() if self._gamma_spin is not None else 1.8,
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        if state is None:
            state = {}
        assert self._type_combo is not None
        assert self._n_spin is not None
        assert self._dt_spin is not None
        assert self._zeta_spin is not None
        assert self._tol_spin is not None
        assert self._iter_spin is not None
        assert self._trials_spin is not None
        assert self._fm_combo is not None
        assert self._mw_spin is not None
        assert self._r_spin is not None
        assert self._vs30_spin is not None
        assert self._fault_combo is not None
        assert self._gmpe_check is not None
        assert self._region_combo is not None
        assert self._axis_combo is not None

        for combo, key, default in (
            (self._type_combo, "type", "general"),
            (self._fm_combo, "fm", 1),
            (self._fault_combo, "fault_type", "strike_slip"),
            (self._region_combo, "region", "east_strong"),
            (self._axis_combo, "axis", "major"),
        ):
            index = combo.findData(state.get(key, default))
            if index >= 0:
                combo.setCurrentIndex(index)

        self._n_spin.setValue(int(state.get("n", 512)))
        self._dt_spin.setValue(float(state.get("dt", 0.02)))
        self._zeta_spin.setValue(float(state.get("zeta", 0.05)))
        self._tol_spin.setValue(float(state.get("tol", 0.05)))
        self._iter_spin.setValue(int(state.get("max_iter", 8)))
        self._trials_spin.setValue(int(state.get("n_trials", 1)))
        self._mw_spin.setValue(float(state.get("Mw", 7.0)))
        self._r_spin.setValue(float(state.get("R", 10.0)))
        self._vs30_spin.setValue(float(state.get("Vs30", 760.0)))
        self._gmpe_check.setChecked(bool(state.get("gmpe", False)))
        if self._gamma_spin is not None:
            self._gamma_spin.setValue(float(state.get("gamma", 1.8)))
        self._refresh_mode_ui()
