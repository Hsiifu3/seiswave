"""Automatic record-selection tool."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from seiswave.core.io import FileIO
from seiswave.core.peer_db import PeerDatabase, PeerRecord
from seiswave.core.selector import SelectionConfig, WaveSelector
from seiswave.core.signal import EQSignal
from seiswave.core.signal_pool import SignalRecord

from .common import ToolWidget, target_or_warn


@dataclass
class _PoolCandidate:
    source_record: SignalRecord
    peer_record: PeerRecord


class _PoolCandidateDatabase:
    def __init__(self, candidates: list[_PoolCandidate], periods: np.ndarray) -> None:
        self._candidates = candidates
        self.records = [item.peer_record for item in candidates]
        self._lookup = {item.peer_record.rsn: item.source_record for item in candidates}
        self._spectra_periods = np.asarray(periods, dtype=np.float64).copy()

    def get_horizontal(self) -> list[PeerRecord]:
        return list(self.records)

    def filter(self, rsn=None, **_kwargs):
        if rsn is None:
            return list(self.records)
        return [record for record in self.records if record.rsn == rsn]

    def load_waveform(self, record: PeerRecord) -> np.ndarray:
        source = self._lookup.get(record.rsn)
        if source is None:
            raise KeyError(f"未找到候选源记录: {record.rsn}")
        return np.asarray(source.acc, dtype=np.float64)

    @property
    def spectra_periods(self) -> np.ndarray:
        return self._spectra_periods


class AutoSelectTool(ToolWidget):
    """Select the best natural records from PEER or imported candidates."""

    def __init__(self, pool, target_service, notify, parent=None) -> None:
        super().__init__(parent)
        self._pool = pool
        self._target_service = target_service
        self._notify = notify
        self._source_combo: QComboBox | None = None
        self._path_edit: QLineEdit | None = None
        self._n_select_spin: QSpinBox | None = None
        self._scale_lo_spin: QDoubleSpinBox | None = None
        self._scale_hi_spin: QDoubleSpinBox | None = None
        self._tol_spin: QDoubleSpinBox | None = None
        self._dur_factor_spin: QDoubleSpinBox | None = None
        self._t1_spin: QDoubleSpinBox | None = None
        self._t2_spin: QDoubleSpinBox | None = None
        self._t3_spin: QDoubleSpinBox | None = None
        self._mw_spin: QDoubleSpinBox | None = None
        self._r_spin: QDoubleSpinBox | None = None
        self._vs30_spin: QDoubleSpinBox | None = None
        self._setup_ui()
        self._refresh_source_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        hint = QLabel(
            "一键复用现有 WaveSelector：按持时、谱偏差、缩放区间和组合平均谱排序。"
            "Mw/R/Vs30 作为情景条件记录到结果元数据。"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()

        self._source_combo = QComboBox()
        self._source_combo.addItem("PEER 目录", "peer")
        self._source_combo.addItem("已导入候选", "pool")
        self._source_combo.currentIndexChanged.connect(self._refresh_source_ui)
        form.addRow("来源:", self._source_combo)

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("PEER AT2 目录")
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_peer_dir)
        path_row.addWidget(self._path_edit, 1)
        path_row.addWidget(browse_btn)
        form.addRow("PEER 目录:", path_row)

        self._n_select_spin = QSpinBox()
        self._n_select_spin.setRange(1, 20)
        self._n_select_spin.setValue(3)
        form.addRow("数量 N:", self._n_select_spin)

        self._scale_lo_spin = QDoubleSpinBox()
        self._scale_lo_spin.setRange(0.1, 10.0)
        self._scale_lo_spin.setValue(0.5)
        form.addRow("缩放下限:", self._scale_lo_spin)

        self._scale_hi_spin = QDoubleSpinBox()
        self._scale_hi_spin.setRange(0.1, 10.0)
        self._scale_hi_spin.setValue(4.0)
        form.addRow("缩放上限:", self._scale_hi_spin)

        self._tol_spin = QDoubleSpinBox()
        self._tol_spin.setRange(0.05, 1.0)
        self._tol_spin.setDecimals(3)
        self._tol_spin.setValue(0.30)
        form.addRow("谱偏差容限:", self._tol_spin)

        self._dur_factor_spin = QDoubleSpinBox()
        self._dur_factor_spin.setRange(1.0, 20.0)
        self._dur_factor_spin.setValue(5.0)
        form.addRow("持时倍数:", self._dur_factor_spin)

        self._t1_spin = QDoubleSpinBox()
        self._t1_spin.setRange(0.05, 10.0)
        self._t1_spin.setValue(1.0)
        form.addRow("T1 (s):", self._t1_spin)

        self._t2_spin = QDoubleSpinBox()
        self._t2_spin.setRange(0.05, 10.0)
        self._t2_spin.setValue(0.5)
        form.addRow("T2 (s):", self._t2_spin)

        self._t3_spin = QDoubleSpinBox()
        self._t3_spin.setRange(0.05, 10.0)
        self._t3_spin.setValue(0.3)
        form.addRow("T3 (s):", self._t3_spin)

        self._mw_spin = QDoubleSpinBox()
        self._mw_spin.setRange(4.5, 9.0)
        self._mw_spin.setValue(7.0)
        form.addRow("Mw:", self._mw_spin)

        self._r_spin = QDoubleSpinBox()
        self._r_spin.setRange(0.0, 300.0)
        self._r_spin.setValue(10.0)
        form.addRow("R (km):", self._r_spin)

        self._vs30_spin = QDoubleSpinBox()
        self._vs30_spin.setRange(150.0, 2000.0)
        self._vs30_spin.setValue(760.0)
        form.addRow("Vs30:", self._vs30_spin)

        layout.addLayout(form)
        layout.addStretch(1)

    def _refresh_source_ui(self) -> None:
        assert self._source_combo is not None
        assert self._path_edit is not None
        use_peer = self._source_combo.currentData() == "peer"
        self._path_edit.setEnabled(use_peer)

    def _browse_peer_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "选择 PEER 数据目录")
        if path and self._path_edit is not None:
            self._path_edit.setText(path)

    def run_tool(self) -> list[SignalRecord]:
        prepared = self._prepare()
        if prepared is None:
            return []
        try:
            payload = self._compute(prepared, lambda *_: None, lambda: False)
            return self._finalize(payload)
        except Exception as exc:
            QMessageBox.critical(self, "自动选波", str(exc))
            return []

    def build_job(self):
        prepared = self._prepare()
        if prepared is None:
            return None
        compute = lambda progress, is_cancelled: self._compute(prepared, progress, is_cancelled)
        return compute, self._finalize

    def _prepare(self):
        """GUI 线程：校验目标谱、快照配置与候选记录。"""
        assert self._source_combo is not None
        assert self._path_edit is not None
        assert self._mw_spin is not None
        assert self._r_spin is not None
        assert self._vs30_spin is not None
        target = target_or_warn(self, self._target_service, "自动选波")
        if target is None:
            return None
        periods, target_sa = target
        source = str(self._source_combo.currentData())
        ctx = {
            "periods": np.asarray(periods, dtype=np.float64),
            "config": self._build_config(periods, target_sa),
            "source": source,
            "peer_path": self._path_edit.text().strip(),
            "zeta": self._target_service.zeta(),
            "scenario": {
                "Mw": float(self._mw_spin.value()),
                "R": float(self._r_spin.value()),
                "Vs30": float(self._vs30_spin.value()),
            },
        }
        if source != "peer":
            source_records = [
                record
                for record in (self._pool.selection() or self._pool.all())
                if record.kind != "artificial"
                and record.meta.get("operation") != "auto_select"
            ]
            if not source_records:
                QMessageBox.warning(self, "自动选波", "当前没有可作为候选的已导入天然波")
                return None
            ctx["source_records"] = source_records
        return ctx

    def _compute(self, ctx, progress_cb, is_cancelled):
        periods = ctx["periods"]
        if ctx["source"] == "peer":
            database = self._load_peer_database(
                ctx["peer_path"], periods, ctx["zeta"], progress_cb, is_cancelled
            )
            source_label = "peer"
        else:
            progress_cb(20, "计算候选反应谱…")
            database = self._build_pool_database(ctx["source_records"], periods, ctx["zeta"])
            source_label = "pool"

        if is_cancelled():
            raise InterruptedError("用户取消")
        progress_cb(70, "谱型匹配筛选…")

        def _sel_progress(done, total):
            if is_cancelled():
                raise InterruptedError("用户取消")
            frac = 70 + (done / max(total, 1)) * 25
            progress_cb(int(frac), f"筛选 {done}/{total}")

        selector = WaveSelector(ctx["config"])
        try:
            results = selector.select(database, progress_cb=_sel_progress)
        except TypeError:
            results = selector.select(database)
        if not results:
            raise ValueError("当前条件下未筛选到可用天然波")

        progress_cb(96, "载入波形…")
        specs = self._build_specs(results, database, source_label, ctx["scenario"])
        return {"specs": specs}

    def _finalize(self, payload) -> list[SignalRecord]:
        created: list[SignalRecord] = []
        for spec in payload["specs"]:
            if spec["source_record"] is not None:
                child = self._pool.derive(
                    spec["source_record"],
                    spec["acc"],
                    "自动选波",
                    kind="natural",
                    meta=spec["meta"],
                )
            else:
                child = SignalRecord(
                    acc=np.asarray(spec["acc"], dtype=np.float64).copy(),
                    dt=float(spec["dt"]),
                    name=spec["name"],
                    kind="natural",
                    meta=spec["meta"],
                )
                self._pool.add(child)
            created.append(child)
        self._pool.set_selection([record.id for record in created])
        self._notify(f"自动选波完成，已入池 {len(created)} 条天然波")
        return created

    def _load_peer_database(
        self, peer_path, periods, zeta, progress_cb, is_cancelled
    ) -> PeerDatabase:
        path = Path(str(peer_path)).expanduser()
        if not str(peer_path).strip() or not path.exists():
            raise FileNotFoundError(f"PEER 目录不存在: {path}")

        progress_cb(5, "加载 PEER 索引…")
        database = PeerDatabase(str(path))
        if not database.load_index():
            progress_cb(10, "构建 PEER 索引…")
            database.build_index()
            database.save_index()
        if is_cancelled():
            raise InterruptedError("用户取消")

        if not database.load_spectra_cache(zeta):
            def _pre(done, total):
                if is_cancelled():
                    raise InterruptedError("用户取消")
                frac = 15 + (done / max(total, 1)) * 50
                progress_cb(int(frac), f"预算反应谱 {done}/{total}")

            try:
                database.precompute_spectra(
                    np.asarray(periods, dtype=np.float64), zeta=zeta, progress_cb=_pre
                )
            except TypeError:
                database.precompute_spectra(
                    np.asarray(periods, dtype=np.float64), zeta=zeta
                )
        return database

    def _build_pool_database(self, source_records, periods: np.ndarray, zeta):
        candidates: list[_PoolCandidate] = []
        for index, record in enumerate(source_records, start=1):
            acc = np.asarray(record.acc, dtype=np.float64)
            sig = EQSignal(acc, record.dt, name=record.name)
            spectrum = record.spectrum(periods, zeta=zeta)
            rsn_value = record.meta.get("rsn")
            try:
                rsn = int(rsn_value)
            except (TypeError, ValueError):
                rsn = 100000 + index

            peer_record = PeerRecord(
                rsn=rsn,
                event=str(record.meta.get("event", record.name)),
                station=str(record.meta.get("station", record.meta.get("source", "pool"))),
                component=str(record.meta.get("component", f"C{index}")),
                direction="H",
                filepath=record.id,
                dt=record.dt,
                npts=record.n,
                pga=float(np.max(np.abs(acc))),
                duration=float(sig.duration),
                eff_duration=float(sig.effective_duration),
                acc=acc.copy(),
                sa=np.asarray(spectrum.sa, dtype=np.float64).copy(),
            )
            candidates.append(_PoolCandidate(record, peer_record))

        return _PoolCandidateDatabase(candidates, periods)

    def _build_config(self, periods, target_sa) -> SelectionConfig:
        assert self._n_select_spin is not None
        assert self._scale_lo_spin is not None
        assert self._scale_hi_spin is not None
        assert self._tol_spin is not None
        assert self._dur_factor_spin is not None
        assert self._t1_spin is not None
        assert self._t2_spin is not None
        assert self._t3_spin is not None
        return SelectionConfig(
            target_sa=np.asarray(target_sa, dtype=np.float64),
            periods=np.asarray(periods, dtype=np.float64),
            T_main=[
                float(self._t1_spin.value()),
                float(self._t2_spin.value()),
                float(self._t3_spin.value()),
            ],
            zeta=self._target_service.zeta(),
            duration_factor=float(self._dur_factor_spin.value()),
            spectral_tol=float(self._tol_spin.value()),
            n_select=int(self._n_select_spin.value()),
            scale_range=(
                float(self._scale_lo_spin.value()),
                float(self._scale_hi_spin.value()),
            ),
        )

    def _build_specs(
        self,
        results,
        database,
        source_label: str,
        scenario: dict,
    ) -> list[dict]:
        """worker 线程：载入波形并组装入池规格，不触碰 SignalPool。"""
        specs: list[dict] = []
        for index, result in enumerate(results, start=1):
            rec = result.record
            meta = self._result_meta(result, source_label, scenario)
            acc = database.load_waveform(rec) * float(result.scale_factor)
            source_record = None
            if source_label == "pool" and isinstance(database, _PoolCandidateDatabase):
                source_record = database._lookup[rec.rsn]
            specs.append(
                {
                    "acc": np.asarray(acc, dtype=np.float64).copy(),
                    "dt": float(rec.dt),
                    "name": self._peer_record_name(rec, index),
                    "meta": meta,
                    "source_record": source_record,
                }
            )
        return specs

    def _peer_record_name(self, record: PeerRecord, index: int) -> str:
        base = Path(record.filepath).stem if record.filepath else f"RSN{record.rsn}"
        if record.event:
            return f"{base}_{record.event}"
        return f"{base}_{index}"

    def _result_meta(self, result, source_label: str, scenario: dict) -> dict[str, object]:
        return {
            "source": "auto_select",
            "operation": "auto_select",
            "selector_source": source_label,
            "rsn": int(result.record.rsn),
            "event": result.record.event,
            "station": result.record.station,
            "component": result.record.component,
            "scale_factor": float(result.scale_factor),
            "match_rmse": float(result.match_error),
            "deviations": {str(k): float(v) for k, v in result.deviations.items()},
            "Mw": float(scenario["Mw"]),
            "R": float(scenario["R"]),
            "Vs30": float(scenario["Vs30"]),
            "target_source": self._target_service.source(),
            "target_description": self._target_service.describe(),
            "target_meta": self._target_service.meta(),
        }

    def state(self) -> dict[str, object]:
        assert self._source_combo is not None
        assert self._path_edit is not None
        assert self._n_select_spin is not None
        assert self._scale_lo_spin is not None
        assert self._scale_hi_spin is not None
        assert self._tol_spin is not None
        assert self._dur_factor_spin is not None
        assert self._t1_spin is not None
        assert self._t2_spin is not None
        assert self._t3_spin is not None
        assert self._mw_spin is not None
        assert self._r_spin is not None
        assert self._vs30_spin is not None
        return {
            "source": self._source_combo.currentData(),
            "peer_dir": self._path_edit.text(),
            "n_select": self._n_select_spin.value(),
            "scale_lo": self._scale_lo_spin.value(),
            "scale_hi": self._scale_hi_spin.value(),
            "tol": self._tol_spin.value(),
            "duration_factor": self._dur_factor_spin.value(),
            "T1": self._t1_spin.value(),
            "T2": self._t2_spin.value(),
            "T3": self._t3_spin.value(),
            "Mw": self._mw_spin.value(),
            "R": self._r_spin.value(),
            "Vs30": self._vs30_spin.value(),
        }

    def restore_state(self, state: dict[str, object] | None) -> None:
        if state is None:
            state = {}
        assert self._source_combo is not None
        assert self._path_edit is not None
        assert self._n_select_spin is not None
        assert self._scale_lo_spin is not None
        assert self._scale_hi_spin is not None
        assert self._tol_spin is not None
        assert self._dur_factor_spin is not None
        assert self._t1_spin is not None
        assert self._t2_spin is not None
        assert self._t3_spin is not None
        assert self._mw_spin is not None
        assert self._r_spin is not None
        assert self._vs30_spin is not None

        index = self._source_combo.findData(state.get("source", "peer"))
        if index >= 0:
            self._source_combo.setCurrentIndex(index)
        self._path_edit.setText(str(state.get("peer_dir", "")))
        self._n_select_spin.setValue(int(state.get("n_select", 3)))
        self._scale_lo_spin.setValue(float(state.get("scale_lo", 0.5)))
        self._scale_hi_spin.setValue(float(state.get("scale_hi", 4.0)))
        self._tol_spin.setValue(float(state.get("tol", 0.30)))
        self._dur_factor_spin.setValue(float(state.get("duration_factor", 5.0)))
        self._t1_spin.setValue(float(state.get("T1", 1.0)))
        self._t2_spin.setValue(float(state.get("T2", 0.5)))
        self._t3_spin.setValue(float(state.get("T3", 0.3)))
        self._mw_spin.setValue(float(state.get("Mw", 7.0)))
        self._r_spin.setValue(float(state.get("R", 10.0)))
        self._vs30_spin.setValue(float(state.get("Vs30", 760.0)))
        self._refresh_source_ui()
