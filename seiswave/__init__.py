"""
SeisWave - 地震信号处理与选波工具包

核心计算库 + GUI 桌面应用
"""

from .core import (
    EQSignal, Spectra, Filter, WaveGenerator,
    FileIO, EQRecord, CodeSpectrum,
    WaveSelector, SelectionConfig, SelectionResult,
    PeerDatabase, PeerRecord, Combiner, WaveGroup,
    FFT,
)

__version__ = "2.0.0"

def __getattr__(name):
    if name == 'Response':
        from .core import Response
        return Response
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    'EQSignal',
    'Spectra',
    'Filter',
    'WaveGenerator',
    'FileIO',
    'EQRecord',
    'CodeSpectrum',
    'WaveSelector',
    'SelectionConfig',
    'SelectionResult',
    'PeerDatabase',
    'PeerRecord',
    'Combiner',
    'WaveGroup',
    'FFT',
    'Response',
]
