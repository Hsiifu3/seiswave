"""工作台目标谱服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QObject, Signal

from .code_spec import CodeSpectrum
from .signal_pool import SignalRecord
from .spectrum import Spectra


def _sorted_pairs(periods: np.ndarray, sa: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """按周期升序整理自定义谱。"""
    periods_arr = np.asarray(periods, dtype=np.float64)
    sa_arr = np.asarray(sa, dtype=np.float64)

    if periods_arr.ndim != 1 or sa_arr.ndim != 1:
        raise ValueError("periods 和 sa 必须是一维数组")
    if len(periods_arr) != len(sa_arr):
        raise ValueError("periods 和 sa 长度必须一致")
    if len(periods_arr) == 0:
        raise ValueError("目标谱不能为空")

    order = np.argsort(periods_arr)
    return periods_arr[order], sa_arr[order]


class TargetSpectrumService(QObject):
    """共享目标谱服务，统一管理三种目标谱来源。"""

    target_changed = Signal()

    def __init__(
        self,
        periods: np.ndarray | None = None,
        zeta: float = 0.05,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if periods is None:
            periods = Spectra.default_periods()

        self._periods = np.asarray(periods, dtype=np.float64).copy()
        self._sa: np.ndarray | None = None
        self._zeta = float(zeta)
        self._source: str | None = None
        self._description = "未设置目标谱"
        self._meta: dict[str, Any] = {}

    def set_code(self, code: str = "GB50011", **params: Any) -> None:
        """设置规范目标谱，支持 GB50011 与 GB/T51408。"""
        periods = np.asarray(
            params.pop("periods", self._periods),
            dtype=np.float64,
        ).copy()
        # 规范设计谱仅定义至 6s，截断到规范范围，不向更长周期外推
        periods = periods[periods <= 6.0]
        if periods.size == 0:
            raise ValueError("规范谱周期范围内（0–6s）没有有效周期点")
        zeta = float(params.pop("zeta", self._zeta))
        normalized = code.strip().lower().replace("/", "").replace(" ", "")

        defaults = {
            "intensity": 8,
            "group": 2,
            "site_class": "II",
            "level": "frequent",
        }
        defaults.update(params)

        if normalized in {"gb50011", "gb11"}:
            sa = CodeSpectrum.from_params(
                periods,
                defaults["intensity"],
                defaults["group"],
                defaults["site_class"],
                defaults["level"],
                zeta=zeta,
                isolation=False,
            )
            label = "GB50011"
        elif normalized in {"gbt51408", "gb51408", "51408"}:
            sa = CodeSpectrum.gb51408(
                periods,
                defaults["intensity"],
                defaults["group"],
                defaults["site_class"],
                defaults["level"],
                zeta=zeta,
            )
            label = "GB/T51408"
        else:
            raise ValueError(f"不支持的规范谱类型: {code}")

        self._periods = periods
        self._sa = sa
        self._zeta = zeta
        self._source = "code"
        self._meta = {"code": label, **defaults, "zeta": zeta}
        self._description = (
            f"{label} 目标谱 ({defaults['intensity']}度, "
            f"第{defaults['group']}组, {defaults['site_class']}类场地, "
            f"{defaults['level']}, ζ={zeta:.2f})"
        )
        self.target_changed.emit()

    def set_from_record(
        self,
        rec: SignalRecord,
        periods: np.ndarray | None = None,
        zeta: float | None = None,
    ) -> None:
        """用一条记录的反应谱作为目标谱。"""
        if periods is None:
            periods_arr = self._periods.copy()
        else:
            periods_arr = np.asarray(periods, dtype=np.float64).copy()

        if zeta is None:
            zeta = self._zeta

        spectra = rec.spectrum(periods_arr, zeta=zeta)
        self._periods = periods_arr
        self._sa = np.asarray(spectra.sa, dtype=np.float64).copy()
        self._zeta = float(zeta)
        self._source = "record"
        self._meta = {"record_id": rec.id, "record_name": rec.name, "zeta": self._zeta}
        self._description = f"记录目标谱 ({rec.name}, ζ={self._zeta:.2f})"
        self.target_changed.emit()

    def set_custom(
        self,
        periods: np.ndarray | str | Path,
        sa: np.ndarray | None = None,
    ) -> None:
        """设置自定义目标谱，支持数组或两列文件。"""
        file_name: str | None = None
        if sa is None and isinstance(periods, (str, Path)):
            file_name = Path(periods).name
            periods_arr, sa_arr = CodeSpectrum.from_csv(str(periods))
        else:
            if sa is None:
                raise ValueError("自定义谱需要同时提供 periods 和 sa")
            periods_arr = np.asarray(periods, dtype=np.float64)
            sa_arr = np.asarray(sa, dtype=np.float64)

        periods_arr, sa_arr = _sorted_pairs(periods_arr, sa_arr)
        self._periods = periods_arr
        self._sa = sa_arr
        self._source = "custom"
        self._meta = {"file_name": file_name}

        if file_name is None:
            self._description = f"自定义目标谱 ({len(periods_arr)} 点)"
        else:
            self._description = f"自定义目标谱 ({file_name}, {len(periods_arr)} 点)"
        self.target_changed.emit()

    def clear(self) -> None:
        """清空当前目标谱。"""
        self._sa = None
        self._source = None
        self._description = "未设置目标谱"
        self._meta = {}
        self.target_changed.emit()

    def periods(self) -> np.ndarray:
        """返回当前目标谱的周期数组。"""
        return self._periods.copy()

    def sa(self) -> np.ndarray:
        """返回当前目标谱加速度数组。"""
        if self._sa is None:
            return np.array([], dtype=np.float64)
        return self._sa.copy()

    def describe(self) -> str:
        """返回当前目标谱的文字描述。"""
        return self._description

    def source(self) -> str | None:
        """返回当前目标谱来源。"""
        return self._source

    def meta(self) -> dict[str, Any]:
        """返回当前目标谱元数据副本。"""
        return dict(self._meta)

    def zeta(self) -> float:
        """返回当前目标谱阻尼比。"""
        return self._zeta
