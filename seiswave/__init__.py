"""
SeisWave - 地震信号处理与选波工具包

核心计算库 + GUI 桌面应用
"""

from .core import (
    EQSignal, Spectra, Filter, WaveGenerator,
    FileIO, EQRecord, CodeSpectrum,
    WaveSelector, SelectionCriteria, SelectionResult,
    FFT, Response,
)

__version__ = "2.0.0"

__all__ = [
    'EQSignal',
    'Spectra',
    'Filter',
    'WaveGenerator',
    'FileIO',
    'EQRecord',
    'CodeSpectrum',
    'WaveSelector',
    'SelectionCriteria',
    'SelectionResult',
    'FFT',
    'Response',
]
