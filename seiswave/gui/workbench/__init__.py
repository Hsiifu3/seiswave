"""SeisWave 工作台主壳。"""

from __future__ import annotations

from seiswave.core.signal_pool import SignalPool
from seiswave.core.target_spectrum import TargetSpectrumService

_signal_pool_singleton: SignalPool | None = None
_target_spectrum_singleton: TargetSpectrumService | None = None


def get_signal_pool() -> SignalPool:
    """返回工作台共享信号池单例。"""
    global _signal_pool_singleton
    if _signal_pool_singleton is None:
        _signal_pool_singleton = SignalPool()
    return _signal_pool_singleton



def get_target_spectrum_service() -> TargetSpectrumService:
    """返回工作台共享目标谱服务单例。"""
    global _target_spectrum_singleton
    if _target_spectrum_singleton is None:
        _target_spectrum_singleton = TargetSpectrumService()
    return _target_spectrum_singleton


__all__ = [
    "get_signal_pool",
    "get_target_spectrum_service",
]
