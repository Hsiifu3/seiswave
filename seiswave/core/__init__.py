"""
SeisWave 核心计算库

纯 Python 实现，无 GUI 依赖。
"""

from .signal import EQSignal
from .spectrum import Spectra
from .filter import Filter, correct_baseline
from .generator import WaveGenerator, FarFieldGenerator, NearFieldNoPulseGenerator
from .io import FileIO, EQRecord, parse_peer_filename
from .code_spec import CodeSpectrum
from .selector import WaveSelector, SelectionConfig, SelectionResult
from .peer_db import PeerDatabase, PeerRecord
from .combiner import Combiner, WaveGroup
from .fft import FFT
from .reporting import build_selection_summary
from .envelope_presets import (
    EnvelopeParams, EnvelopeGenerator,
    FarFieldEnvelope, NearFieldEnvelope, PulseEnvelope,
    get_envelope,
)
from .gmpe import (
    FaultType, MotionType, GMPEParams, GMPEAdapter,
    CustomSpectrum, FEMAP695Scenario,
    FEMA_P695_SCENARIOS, get_fema_scenario,
    compute_fema_spectrum, get_target_spectrum,
    compute_gmpe_spectrum,
)
from .pulse import (
    PulseParams, PulseCalculator, PulseWavelet,
    BakerPulseDetector,
    create_pulse,
)

def __getattr__(name):
    if name == 'Response':
        from .response import Response
        return Response
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    'EQSignal',
    'Spectra',
    'Filter',
    'correct_baseline',
    'WaveGenerator',
    'FarFieldGenerator',
    'NearFieldNoPulseGenerator',
    'FileIO',
    'EQRecord',
    'parse_peer_filename',
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
    'build_selection_summary',
    'EnvelopeParams',
    'EnvelopeGenerator',
    'FarFieldEnvelope',
    'NearFieldEnvelope',
    'PulseEnvelope',
    'get_envelope',
    'FaultType',
    'MotionType',
    'GMPEParams',
    'GMPEAdapter',
    'CustomSpectrum',
    'FEMAP695Scenario',
    'FEMA_P695_SCENARIOS',
    'get_fema_scenario',
    'compute_fema_spectrum',
    'get_target_spectrum',
    'compute_gmpe_spectrum',
    'PulseParams',
    'PulseCalculator',
    'PulseWavelet',
    'BakerPulseDetector',
    'create_pulse',
]