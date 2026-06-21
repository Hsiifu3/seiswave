"""工作台项目存取。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from seiswave.core.signal_pool import SignalPool, SignalRecord
from seiswave.core.target_spectrum import TargetSpectrumService


class ProjectIO:
    """序列化/反序列化工作台项目。"""

    VERSION = 1

    @classmethod
    def save_project(
        cls,
        path: str | Path,
        pool: SignalPool,
        target_service: TargetSpectrumService,
        ui_state: dict[str, Any] | None = None,
    ) -> tuple[Path, Path]:
        """保存工作台项目到 JSON + NPZ。"""
        json_path = Path(path)
        npz_path = json_path.with_suffix(".npz")

        arrays: dict[str, np.ndarray] = {}
        records_payload: list[dict[str, Any]] = []
        for index, record in enumerate(pool.all()):
            acc_key = f"record_{index}_acc"
            arrays[acc_key] = np.asarray(record.acc, dtype=np.float64)
            records_payload.append(
                {
                    "id": record.id,
                    "name": record.name,
                    "kind": record.kind,
                    "dt": float(record.dt),
                    "meta": cls._jsonify(record.meta),
                    "parent_id": record.parent_id,
                    "acc_key": acc_key,
                }
            )

        target_payload: dict[str, Any] | None = None
        target_sa = target_service.sa()
        if target_service.source() is not None and target_sa.size:
            periods_key = "target_periods"
            sa_key = "target_sa"
            arrays[periods_key] = np.asarray(target_service.periods(), dtype=np.float64)
            arrays[sa_key] = np.asarray(target_sa, dtype=np.float64)
            target_payload = {
                "source": target_service.source(),
                "zeta": float(target_service.zeta()),
                "meta": cls._jsonify(target_service.meta()),
                "description": target_service.describe(),
                "periods_key": periods_key,
                "sa_key": sa_key,
            }

        payload = {
            "version": cls.VERSION,
            "npz_file": npz_path.name,
            "records": records_payload,
            "selection_ids": pool.selection_ids(),
            "target": target_payload,
            "ui_state": cls._jsonify(ui_state or {}),
        }

        np.savez_compressed(npz_path, **arrays)
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return json_path, npz_path

    @classmethod
    def load_project(
        cls,
        path: str | Path,
        pool: SignalPool | None = None,
        target_service: TargetSpectrumService | None = None,
    ) -> dict[str, Any]:
        """从 JSON + NPZ 载入工作台项目。"""
        json_path = Path(path)
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        npz_path = json_path.with_name(payload.get("npz_file", json_path.with_suffix(".npz").name))

        pool = pool or SignalPool()
        target_service = target_service or TargetSpectrumService()

        arrays = np.load(npz_path, allow_pickle=False)
        try:
            pool.clear()
            for record_payload in payload.get("records", []):
                record = SignalRecord(
                    acc=np.asarray(arrays[record_payload["acc_key"]], dtype=np.float64),
                    dt=float(record_payload["dt"]),
                    name=record_payload["name"],
                    kind=record_payload["kind"],
                    meta=dict(record_payload.get("meta", {})),
                    parent_id=record_payload.get("parent_id"),
                    id=record_payload["id"],
                )
                pool.add(record)
            pool.set_selection(list(payload.get("selection_ids", [])))
            cls._restore_target(target_service, payload.get("target"), arrays, pool)
        finally:
            arrays.close()

        return {
            "pool": pool,
            "target_service": target_service,
            "ui_state": payload.get("ui_state", {}),
        }

    @classmethod
    def _restore_target(
        cls,
        target_service: TargetSpectrumService,
        target_payload: dict[str, Any] | None,
        arrays: np.lib.npyio.NpzFile,
        pool: SignalPool,
    ) -> None:
        target_service.clear()
        if not target_payload:
            return

        periods = np.asarray(arrays[target_payload["periods_key"]], dtype=np.float64)
        sa = np.asarray(arrays[target_payload["sa_key"]], dtype=np.float64)
        source = target_payload.get("source")
        meta = dict(target_payload.get("meta", {}))
        zeta = float(target_payload.get("zeta", 0.05))

        if source == "code":
            code = meta.pop("code", "GB50011")
            meta.pop("zeta", None)
            target_service.set_code(code, periods=periods, zeta=zeta, **meta)
            return

        if source == "record":
            record_id = meta.get("record_id")
            if record_id and record_id in {record.id for record in pool.all()}:
                target_service.set_from_record(pool.get(record_id), periods=periods, zeta=zeta)
                return

        target_service.set_custom(periods, sa)
        file_name = meta.get("file_name")
        if file_name:
            target_service._meta["file_name"] = file_name
            target_service._description = f"自定义目标谱 ({file_name}, {len(periods)} 点)"

    @classmethod
    def _jsonify(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._jsonify(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._jsonify(item) for item in value]
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, Path):
            return str(value)
        return value
