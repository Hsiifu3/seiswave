"""工作台共享信号池与信号记录。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import numpy as np
from PySide6.QtCore import QObject, Signal

from .signal import EQSignal
from .spectrum import Spectra


def _spectrum_cache_key(periods: np.ndarray, zeta: float) -> tuple[Any, ...]:
    """将周期数组标准化为可哈希缓存键。"""
    periods_arr = np.ascontiguousarray(np.asarray(periods, dtype=np.float64))
    return (float(zeta), periods_arr.shape, periods_arr.tobytes())


@dataclass
class SignalRecord:
    """工作台中的一条共享信号记录。"""

    acc: np.ndarray
    dt: float
    name: str
    kind: str
    meta: dict[str, Any] = field(default_factory=dict)
    parent_id: str | None = None
    id: str = field(default_factory=lambda: uuid4().hex[:8])

    _vel_cache: np.ndarray | None = field(default=None, init=False, repr=False)
    _disp_cache: np.ndarray | None = field(default=None, init=False, repr=False)
    _spectrum_cache: dict[tuple[Any, ...], Spectra] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        self.acc = np.asarray(self.acc, dtype=np.float64).copy()
        self.meta = dict(self.meta)
        self.dt = float(self.dt)
        if self.acc.ndim != 1:
            raise ValueError("acc 必须是一维数组")
        if self.dt <= 0:
            raise ValueError("dt 必须大于 0")

    @property
    def n(self) -> int:
        """时程数据点数。"""
        return len(self.acc)

    def _ensure_kinematics(self) -> None:
        if self._vel_cache is not None and self._disp_cache is not None:
            return

        sig = EQSignal(self.acc, self.dt, name=self.name)
        sig.a2vd()
        self._vel_cache = sig.vel.copy()
        self._disp_cache = sig.disp.copy()

    def vel(self) -> np.ndarray:
        """惰性计算并缓存速度时程。"""
        self._ensure_kinematics()
        assert self._vel_cache is not None
        return self._vel_cache

    def disp(self) -> np.ndarray:
        """惰性计算并缓存位移时程。"""
        self._ensure_kinematics()
        assert self._disp_cache is not None
        return self._disp_cache

    def spectrum(self, periods: np.ndarray, zeta: float = 0.05) -> Spectra:
        """惰性计算并缓存反应谱。"""
        periods_arr = np.asarray(periods, dtype=np.float64).copy()
        cache_key = _spectrum_cache_key(periods_arr, zeta)
        if cache_key not in self._spectrum_cache:
            self._spectrum_cache[cache_key] = Spectra.compute(
                self.acc,
                self.dt,
                periods_arr,
                zeta=zeta,
            )
        return self._spectrum_cache[cache_key]


class SignalPool(QObject):
    """工作台共享信号池。"""

    signals_changed = Signal()
    selection_changed = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._records: dict[str, SignalRecord] = {}
        self._selection_ids: list[str] = []

    def add(self, rec: SignalRecord) -> str:
        """添加一条记录并返回其 ID。"""
        if rec.id in self._records:
            raise ValueError(f"信号 ID 已存在: {rec.id}")
        self._records[rec.id] = rec
        self.signals_changed.emit()
        return rec.id

    def remove(self, id: str) -> None:
        """按 ID 删除记录。"""
        if id not in self._records:
            return

        self._records.pop(id)
        self.signals_changed.emit()

        if id in self._selection_ids:
            self._selection_ids = [
                selected_id
                for selected_id in self._selection_ids
                if selected_id != id
            ]
            self.selection_changed.emit()

    def get(self, id: str) -> SignalRecord:
        """按 ID 获取记录。"""
        return self._records[id]

    def all(self) -> list[SignalRecord]:
        """按插入顺序返回全部记录。"""
        return list(self._records.values())

    def set_selection(self, ids: list[str]) -> None:
        """更新当前选中信号。"""
        seen: set[str] = set()
        cleaned = []
        for signal_id in ids:
            if signal_id in self._records and signal_id not in seen:
                cleaned.append(signal_id)
                seen.add(signal_id)

        if cleaned == self._selection_ids:
            return

        self._selection_ids = cleaned
        self.selection_changed.emit()

    def selection(self) -> list[SignalRecord]:
        """返回当前选中的记录对象。"""
        return [self._records[id] for id in self._selection_ids if id in self._records]

    def derive(
        self,
        parent: SignalRecord,
        acc: np.ndarray,
        name_suffix: str,
        kind: str = "processed",
        meta: dict[str, Any] | None = None,
    ) -> SignalRecord:
        """从父信号派生一条新记录并自动存回池。"""
        child_meta = dict(parent.meta)
        if meta:
            child_meta.update(meta)

        suffix = name_suffix.strip()
        if suffix:
            child_name = f"{parent.name} · {suffix}" if parent.name else suffix
        else:
            child_name = parent.name

        child = SignalRecord(
            acc=np.asarray(acc, dtype=np.float64).copy(),
            dt=parent.dt,
            name=child_name,
            kind=kind,
            meta=child_meta,
            parent_id=parent.id,
        )
        self.add(child)
        return child
