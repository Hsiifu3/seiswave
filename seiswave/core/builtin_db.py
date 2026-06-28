"""内置地震动库:从预打包的 npz(int16 量化)加载,开箱即用、全离线。

数据由 `tools/build_builtin_db.py` 生成,放 `seiswave/data/builtin_db/`：
- waveforms.npz   每条 int16 量化加速度(键=记录 id)
- spectra_z0.05.npz   全部反应谱 sa(N×Np)+ ids + periods
- index.json      每条元数据(含 int16 还原用的 scale)

对外暴露与 selector 所需一致的接口：records / spectra_periods / load_waveform。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np

from .peer_db import PeerRecord


def _default_db_dir() -> Path:
    """定位内置库目录,兼容源码运行与 PyInstaller 打包(_MEIPASS)。"""
    candidates = [Path(__file__).resolve().parent.parent / "data" / "builtin_db"]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "seiswave" / "data" / "builtin_db")
    for c in candidates:
        if (c / "waveforms.npz").exists():
            return c
    return candidates[0]


_DB_DIR = _default_db_dir()
_SPECTRA = "spectra_z0.05.npz"


class BuiltinDatabase:
    """内置地震动库(只读,预打包)。"""

    def __init__(self, db_dir: Optional[str] = None):
        self.db_dir = Path(db_dir) if db_dir else _DB_DIR
        self.records: list[PeerRecord] = []
        self._spectra_periods: Optional[np.ndarray] = None
        self._wf = None
        self._scale: dict[str, float] = {}

    @staticmethod
    def is_available(db_dir: Optional[str] = None) -> bool:
        d = Path(db_dir) if db_dir else _DB_DIR
        return (
            (d / "waveforms.npz").exists()
            and (d / _SPECTRA).exists()
            and (d / "index.json").exists()
        )

    def load(self) -> "BuiltinDatabase":
        """加载索引与预算反应谱(波形按需延迟解码)。"""
        if not self.is_available(str(self.db_dir)):
            raise FileNotFoundError(
                f"内置地震动库未找到: {self.db_dir}\n"
                "请运行 tools/build_builtin_db.py 生成,或从 Release 下载数据包。"
            )
        index = json.loads((self.db_dir / "index.json").read_text(encoding="utf-8"))
        spz = np.load(self.db_dir / _SPECTRA)
        sa = np.asarray(spz["sa"], dtype=np.float64)
        ids = [str(x) for x in spz["ids"]]
        self._spectra_periods = np.asarray(spz["periods"], dtype=np.float64)

        self.records = []
        self._scale = {}
        for i, rid in enumerate(ids):
            meta = index.get(rid)
            if meta is None:
                continue
            self._scale[rid] = float(meta["scale"])
            self.records.append(
                PeerRecord(
                    rsn=i + 1,
                    event=str(meta.get("event", "")),
                    station=str(meta.get("station", "")),
                    date=str(meta.get("date", "")),
                    component=str(meta.get("component", "")),
                    direction="H",
                    filepath=rid,  # 用 id 作为波形键
                    dt=float(meta["dt"]),
                    npts=int(meta["npts"]),
                    pga=float(meta["pga"]),
                    duration=float(meta.get("duration", meta["npts"] * meta["dt"])),
                    eff_duration=float(meta.get("eff_duration", 0.0)),
                    sa=sa[i],
                )
            )
        return self

    @property
    def spectra_periods(self) -> Optional[np.ndarray]:
        return self._spectra_periods

    def get_horizontal(self) -> list[PeerRecord]:
        """全部为水平分量记录。"""
        return self.records

    def get_vertical(self) -> list[PeerRecord]:
        return []

    def load_waveform(self, record: PeerRecord) -> np.ndarray:
        """按需从 npz 解码 int16 波形 → 物理加速度(g)。"""
        if self._wf is None:
            self._wf = np.load(self.db_dir / "waveforms.npz")
        rid = record.filepath
        q = np.asarray(self._wf[rid], dtype=np.float64)
        return q * self._scale.get(rid, 1.0)

    def __len__(self) -> int:
        return len(self.records)

    def __repr__(self) -> str:
        return f"BuiltinDatabase({len(self.records)} records @ {self.db_dir})"


__all__ = ["BuiltinDatabase"]
